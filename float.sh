export ANCHOR_WALLET="/home/ec2-user/drift/my-keypair.json"
python floating_maker.py --env mainnet --market SOL-PERP --min-position -250 --max-position -150 --amount 1 --spread 0.5 --loop 600 --target-pos -200

