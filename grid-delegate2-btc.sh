export ANCHOR_WALLET="/home/ec2-user/drift/delegate-key2.json"
python limit_order_grid.py  --authority 3YsLJNp2pjxr1yc9j6b4Bm9cBePVCgVdw7Ky2DzymhJk --env mainnet --market BTC-PERP --loop 5 --target-pos 0 --min-position -2 --max-position 2 --amount 1000 --grids 5 --spread 0.005
