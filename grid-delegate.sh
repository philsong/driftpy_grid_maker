export ANCHOR_WALLET="/home/ec2-user/drift/delegate-key.json"
python limit_order_grid.py --env mainnet --market SOL-PERP --authority 9tAoVCc48VrezYTwau1AcZ3LPfjMDU5JaugAikgsePFW  --min-position -200 --max-position 200 --loop 5 --amount 400 --grids 5 --spread 0.005 --target-pos 0
