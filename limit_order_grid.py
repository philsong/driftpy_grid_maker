import os
import json
import copy
import sys
import time

sys.path.append("./driftpy/src/")
sys.path.append("./src/")
sys.path.append("../src/")


from anchorpy import Wallet
from anchorpy import Provider
from solders.keypair import Keypair
from solders.pubkey import Pubkey


from solana.rpc.async_api import AsyncClient

from driftpy.constants.config import configs, get_markets_and_oracles
from driftpy.account_subscription_config import AccountSubscriptionConfig
from driftpy.types import *
from driftpy.keypair import load_keypair

# MarketType, OrderType, OrderParams, PositionDirection, OrderTriggerCondition
from driftpy.accounts import get_perp_market_account, get_spot_market_account
from driftpy.accounts.oracle import get_oracle_price_data_and_slot
from driftpy.math.spot_market import get_signed_token_amount, get_token_amount
from driftpy.drift_client import DriftClient
from driftpy.drift_user import DriftUser
from driftpy.constants.numeric_constants import BASE_PRECISION, PRICE_PRECISION, QUOTE_PRECISION
import time


def order_print(orders: list[OrderParams], market_str=None):
    for order in orders:
        if order.price == 0:
            pricestr = "$ORACLE"
            if order.oracle_price_offset > 0:
                pricestr += " + " + str(order.oracle_price_offset / 1e6)
            else:
                pricestr += " - " + str(abs(order.oracle_price_offset) / 1e6)
        else:
            pricestr = "$" + str(order.price / 1e6)

        if market_str == None:
            market_str = configs["mainnet"].markets[order.market_index].symbol

        print(
            str(order.direction).split(".")[-1].replace("()", ""),
            market_str,
            "@",
            pricestr,
        )


def calculate_grid_prices(
    num_of_grids, upper_price, lower_price, current_price, chunk_increment=0.0, spread=0.005, offset=0.0
):
    if upper_price is None and lower_price is None:
        print("calculate_grid_prices spread:", spread, "offset:%.4f" % offset, "chunk_increment:%.4f" % chunk_increment, "num_of_grids:", num_of_grids)
        # default to .5% grid around oracle
        upper_price = current_price * (1. + spread)
        lower_price = current_price * (1. - spread)
    elif upper_price is not None and lower_price is None:
        lower_price = current_price
    elif lower_price is not None and upper_price is None:
        upper_price = current_price

    price_range = upper_price - lower_price
    grid_size = price_range / num_of_grids

    print("calculate_grid_prices current_price:%.4f" % current_price, "lower_price:%.4f" % lower_price, "upper_price:%.4f" % upper_price)
    print("calculate_grid_prices price_range:%.4f" % price_range, "grid_size:%.4f" % grid_size)

    bid_prices = []
    ask_prices = []

    for i in range(num_of_grids):
        price = lower_price + (grid_size * i)
        print("calculate_grid_prices without offset: %d %.4f" % (i, price))
        price_with_offset = price + offset
        print("calculate_grid_prices with    offset: %d %.4f" % (i, price_with_offset))
        if price < current_price and price > lower_price:
            if price_with_offset > current_price: #avoid maker reject
                price_with_offset = current_price
            bid_prices.append(price_with_offset - chunk_increment)
        elif price > current_price and price < upper_price:
            if price_with_offset < current_price: #avoid maker reject
                price_with_offset = current_price
            ask_prices.append(price_with_offset + chunk_increment)

    print(bid_prices)
    print(ask_prices)
    # ask_prices.append(upper_price)
    # reversed(bid_prices)  # make it descending order
    # print(bid_prices)
    # print(ask_prices)
    
    return bid_prices, ask_prices


