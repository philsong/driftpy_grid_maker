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

from driftpy.drift_client import DriftClient
from driftpy.constants.numeric_constants import BASE_PRECISION, PRICE_PRECISION, QUOTE_PRECISION

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

        if market_str is None:
            market_str = configs["mainnet"].markets[order.market_index].symbol

        print(
            str(order.direction).split(".")[-1].replace("()", ""),
            market_str,
            "@",
            pricestr,
        )


async def main(
    keypath,
    env,
    url,
    market_name,
    base_asset_amount,
    subaccount_id,
    spread=0.01,
    offset=0,
    min_position=None,
    max_position=None,
    authority=None,
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
    print('drift_user:', drift_user)
    market_index = 0
    perp_position = drift_user.get_perp_position(market_index)

    print(perp_position)
    base_asset_amount_pos = perp_position.base_asset_amount if perp_position is not None else 0

    is_long = base_asset_amount_pos > 0
    is_short = base_asset_amount_pos < 0
    
    pos = base_asset_amount_pos/BASE_PRECISION + 100
    
    offset = -1 * 0.0001 * pos / base_asset_amount
    print("pos:", pos, "offset:  %.6f" % offset)
    # offset =0 
    
    unrealized_pnl = drift_user.get_unrealized_pnl()/QUOTE_PRECISION
    print("unrealized_pnl: %.3f" % unrealized_pnl)

    # print("base_asset_amount:", base_asset_amount, "BASE_PRECISION:",BASE_PRECISION, int(base_asset_amount * BASE_PRECISION))
    default_order_params = OrderParams(
        order_type=OrderType.Limit(),
        market_type=market_type,
        direction=PositionDirection.Long(),
        user_order_id=0,
        base_asset_amount=int(base_asset_amount * BASE_PRECISION),
        price=0,
        market_index=market_index,
        reduce_only=False,
        post_only=PostOnlyParams.TryPostOnly(),
        immediate_or_cancel=False,
        trigger_price=0,
        trigger_condition=OrderTriggerCondition.Above(),
        oracle_price_offset=0,
        auction_duration=None,
        max_ts=None,
        auction_start_price=None,
        auction_end_price=None,
    )

    print("offset: %.6f" % offset, "spread:", spread)
    # print("default_order_params:", default_order_params)
    bid_order_params = copy.deepcopy(default_order_params)
    bid_order_params.direction = PositionDirection.Long()
    bid_order_params.oracle_price_offset = int((offset - spread / 2) * PRICE_PRECISION)
    # print("bid_order_params:", bid_order_params)
    
    ask_order_params = copy.deepcopy(default_order_params)
    ask_order_params.direction = PositionDirection.Short()
    ask_order_params.oracle_price_offset = int((offset + spread / 2) * PRICE_PRECISION)

    # print("ask_order_params:", ask_order_params)
    order_print([bid_order_params, ask_order_params], market_name)
    
    perp_orders_ix = []
    spot_orders_ix = []
    if is_perp:
        if pos > 50:
            perp_orders_ix = [
                drift_acct.get_place_perp_order_ix(ask_order_params, subaccount_id),
            ]
        elif pos < -50:
            perp_orders_ix = [
                drift_acct.get_place_perp_order_ix(bid_order_params, subaccount_id),
            ]
        else:
            perp_orders_ix = [
                drift_acct.get_place_perp_order_ix(bid_order_params, subaccount_id),
                drift_acct.get_place_perp_order_ix(ask_order_params, subaccount_id),
            ]
    else:
        spot_orders_ix = [
            drift_acct.get_place_spot_order_ix(bid_order_params, subaccount_id),
            drift_acct.get_place_spot_order_ix(ask_order_params, subaccount_id),
        ]

    # print("get_cancel_orders_ix:", drift_acct.get_cancel_orders_ix(sub_account_id=subaccount_id))
    # print("perp_orders_ix:", perp_orders_ix)
    # print("spot_orders_ix:", spot_orders_ix)
    signature = (await drift_acct.send_ixs(
        [
            drift_acct.get_cancel_orders_ix(sub_account_id=subaccount_id),
        ]
        + perp_orders_ix
        + spot_orders_ix
    )).tx_sig
    
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

    parser.add_argument("--spread", type=float, required=False, default=0.2)  # $0.01
    parser.add_argument("--offset", type=float, required=False, default=0)  # $0.00
    parser.add_argument("--min-position", type=float, required=False, default=None)
    parser.add_argument("--max-position", type=float, required=False, default=None)
    
    parser.add_argument("--loop", type=int, required=False, default=0)

    args = parser.parse_args()

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
        url = "https://api.mainnet-beta.solana.com"
        # url = "https://node.onekey.so/sol"
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
                        args.market,
                        args.amount,
                        args.subaccount,
                        args.spread,
                        args.offset,
                        args.min_position,
                        args.max_position,
                        args.authority,
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
                args.market,
                args.amount,
                args.subaccount,
                args.spread,
                args.offset,
                args.min_position,
                args.max_position,
                args.authority,
            )
        )