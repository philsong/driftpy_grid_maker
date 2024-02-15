export ANCHOR_WALLET="/home/ec2-user/.shiwallet.json"
python floating_maker.py --env mainnet --market SOL-PERP --min-position -50 --max-position 50  --amount 0.5 --spread 0.1 --loop 600

