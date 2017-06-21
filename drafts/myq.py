#!/bin/env python
import argparse
#import common.config
import oandaconfig
import v20
from forwardInstrument import InstrumentWrapper, PathFinder
from teeth import MovingQueue
import pdb
from myt_support import candleTime, summarize, downloads, PositionFactory
import numpy as np
from oscillators import OscillatorCalculation

parser = argparse.ArgumentParser()
parser.add_argument('--size', nargs='?', type=float, default=10000.0);
parser.add_argument("--start", nargs='?', type=float, default=5000.0)
parser.add_argument('--select', nargs='?')
parser.add_argument('--depth', nargs='?', type=int, default=20)
parser.add_argument('--drag', nargs='?', type=int, default=50)
parser.add_argument('--slice', nargs='?', default='M5')
parser.add_argument('--trigger', nargs='?', type=float, default=2.0)
parser.add_argument('--sdf', type=float, default=0.3)
parser.add_argument('--risk', nargs='?', type=float, default=1.0)
parser.add_argument('--profit', nargs='?', type=float, default=3.0)
parser.add_argument('--rsi', nargs='?', default="14:31-71")
parser.add_argument('--after', nargs='?', type=int, default=0)
parser.add_argument('--stop', nargs='?', type=int, default = 1000)
parser.add_argument('--debug', action='store_true')
parser.add_argument('--pessimist', action='store_true')
parser.add_argument('--verbose', action='store_true')

# parser.add_argument('--level', nargs='?', type=int, default=4)
args = parser.parse_args()

cfg = oandaconfig.Config()
cfg.load("~/.v20.conf")
api = v20.Context( cfg.hostname, cfg.port, token = cfg.token)

accountResp = api.account.get(cfg.active_account)
account = accountResp.get('account', '200')

rsiMaker = OscillatorCalculation(args.rsi)
posMaker = PositionFactory(50,50) if(args.pessimist) else PositionFactory(100,0)

positions = filter(lambda p: p.instrument == args.select, account.positions)
if(len(positions)>1):
    raise ValueError("api returned too many positions for the same instrument...")

avoidBUY=False
avoidSELL=False
closings = 0
# if(len(positions)==1):
#     # limit ourselves to same BUY/SELL as pre-existing
#     if(positions[0].short.units==0):
#         avoidSELL=True
#     else:
#         avoidBUY=True
#     print "Will avoid {} {} as we have an existing position...".format("BUYing" if(avoidBUY) else "SELLing", args.select)


kwargs = {}
kwargs['count'] = (args.drag+3)*args.depth
kwargs['price'] = 'BA'
kwargs['granularity'] = args.slice
resp = api.instrument.candles(args.select, **kwargs)

candles = resp.get('candles', 200)
candles.sort(lambda a,b: cmp(a.time,b.time))

queue = MovingQueue(args.depth)

pos1 = None
pos2 = None

money = args.start
print("Starting with ${0}".format(money))

for c in candles:
    queue.add(c)
    rsiMaker.add(c)
    printOK = (closings>=args.after)
    if(queue.currentSize()>=args.depth):
        spreads = map(lambda x: x.ask.o - x.bid.o, queue)
        bids = map (lambda x: x.bid.o, queue)
        asks = map (lambda x: x.ask.o, queue)
        sdev   = np.std(bids)
        mspread = np.median(spreads)
        mbid = np.median(bids)
        mask = np.median(asks)
        if(not rsiMaker.full()):
            continue

        rsi = rsiMaker.RSI
        if(pos1 is None):
            if(c.ask.o < mbid-args.trigger+mspread+args.sdf*sdev and not avoidBUY):
                if(rsi<rsiMaker.oscLow*1.05):
                    # it is low, we should buy
                    pos1 = posMaker.make(True, c,args.size, c.bid.o  - args.risk*mspread, c.ask.o+args.profit*mspread)
                    if(printOK): print("{0} -- Taking BUY position at Asking price of {1}  medians[bid={2}, 10Kspread={3}, 10Ksd={4}] RSI={5}".format(\
                                       c.time, c.ask.o, mbid,mspread*10000,sdev*10000, rsi))
                    if(args.debug): pdb.set_trace()
                else:
                    if(args.verbose): print "{0} -- BUY position not desirable with RSI={1}, though median ask={2} and current ask={3}".format(c.time, rsi, mask, c.ask.o)

            elif(c.bid.o > mask+args.trigger*mspread-args.sdf*sdev and not avoidSELL):
                if(rsi>rsiMaker.oscHigh*0.95):
                    # it is high, we should sell
                    pos1 = posMaker.make(False, c, args.size, c.ask.o + args.risk*mspread, c.bid.o-args.profit*mspread)
                    if(printOK): print ("{0} -- Taking SELL position at Bidding price {1} of  medians[bid={2}, 10Kspread={3}, 10Ksd={4}] RSI={5}".format(c.time, c.bid.o, mbid,mspread*10000,sdev*10000, rsi))
                    if(args.debug): pdb.set_trace()
                else:
                    if(args.verbose): print "{0} -- SELL position not desirable with RSI={1}, though median bid={2} and current bid={3}".format(c.time, rsi, mbid, c.bid.o)

    if(pos1 is not None):
        event,todo,benef, benefRatio = pos1.timeToClose(c, rsiMaker.isLow(), rsiMaker.isHigh())
        if(todo=='close'):
            if(printOK):
                    print( "{0} -- Closing with event {1} - with impact {2} ({4}%); RSI={3}".format(c.time, event, benef, rsi, benefRatio))
                    print("[{},{}] [{}, {}], [{},{}] [{},{}] -- {}".format(c.bid.l, c.ask.l, c.bid.o,c.ask.o,c.bid.h,c.ask.h, c.bid.c, c.ask.c, pos1.relevantPrice(c)))
            money = money + benef*args.size
            print(" ------------------------------------  Money: ${0}".format(money))
            pos1=None
            closings+=1
            if(closings>args.stop): break

print("Ending with: ${0}".format(money))
if(pos1 is not None):
    print "Take Profit: {}\tSave Loss: {}".format(pos1.takeProfit, pos1.saveLoss)
    print "Current: bid={}, ask={}".format(candles[-1].bid.o, candles[-1].ask.o)