async def main(
    keypath,
    env,
    url,
    subaccount_id,
    market_name,
    quote_asset_amount,
    grids,
    spread=0.01,
    offset=0,
    upper_price=None,
    lower_price=None,
    min_position=None,
    max_position=None,
    authority=None,
    taker=False,
    target_pos = 0,
):
    if min_position is not None and max_position is not None:
        assert min_position < max_position
        
    keypair_file = os.path.expanduser(keypath)
    keypair = load_keypair(keypair_file)
    print("using public key from keypair file:", keypair.pubkey(), "subaccount=", subaccount_id)
    
    config = configs[env]

    is_perp = "PERP" in market_name.upper()
    market_type = MarketType.Perp() if is_perp else MarketType.Spot()

    market_index = -1
    for perp_market_config in config.perp_markets:
        if perp_market_config.symbol == market_name:
            market_index = perp_market_config.market_index
    for spot_market_config in config.spot_markets:
        if spot_market_config.symbol == market_name:
            market_index = spot_market_config.bank_index

    if market_index == -1:
        print("INVALID MARKET")
        return

    # print("market_index:", market_index)
    
    # print("config.env:", config.env)
    wallet = Wallet(keypair)
    connection = AsyncClient(url)
    provider = Provider(connection, wallet)
    
    perp_markets = [0]
    spot_markets = [0, 1]
    spot_market_oracle_infos, perp_market_oracle_infos, spot_market_indexes = get_markets_and_oracles(perp_markets = perp_markets, spot_markets=spot_markets)

    oracle_infos = spot_market_oracle_infos + perp_market_oracle_infos
    # print("oracle_infos:", oracle_infos)
    drift_acct = DriftClient(
        connection,
        wallet, 
        config.env,             
        perp_market_indexes = perp_markets,
        spot_market_indexes = spot_market_indexes,
        oracle_infos = oracle_infos,
        account_subscription = AccountSubscriptionConfig("demo"),
        authority=Pubkey.from_string(authority) if authority else None,
    )

    await drift_acct.subscribe()
    
    drift_user = drift_acct.get_user()

    market_index = 0
        
    # inspect user's leverage
    leverage = drift_user.get_leverage()
    print('current leverage:', leverage / 10_000)

    if is_perp:
        market = await get_perp_market_account(drift_acct.program, market_index)
        try:
            oracle_data = (
                await get_oracle_price_data_and_slot(connection, market.amm.oracle)
            ).data
            current_price = oracle_data.price / PRICE_PRECISION
        except:
            current_price = (
                market.amm.historical_oracle_data.last_oracle_price / PRICE_PRECISION
            )
        # current_price = 20.00
        current_pos_raw = drift_user.get_perp_position(market_index)
        if current_pos_raw is not None:
            current_pos = current_pos_raw.base_asset_amount / float(BASE_PRECISION)
        else:
            current_pos = 0
        
        print("current_pos_raw:", current_pos_raw)
        if current_pos_raw.open_orders >= 30:
            print("open_orders full:", current_pos_raw.open_orders)
            time.sleep(60)
            return

    else:
        market = await get_spot_market_account(drift_acct.program, market_index)
        try:
            oracle_data = (
                await get_oracle_price_data_and_slot(connection, market.oracle)
            ).data
            current_price = oracle_data.price / PRICE_PRECISION
        except:
            current_price = (
                market.historical_oracle_data.last_oracle_price / PRICE_PRECISION
            )

        spot_pos = await drift_user.get_spot_position(market_index)
        tokens = get_token_amount(
            spot_pos.scaled_balance, market, spot_pos.balance_type
        )
        current_pos = get_signed_token_amount(tokens, spot_pos.balance_type) / (
            10**market.decimals
        )

    print(
        "grid trade for " + market_name,
        "market_index=",
        market_index,
        "price=",
        current_price,
        "current_pos=",
        current_pos,
        "spread=",
        spread
    )
    
    base_asset_amount = quote_asset_amount / current_price

    print("quote_asset_amount: %.1f" % quote_asset_amount, "base_asset_amount:%.1f" % base_asset_amount)
    
    market_index = 0
    perp_position = drift_user.get_perp_position(market_index)

    print("perp_position:", perp_position)
    base_asset_pos = perp_position.base_asset_amount/BASE_PRECISION if perp_position is not None else 0
    
    delta_pos = base_asset_pos - target_pos
    
    offset = -1 * 0.01 * delta_pos / base_asset_amount
    print("target_pos:", target_pos, "base_asset_pos: %.1f" % base_asset_pos, "delta_pos: %.1f" % delta_pos, "offset:  %.6f" % offset)
    # offset =0 
    
    unrealized_pnl = drift_user.get_unrealized_pnl()/QUOTE_PRECISION
    print("unrealized_pnl: %.1f" % unrealized_pnl)
    
    bid_prices, ask_prices = calculate_grid_prices(
        grids, upper_price, lower_price, current_price, offset=offset,spread=spread
    )

    base_asset_amount_per_bid = base_asset_amount / (
        len(ask_prices) + len(bid_prices) + 1e-6
    )
    base_asset_amount_per_ask = base_asset_amount / (
        len(ask_prices) + len(bid_prices) + 1e-6
    )
    print("len(ask_prices):", len(ask_prices),"len(bid_prices):", len(bid_prices))
    print("base_asset_amount_per_bid:%.1f" % base_asset_amount_per_bid)
    print("base_asset_amount_per_ask:%.1f" % base_asset_amount_per_ask)

    print("min_position:", min_position, "max_position:", max_position)
    if min_position is not None and max_position is not None:
        print("max_position_delta_for_bid: %.1f" % (max_position - current_pos))
        print("min_position_delta_for_ask: %.1f" % (current_pos - min_position))
        available_base_asset_amount_for_bids = max(
            0, min(base_asset_amount, max_position - current_pos) / 2
        )
        available_base_asset_amount_for_asks = max(
            0, min(base_asset_amount, current_pos - min_position) / 2
        )

        if len(bid_prices):
            base_asset_amount_per_bid = available_base_asset_amount_for_bids / (
                len(bid_prices)
            )
        if len(ask_prices):
            base_asset_amount_per_ask = available_base_asset_amount_for_asks / (
                len(ask_prices)
            )
        print("available_base_asset_amount_for_bids:%.1f" % available_base_asset_amount_for_bids)
        print("available_base_asset_amount_for_asks:%.1f" % available_base_asset_amount_for_asks)
        print("base_asset_amount_per_bid adjust:%.1f" % base_asset_amount_per_bid)
        print("base_asset_amount_per_ask adjust:%.1f" % base_asset_amount_per_ask)
    
    order_params = []
    for x in bid_prices:
        bid_order_params = OrderParams(
            order_type=OrderType.Limit(),
            market_index=market_index,
            market_type=market_type,
            direction=PositionDirection.Long(),
            base_asset_amount=int(base_asset_amount_per_bid * BASE_PRECISION),
            price=int(x * PRICE_PRECISION),
            post_only=PostOnlyParams.TryPostOnly() if taker else PostOnlyParams.NONE(),
        )
        if bid_order_params.base_asset_amount > 0:
            order_params.append(bid_order_params)

    for x in ask_prices:
        ask_order_params = OrderParams(
            order_type=OrderType.Limit(),
            market_index=market_index,
            market_type=market_type,
            direction=PositionDirection.Short(),
            base_asset_amount=int(base_asset_amount_per_ask * BASE_PRECISION),
            price=int(x * PRICE_PRECISION),
            post_only=PostOnlyParams.TryPostOnly() if taker else PostOnlyParams.NONE(),
        )
        if ask_order_params.base_asset_amount > 0:
            order_params.append(ask_order_params)
    # print(order_params)
    # order_print([bid_order_params, ask_order_params], market_name)
    order_print(order_params, market_name)
    
    print("open_orders:%d len(order_params): %d" % (current_pos_raw.open_orders, len(order_params)))
    if current_pos_raw.open_orders + len(order_params) >= 30:
        print("open_orders near full:", current_pos_raw.open_orders)
        time.sleep(60)
        return
    
    place_orders_ix = drift_acct.get_place_orders_ix(order_params)
    # perp_orders_ix = [ await drift_acct.get_place_perp_order_ix(order_params[0], subaccount_id)]
    signature = (await drift_acct.send_ixs([place_orders_ix])).tx_sig
    print("tx Signature:", signature)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--keypath", type=str, required=False, default=os.environ.get("ANCHOR_WALLET")
    )
    parser.add_argument("--env", type=str, default="devnet")
    parser.add_argument("--amount", type=float, required=True)
    parser.add_argument("--market", type=str, required=True)
    parser.add_argument("--subaccount", type=int, required=False, default=0)
    parser.add_argument("--authority", type=str, required=False, default=None)
    
    parser.add_argument("--spread", type=float, required=False, default=0.005)  # $0.01
    parser.add_argument("--offset", type=float, required=False, default=0)  # $0.00
    parser.add_argument("--min-position", type=float, required=False, default=None)
    parser.add_argument("--max-position", type=float, required=False, default=None)
    parser.add_argument("--lower-price", type=float, required=False, default=None)
    parser.add_argument("--upper-price", type=float, required=False, default=None)
    parser.add_argument("--grids", type=int, required=True)
    parser.add_argument("--taker", type=bool, required=False, default=False)
    parser.add_argument("--target-pos", type=float, required=False, default=0.)

    parser.add_argument("--loop", type=int, required=False, default=0)
    args = parser.parse_args()
    
    print(args)

    # assert(args.spread > 0, 'spread must be > $0')
    # assert(args.spread+args.offset < 2000, 'Invalid offset + spread (> $2000)')

    if args.keypath is None:
        if os.environ["ANCHOR_WALLET"] is None:
            raise NotImplementedError("need to provide keypath or set ANCHOR_WALLET")
        else:
            args.keypath = os.environ["ANCHOR_WALLET"]

    if args.env == "devnet":
        url = "https://api.devnet.solana.com"
    elif args.env == "mainnet":
        # url = "https://api.mainnet-beta.solana.com"
        url = "https://node.onekey.so/sol"
    else:
        raise NotImplementedError("only devnet/mainnet env supported")
    import asyncio

    if args.loop > 0:
        while 1:
            try:
                asyncio.run(
                    main(
                        args.keypath,
                        args.env,
                        url,
                        args.subaccount,
                        args.market,
                        args.amount,
                        args.grids,
                        args.spread,
                        args.offset,
                        args.upper_price,
                        args.lower_price,
                        args.min_position,
                        args.max_position,
                        args.authority,
                        args.taker,
                        args.target_pos
                    )
                )
            except Exception as e:
                print("Exception:")
                print(e)
                time.sleep(60)
            time.sleep(args.loop)
    else:
        asyncio.run(
            main(
                args.keypath,
                args.env,
                url,
                args.subaccount,
                args.market,
                args.amount,
                args.grids,
                args.spread,
                args.offset,
                args.upper_price,
                args.lower_price,
                args.min_position,
                args.max_position,
                args.authority,
                args.taker,
                args.target_pos
            )
        )
