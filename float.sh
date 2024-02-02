export ANCHOR_WALLET="/home/ec2-user/drift/my-keypair.json"
python floating_maker.py --env mainnet --market SOL-PERP --min-position -150 --max-position -50 --amount 1 --spread 0.1 --loop 600 --target-pos -100

