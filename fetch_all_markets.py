import sys

sys.path.append("./driftpy/src/")
sys.path.append("./src/")
sys.path.append("../src/")

from anchorpy import Provider, Wallet
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from driftpy.drift_client import DriftClient, AccountSubscriptionConfig
import asyncio

async def get_all_market_names():
    env = 'mainnet-beta' # 'devnet'
    rpc = 'https://node.onekey.so/sol' # todo replace
    # rpc = "https://mainnet.helius-rpc.com/?api-key=3a1ca16d-e181-4755-9fe7-eac27579b48c"
    kp = Keypair() # random wallet
    wallet = Wallet(kp)
    connection = AsyncClient(rpc)
    provider = Provider(connection, wallet)
    drift_client = DriftClient(provider.connection, provider.wallet, env.split('-')[0], account_subscription=AccountSubscriptionConfig("cached"))
    
    all_perps_markets = await drift_client.program.account['PerpMarket'].all()
    sorted_all_perps_markets = sorted(all_perps_markets, key=lambda x: x.account.market_index)
    result_perp = [bytes(x.account.name).decode('utf-8').strip() for x in sorted_all_perps_markets]

    index =0 
    for x in result_perp:
        print(index, x)
        index+=1
        
    all_spot_markets = await drift_client.program.account['SpotMarket'].all()
    sorted_all_spot_markets = sorted(all_spot_markets, key=lambda x: x.account.market_index)
    result_spot = [bytes(x.account.name).decode('utf-8').strip() for x in sorted_all_spot_markets]

    result = result_perp + result_spot[1:] # ignore quote spot market index
    return result

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    answer = loop.run_until_complete(get_all_market_names())
    print(answer)
