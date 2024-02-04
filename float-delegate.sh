export ANCHOR_WALLET="/home/ec2-user/drift/delegate-key.json"
python floating_maker.py --env mainnet --market SOL-PERP --min-position -250 --max-position -150 --amount 1 --spread 0.5 --loop 600 --target-pos -200 --authority 9tAoVCc48VrezYTwau1AcZ3LPfjMDU5JaugAikgsePFW 

