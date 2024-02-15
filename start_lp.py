import os
import json
import copy
import sys
import time
import pprint

sys.path.append("./driftpy/src/")
sys.path.append("./src/")
sys.path.append("../src/")

from anchorpy import Wallet

from solana.rpc.async_api import AsyncClient
from solana.rpc import commitment

from solders.keypair import Keypair
from solders.pubkey import Pubkey

from driftpy.drift_client import DriftClient
from driftpy.drift_user import DriftUser
from driftpy.keypair import load_keypair

from driftpy.constants.config import configs
from driftpy.accounts import *

# todo: airdrop udsc + init account for any kp
# rn do it through UI
from driftpy.constants.numeric_constants import AMM_RESERVE_PRECISION, QUOTE_PRECISION, K_BPS_UPDATE_SCALE


async def view_logs(sig: str, connection: AsyncClient):
    connection._commitment = commitment.Confirmed
    logs = ""
    try:
        await connection.confirm_transaction(sig, commitment.Confirmed)
        logs = (await connection.get_transaction(sig))["result"]["meta"]["logMessages"]
    finally:
        connection._commitment = commitment.Processed
    pprint.pprint(logs)


async def main(
    keypath,
    env,
    url,
    market_index,
    liquidity_amount,
    operation,
):
    keypair_file = os.path.expanduser(keypath)
    keypair = load_keypair(keypair_file)
    print("using public key from keypair file:", keypair.pubkey())
    
    print("market:", market_index)
    # authority = "57BY9ciy53kHRqyFJuGDVaE56BnEWtkjLWAdpGCta2XA"  
    authority = None  
    print("authority:", authority)
    subaccount_id = 2
    print("subaccount_id:", subaccount_id)
    
    config = configs[env]
    connection = AsyncClient(url)

    drift_acct = DriftClient(
        connection,
        keypair, 
        config.env,
        authority=Pubkey.from_string(authority) if authority else None,
        active_sub_account_id = subaccount_id)
    await drift_acct.subscribe()
    
    drift_user = drift_acct.get_user()

    total_collateral = drift_user.get_total_collateral()
    print("total collateral:", total_collateral / QUOTE_PRECISION)

    if total_collateral == 0:
        print("cannot lp with 0 collateral")
        return
    
    position = drift_acct.get_perp_position(market_index)
    market = await get_perp_market_account(drift_acct.program, market_index)
    percent_provided = (position.lp_shares / market.amm.sqrt_k) * 100
    print(f"lp shares: {position.lp_shares/AMM_RESERVE_PRECISION}")
    print(f"providing {percent_provided}% of total market liquidity")
    print("operation:",operation)
    
    if operation == "add" or operation == "remove":    
        lp_amount = liquidity_amount * AMM_RESERVE_PRECISION
        lp_amount -= lp_amount % market.amm.order_step_size
        lp_amount = int(lp_amount)
        print("standardized lp amount:", lp_amount / AMM_RESERVE_PRECISION)

        if lp_amount < market.amm.order_step_size:
            print("lp amount too small - exiting...")

        print(f"{operation}ing {lp_amount} lp shares...")

    sig = None
    if operation == "add":
        resp = input("confirm adding liquidity: Y?")
        if resp != "Y":
            print("confirmation failed exiting...")
            return
        sig = await drift_acct.add_liquidity(lp_amount, market_index)
        print(sig)

    elif operation == "remove":
        resp = input("confirm removing liquidity: Y?")
        if resp != "Y":
            print("confirmation failed exiting...")
            return
        sig = await drift_acct.remove_liquidity(lp_amount, market_index)
        print(sig)

    elif operation == "view":
        pass

    elif operation == "settle":
        resp = input("confirm settling revenue to if stake: Y?")
        if resp != "Y":
            print("confirmation failed exiting...")
            return
        
        settle_pk = drift_acct.get_user_account_public_key(sub_account_id=subaccount_id)
        print("settle_pk:", settle_pk)
        sig = await drift_acct.settle_lp(settle_pk, market_index)
        print("sig:", sig)

    else:
        return

    if sig:
        print("confirming tx...")
        resp = await connection.confirm_transaction(sig)
        print("confirming tx...resp:", resp)

    position = drift_acct.get_perp_position(market_index)
    market = await get_perp_market_account(drift_acct.program, market_index)
    percent_provided = (position.lp_shares / market.amm.sqrt_k) * 100
    print(f"lp shares: {position.lp_shares/AMM_RESERVE_PRECISION}")
    print(f"providing {percent_provided}% of total market liquidity")
    print("done! :)")


if __name__ == "__main__":
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

    if args.operation == "add":
        assert args.amount is not None, "adding requires --amount"

    if args.operation == "remove" and args.amount is None:
        print("removing full IF stake")

    if args.keypath is None:
        raise NotImplementedError("need to provide keypath or set ANCHOR_WALLET")

    match args.env:
        case "devnet":
            url = "https://api.devnet.solana.com"
        case "mainnet":
            # url = "https://api.mainnet-beta.solana.com"
            url = "https://node.onekey.so/sol"
        case _:
            raise NotImplementedError("only devnet/mainnet env supported")

    import asyncio

    asyncio.run(
        main(
            args.keypath,
            args.env,
            url,
            args.market,
            args.amount,
            args.operation,
        )
    )
