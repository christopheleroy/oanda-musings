#!/bin/env python
import argparse
#import common.config
import oandaconfig 
import v20
from myt_support import PositionFactory


parser = argparse.ArgumentParser()
parser.add_argument('--size', nargs='?', type=float, default=1000.0);
parser.add_argument('--select', nargs='?')
parser.add_argument('--sell', action='store_true')
parser.add_argument('--sl', type=float)
parser.add_argument('--tp', type=float)


args = parser.parse_args()

cfg = oandaconfig.Config()
cfg.load("~/.v20.conf")
api = v20.Context( cfg.hostname, cfg.port, token = cfg.token)
accountResp = api.account.get(cfg.active_account)
instResp    = api.account.instruments(cfg.active_account)
account = accountResp.get('account', '200')
instruments = instResp.get('instruments','200')
selectedInstruments = filter(lambda p: p.name == args.select,instruments)
if(len(selectedInstruments)==0):
    raise ValueError("Select instrument not found for active account: " + args.select)
zInstrument = selectedInstruments[0]

kwargs = {}
kwargs['count'] = 1
kwargs['price'] = 'BA'
kwargs['granularity'] = 'S5'
resp = api.instrument.candles(args.select, **kwargs)
candles = resp.get('candles', 200)

print zInstrument
mker = PositionFactory(50,5)
# import pdb; pdb.set_trace()
pos = mker.make(not args.sell, candles[-1], args.size, args.sl, args.tp)

tryIt = mker.executeTrade(api, account, args.select, pos)
if(tryIt is not None):
    account=tryIt[0]
    pos = tryIt[1]
else:
    print("Position could not be executed because of market conditions or broker issues - or other exception")
