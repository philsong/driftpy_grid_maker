import os
import json
import copy
import sys
import time
import pprint

sys.path.append("./driftpy/src/")
sys.path.append("./src/")
sys.path.append("../src/")

import driftpy
print(driftpy.__path__)

from driftpy.constants.config import configs
from anchorpy import Provider
import json 
from anchorpy import Wallet
from solana.rpc.async_api import AsyncClient
from driftpy.drift_client import DriftClient
from driftpy.accounts import get_user_account,get_perp_market_account
from driftpy.accounts.bulk_account_loader import BulkAccountLoader
from dataclasses import asdict

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from driftpy.keypair import load_keypair
from driftpy.account_subscription_config import AccountSubscriptionConfig
from driftpy.constants.numeric_constants import *


import asyncio

async def main():
    global summary_data

    import argparse
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--keypath", type=str, required=False, default=os.environ.get("ANCHOR_WALLET")
    )
    parser.add_argument("--env", type=str, default="devnet")
    parser.add_argument("--amount", type=float, required=False)
    parser.add_argument("--market", type=int, required=True)
    parser.add_argument(
        "--operation", choices=["remove", "add", "view", "settle"], required=True
    )
    args = parser.parse_args()
    
    keypair_file = os.path.expanduser(args.keypath)
    keypair = load_keypair(keypair_file)
    print("using public key from keypair file:", keypair.pubkey())

    config = configs['mainnet']
    url = "https://node.onekey.so/sol"
    # url = "https://api.mainnet-beta.solana.com"
    connection = AsyncClient(url)
    
    authority = None  
    print("authority:", authority)
    subaccount_id = 2
    print("subaccount_id:", subaccount_id)

    drift_acct = DriftClient(
        connection,
        keypair, 
        config.env,
        # account_subscription = AccountSubscriptionConfig("polling", BulkAccountLoader(connection)),
        active_sub_account_id = subaccount_id)

    await drift_acct.subscribe()

    settle_pk = drift_acct.authority

    while True: 
        
        # market = await get_perp_market_account(
        #     drift_acct.program, 0 
        # )
        
        # print("market:", market)
        # print('lp position:', market.amm.base_asset_amount_per_lp, market.amm.quote_asset_amount_per_lp)
        
        drift_user = drift_acct.get_user()
        perp_positions = drift_user.get_active_perp_positions()
        print("perp positions:")
        for position in perp_positions:
            print(">", position)
            print('lp_shares:', position.lp_shares/AMM_RESERVE_PRECISION)
        
        # _settle_pk = settle_pk
        settle_pk = drift_acct.get_user_account_public_key(sub_account_id=subaccount_id)
        print("settle_pk:", settle_pk)
        # user = await get_user_account(
        #     drift_acct.program, 
        #     settle_pk,
        # )
        
        # print('user....:', user)

        # position = user.spot_positions[0]
        # print('spot_positions:', position)
        # position = user.perp_positions[0]
        # print('lp_shares:', position.lp_shares/AMM_RESERVE_PRECISION)

        summary_data.append(
            asdict(position)
        )

        await asyncio.sleep(10)
        print("_--------------------------------------------------------------------------------------------_-")
        
        print('settling...', settle_pk)
        # tx = await drift_acct.settle_lp(
        #     settle_pk, 
        #     0
        # )
        # print(tx)
        
        await asyncio.sleep(60)
        drift_acct.unsubscribe()
        break
summary_data = []
try:
    asyncio.run(main())
finally:
    import pandas as pd 
    df = pd.DataFrame(summary_data)
    df.to_csv("lp_summary_bot.csv", index=False)
    