export ANCHOR_WALLET="/home/ec2-user/drift/delegate-key2.json"
python floating_maker.py --subaccount 1 --authority 4xERVrpwTaC6bpznLEUXGazFxJYJrvUziwAe2vuWB7f5 --env mainnet --market PYTH-PERP --loop 600  --target-pos 0 --min-position -5000 --max-position 5000 --amount 100 --spread 0.005



