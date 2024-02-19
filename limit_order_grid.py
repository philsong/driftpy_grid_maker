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

current_cancer_order_loop_count = 0

def order_print(orders: list[OrderParams], market_str=None):
    for order in orders:
        if order.price == 0:
            pricestr = "$ORACLE"
            if order.oracle_price_offset > 0:
                pricestr += " + " + str(order.oracle_price_offset / PRICE_PRECISION)
            else:
                pricestr += " - " + str(abs(order.oracle_price_offset) / PRICE_PRECISION)
        else:
            pricestr = "$" + str(order.price / PRICE_PRECISION)

        if market_str == None:
            market_str = configs["mainnet"].markets[order.market_index].symbol

        print(
            str(order.direction).split(".")[-1].replace("()", ""),
            market_str,
            "@",
            pricestr,
        )


def calculate_grid_prices(
    num_of_grids, upper_price, lower_price, current_price, spread=0.005, offset=0.0
):
    if upper_price is None and lower_price is None:
        print("calculate_grid_prices spread:", spread, "offset:%.4f" % offset, "num_of_grids:", num_of_grids)
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
        # print("calculate_grid_prices without offset: %d %.4f" % (i, price))
        price_with_offset = price*(1 + offset)
        # print("calculate_grid_prices with    offset: %d %.4f" % (i, price_with_offset))
        if price < current_price and price > lower_price:
            if price_with_offset > current_price: #avoid maker reject
                price_with_offset = current_price
            if price_with_offset < lower_price: #avoid too far away
                price_with_offset = lower_price
            bid_prices.append(price_with_offset)
        elif price > current_price and price < upper_price:
            if price_with_offset < current_price: #avoid maker reject
                price_with_offset = current_price
            if price_with_offset > upper_price: #avoid too far away
                price_with_offset = upper_price
            ask_prices.append(price_with_offset)

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
    skew=0,
    upper_price=None,
    lower_price=None,
    min_position=None,
    max_position=None,
    authority=None,
    maker=True,
    target_pos = 0,
    cancer_order_loop_count = 60,
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
            market_index = spot_market_config.market_index

    if market_index == -1:
        print("INVALID MARKET")
        return

    print("market_index:", market_index, market_name)
    
    # print("config.env:", config.env)
    wallet = Wallet(keypair)
    connection = AsyncClient(url)
    provider = Provider(connection, wallet)
    
    perp_markets = []
    if market_index not in perp_markets:
        perp_markets.append(market_index)
    spot_markets = [0, 1, 3, 4] #0 usdc, 1 sol, 3 wBTC, 4 wETH, 5 usdt

    spot_market_oracle_infos, perp_market_oracle_infos, spot_market_indexes = get_markets_and_oracles(perp_markets = perp_markets, spot_markets=spot_markets)

    oracle_infos = spot_market_oracle_infos + perp_market_oracle_infos
    drift_acct = DriftClient(
        connection,
        wallet, 
        config.env,             
        perp_market_indexes = perp_markets,
        spot_market_indexes = spot_markets,
        oracle_infos = oracle_infos,
        account_subscription = AccountSubscriptionConfig("demo"),
        authority=Pubkey.from_string(authority) if authority else None,
        active_sub_account_id = subaccount_id
    )

    await drift_acct.subscribe()
    
    drift_user = drift_acct.get_user()        

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
        
        current_pos_raw = drift_user.get_perp_position(market_index)
        print("current_pos_raw:", current_pos_raw)

        if current_pos_raw is not None:
            current_pos = current_pos_raw.base_asset_amount / float(BASE_PRECISION)
        else:
            current_pos = 0
        
        if current_pos_raw is not None:
            if current_pos_raw.open_orders >= 30:
                print("open_orders full:", current_pos_raw.open_orders)
                # time.sleep(60)
                # return

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
    
    # inspect user's leverage
    leverage = drift_user.get_leverage()
    print('current leverage:', leverage / 10_000)
    
    base_asset_amount = quote_asset_amount / current_price

    print("quote_asset_amount: %.1f" % quote_asset_amount, "base_asset_amount:%.4f" % base_asset_amount)
    
    delta_pos = current_pos - target_pos
    
    offset = -1 * skew * spread * delta_pos / base_asset_amount
    print("target_pos:", target_pos, "current_pos: %.4f" % current_pos, "delta_pos: %.4f" % delta_pos, "offset:  %.6f" % offset)
    
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
    print("base_asset_amount_per_bid:%.4f" % base_asset_amount_per_bid)
    print("base_asset_amount_per_ask:%.4f" % base_asset_amount_per_ask)

    print("min_position:", min_position, "max_position:", max_position)
    if min_position is not None and max_position is not None:
        print("max_position_delta_for_bid: %.4f" % (max_position - current_pos))
        print("min_position_delta_for_ask: %.4f" % (current_pos - min_position))
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
        print("available_base_asset_amount_for_bids:%.4f" % available_base_asset_amount_for_bids)
        print("available_base_asset_amount_for_asks:%.4f" % available_base_asset_amount_for_asks)
        print("base_asset_amount_per_bid adjust:%.4f" % base_asset_amount_per_bid)
        print("base_asset_amount_per_ask adjust:%.4f" % base_asset_amount_per_ask)
    
    order_params = []
    for x in bid_prices:
        if base_asset_amount_per_bid > 0.0005:
            bid_order_params = OrderParams(
                order_type=OrderType.Limit(),
                market_index=market_index,
                market_type=market_type,
                direction=PositionDirection.Long(),
                base_asset_amount=int(base_asset_amount_per_bid * BASE_PRECISION),
                price=int(x * PRICE_PRECISION),
                post_only=PostOnlyParams.TryPostOnly() if maker else PostOnlyParams.NONE(),
            )
            if bid_order_params.base_asset_amount*bid_order_params.price > 11*BASE_PRECISION*PRICE_PRECISION:
                order_params.append(bid_order_params)

    for x in ask_prices:
        if base_asset_amount_per_ask > 0.0005:
            ask_order_params = OrderParams(
                order_type=OrderType.Limit(),
                market_index=market_index,
                market_type=market_type,
                direction=PositionDirection.Short(),
                base_asset_amount=int(base_asset_amount_per_ask * BASE_PRECISION),
                price=int(x * PRICE_PRECISION),
                post_only=PostOnlyParams.TryPostOnly() if maker else PostOnlyParams.NONE(),
            )
            if ask_order_params.base_asset_amount*ask_order_params.price > 11*BASE_PRECISION*PRICE_PRECISION:
                order_params.append(ask_order_params)
    # print(order_params)
    # order_print([bid_order_params, ask_order_params], market_name)
    order_print(order_params, market_name)
    
    place_orders = True
    if current_pos_raw is not None:
        print("open_orders:%d len(order_params): %d" % (current_pos_raw.open_orders, len(order_params)))
        if current_pos_raw.open_orders + len(order_params) > 30:
            print("open_orders near full:", current_pos_raw.open_orders)
            place_orders = False
            # time.sleep(60)
            # return
    
    global current_cancer_order_loop_count
    print("current_cancer_order_loop_count:", current_cancer_order_loop_count, "cancer_order_loop_count:", cancer_order_loop_count)
    
    cancel_ix = None
    if current_cancer_order_loop_count > cancer_order_loop_count:
        cancel_ix = drift_acct.get_cancel_orders_ix(sub_account_id=subaccount_id)
        current_cancer_order_loop_count = 0
        print("cancel_ix:", cancel_ix)
        
    place_orders_ix = None
    if place_orders:
        place_orders_ix = drift_acct.get_place_orders_ix(order_params, subaccount_id)
    
    ixs = [cancel_ix] if cancel_ix else [] + [place_orders_ix] if place_orders_ix else []
    
    if ixs:
        sig = (await drift_acct.send_ixs(ixs)).tx_sig
        print("tx sig:", sig)
        if sig:
            print("confirming tx...")
            resp = await connection.confirm_transaction(sig)
            print("confirming tx...resp:", resp)
        
        return
    else:
        print("no action:", ixs)
        current_cancer_order_loop_count+=5
        time.sleep(60)


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
    parser.add_argument("--skew", type=float, required=False, default=0.01)  # $0.00
    parser.add_argument("--min-position", type=float, required=False, default=None)
    parser.add_argument("--max-position", type=float, required=False, default=None)
    parser.add_argument("--lower-price", type=float, required=False, default=None)
    parser.add_argument("--upper-price", type=float, required=False, default=None)
    parser.add_argument("--grids", type=int, required=True)
    parser.add_argument("--maker", type=bool, required=False, default=True)
    parser.add_argument("--target-pos", type=float, required=False, default=0.)

    parser.add_argument("--loop", type=int, required=False, default=5)
    parser.add_argument("--cancer_order_loop_count", type=int, required=False, default=60)
    
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
                    args.skew,
                    args.upper_price,
                    args.lower_price,
                    args.min_position,
                    args.max_position,
                    args.authority,
                    args.maker,
                    args.target_pos,
                    args.cancer_order_loop_count
                )
            )
            if args.loop <= 0:
                exit(0)
        except Exception as e:
            print("Exception:", e)
            import sys, traceback
            traceback.print_exc()
            # current_cancer_order_loop_count+=5
            # time.sleep(60)
            
        current_cancer_order_loop_count+=1
        time.sleep(args.loop)

