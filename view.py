import os
import json
import copy
import sys
import time

sys.path.append("./driftpy/src/")
sys.path.append("./src/")
sys.path.append("../src/")

from driftpy.constants.config import configs
from anchorpy import Provider
from anchorpy import Wallet
from solana.rpc.async_api import AsyncClient
from driftpy.drift_client import DriftClient
from driftpy.accounts import *
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from driftpy.math.perp_position import is_available
from driftpy.constants.numeric_constants import *

from driftpy.drift_user import DriftUser
import time
from driftpy.math.conversion import convert_to_number


async def main(
    authority,
    subaccount,
):
    env = "mainnet"
    url = "https://node.onekey.so/sol"
    # url = "http://127.0.0.1:8899"
    config = configs[env]
    wallet = Wallet(Keypair())  # throwaway
    print(url)
    print("config.default_http:", config.default_http)
    connection = AsyncClient(url)
    provider = Provider(connection, wallet)
    subaccount_id = 0
    
    # dc = DriftClient.from_config(config, provider)
    drift_acct = DriftClient(
        connection,
        wallet, 
        config.env,
        authority=Pubkey.from_string(authority) if authority else None,
        active_sub_account_id = subaccount_id)

    await drift_acct.subscribe()
        
    drift_user = drift_acct.get_user()

    from driftpy.constants.numeric_constants import QUOTE_PRECISION

    spot_collateral = drift_user.get_spot_market_asset_value(
        None,
        include_open_orders=True,
    )
    print("spot collat:", spot_collateral / QUOTE_PRECISION)

    pnl = drift_user.get_unrealized_pnl(False)
    print("pnl:", pnl / QUOTE_PRECISION)

    total_collateral = drift_user.get_total_collateral()
    print("total collateral:", total_collateral/QUOTE_PRECISION)

    perp_liability =drift_user.get_perp_market_liability(include_open_orders=True)
    spot_liability =drift_user.get_spot_market_liability_value(include_open_orders=True)
    print("perp_liability", perp_liability/QUOTE_PRECISION, "spot_liability", spot_liability/QUOTE_PRECISION)

    perp_market = drift_user.drift_client.get_perp_market_account(0)
    oracle = drift_acct.get_oracle_price_data_for_perp_market(0)
    print("oracle", oracle)
    
    oracle = convert_to_number(oracle.price)
    print("oracle price", oracle)
    
    print(
        "init leverage, main leverage:",
        MARGIN_PRECISION / perp_market.margin_ratio_initial,
        MARGIN_PRECISION / perp_market.margin_ratio_maintenance,
    )

    liq_price = drift_user.get_perp_liq_price(0)
    print("liq price", liq_price/PRICE_PRECISION)

    total_liability = drift_user.get_margin_requirement()
    total_asset_value = drift_user.get_total_collateral()
    print("total_liab", total_liability/QUOTE_PRECISION, "total_asset", total_asset_value/QUOTE_PRECISION)
    print("leverage:", (drift_user.get_leverage()) / 10_000)

    perp_positions = drift_user.get_active_perp_positions()
    print("perp positions:")
    for position in perp_positions:
        print(">", position)

    drift_acct.unsubscribe()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pubkey", type=str, required=True)
    parser.add_argument("--subacc", type=int, required=False, default=0)
    args = parser.parse_args()

    import asyncio

    s = time.time()
    asyncio.run(main(args.pubkey, args.subacc))
    print("time taken:", time.time() - s)
    print("done! :)")