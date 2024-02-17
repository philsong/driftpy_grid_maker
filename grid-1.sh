export ANCHOR_WALLET="/home/ec2-user/drift/my-keypair.json"
python limit_order_grid.py --subaccount 1 --env mainnet --market SOL-PERP  --min-position -150 --max-position -50 --loop 5 --amount 200 --grids 5 --spread 0.005 --target-pos -100
