export ANCHOR_WALLET="/home/ec2-user/.shiwallet.json"
python limit_order_grid.py --env mainnet --market SOL-PERP  --min-position -50 --max-position 50 --loop 5 --amount 100 --grids 5 --spread 0.005 --target-pos 0
