export ANCHOR_WALLET="/home/ec2-user/drift/my-keypair.json"
python limit_order_grid.py --env mainnet --market SOL-PERP  --min-position -200 --max-position 200 --loop 5 --amount 400 --grids 5 --spread 0.005 --target-pos 0
