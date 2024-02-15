export ANCHOR_WALLET="/home/ec2-user/drift/delegate-key2.json"
python floating_maker.py --subaccount 3 --authority 4xERVrpwTaC6bpznLEUXGazFxJYJrvUziwAe2vuWB7f5 --env mainnet --market ETH-PERP --loop 600  --target-pos 0 --min-position -2 --max-position 2 --amount 0.1 --spread 10



