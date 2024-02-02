export ANCHOR_WALLET="/home/ec2-user/drift/delegate-key.json"
python floating_maker.py --env mainnet --market SOL-PERP --min-position -150 --max-position -50 --amount 1 --spread 0.1 --loop 600 --target-pos -100 --authority 9tAoVCc48VrezYTwau1AcZ3LPfjMDU5JaugAikgsePFW 

