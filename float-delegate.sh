export ANCHOR_WALLET="/home/ec2-user/drift/delegate-key.json"
python floating_maker.py --env mainnet --market SOL-PERP --min-position -300 --max-position 100 --amount 1 --spread 0.5 --loop 600 --target-pos -100 --authority 9tAoVCc48VrezYTwau1AcZ3LPfjMDU5JaugAikgsePFW 


