#!/bin/env python
import argparse
import oandaconfig
import v20
from forwardInstrument import InstrumentWrapper, PathFinder
from teeth import MovingQueue
import pdb, time
from myt_support import candleTime, summarize, downloads, PositionFactory, frequency, queueSecretSauce
import numpy as np
from oscillators import OscillatorCalculation

parser = argparse.ArgumentParser()
parser.add_argument('--size', nargs='?', type=float, default=10000.0);
parser.add_argument("--start", nargs='?', type=float, default=5000.0)
parser.add_argument('--select', nargs='?')
parser.add_argument('--depth', nargs='?', type=int, default=20)
parser.add_argument('--drag', nargs='?', type=int, default=50)
parser.add_argument('--slice', nargs='?', default='M5/M1')
parser.add_argument('--trigger', nargs='?', type=float, default=2.0)
parser.add_argument('--risk', nargs='?', type=float, default=1.0)
parser.add_argument('--profit', nargs='?', type=float, default=3.0)
parser.add_argument('--rsi', nargs='?', default="14:31-71")
parser.add_argument('--after', nargs='?', type=int, default=0)
parser.add_argument('--stop', nargs='?', type=int, default = 1000)
parser.add_argument('--debug', action='store_true')
parser.add_argument('--pessimist', action='store_true')
parser.add_argument('--execute', action='store_true')
parser.add_argument('--random', default='none')
parser.add_argument('--sdf', default=0.3, type=float)

# parser.add_argument('--level', nargs='?', type=int, default=4)
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

pipLocation = zInstrument.pipLocation
pipFactor = 10**(pipLocation)
displayPrecision = zInstrument.displayPrecision
print (pipLocation,displayPrecision)

rsiHighMaker = OscillatorCalculation(args.rsi)
rsiLowMaker  = OscillatorCalculation(args.rsi)
posMaker = PositionFactory(50,50) if(args.pessimist) else PositionFactory(100,0)

positions = filter(lambda p: p.instrument == args.select, account.positions)

if(len(positions)>1):
    raise ValueError("api returned too many positions for the same instrument...")


pos1 = None
pos2 = None

drag = args.drag if(len(positions)==0) else 0
slicing = args.slice.split("/")


kwargsHigh = { "count": (2*args.depth), "price": "BA", "granularity": slicing[0] }
kwargsLow =  { "count": (2*args.depth), "price": "BA", "granularity": slicing[1] }

resp = api.instrument.candles(args.select, **kwargsHigh)
candlesHigh = resp.get('candles', 200)
resp = api.instrument.candles(args.select, **kwargsLow)
candlesLow= resp.get('candles', 200)



candlesHigh.sort(lambda a,b: cmp(a.time,b.time))
candlesLow.sort(lambda a,b: cmp(a.time,b.time))


closings = 0
if(len(positions)==1):
    tradeIDs = (positions[0].long.tradeIDs if(positions[0].long.tradeIDs is not None)else positions[0].short.tradeIDs)
    # pdb.set_trace()
    if(tradeIDs is not None and len(tradeIDs)>1):
        pos1 = posMaker.makeFromExistingTrade(candlesHigh[0], account, tradeIDs[0])
        if(pos1 is None):
            raise RuntimeError("Unable to find position correctly (bug?)")
        else:
            print "Found trade on the account..."

queue = MovingQueue(args.depth)

money = args.start
mspread = None
mbid = None
mask = None
sdev=None
askTrigger = None
bidTrigger = None


withRandom = args.random


skipIdenticalCandles = (lambda c1,c2:  c1.time >= c2.time)

queue.skipper = skipIdenticalCandles
rsiHighMaker.setSkipper(skipIdenticalCandles)
rsiLowMaker.setSkipper(skipIdenticalCandles)


print "Digest the higher candle data..."
for c in candlesHigh:
    queue.add(c)
    rsiHighMaker.add(c)
    if(queue.full()):
        mbid,mask, mspread, sdev, bidTrigger, askTrigger = queueSecretSauce(queue, args.trigger, args.sdf)


for c in candlesLow:
    rsiLowMaker.add(c)

print "Median Bid: {}, Ask: {}; 10Kspread: {}, spread: {} pips, sdev: {}pips ".format(mbid, mask, 10000*mspread, mspread/pipFactor, sdev/pipFactor)
print "Quiet range: bid>{} and ask<{}".format(bidTrigger,askTrigger)
print "High RSI= {}\tLow RSI={}".format(rsiHighMaker.RSI, rsiLowMaker.RSI)

loopFrequency = float(frequency(slicing[1]))
flushFrequency = float(frequency(slicing[0]))

lastPush = time.time()
kwargsHigh['count']=2
kwargsLow['count']=4

loopStart = time.time()

while(True):
    now = time.time()
    time.sleep(loopFrequency-2 if(loopFrequency>5)else(loopFrequency-1 if(loopFrequency>1)else loopFrequency))
    blip = time.time()
    resp = api.instrument.candles(args.select, **kwargsLow)
    candlesLow= resp.get('candles', 200)
    candlesLow.sort(lambda a,b: cmp(a.time,b.time))

    timeCost = time.time()-blip
    if(timeCost > 2.0):
        print "Warning - network is too slow for this {} ...".format(timeCost)

    for c in candlesLow:
        rsiLowMaker.add(c)

    print "{} -- {} -- bid: {} -- ask: {} (recent close) - RSI:{}".format(round(blip-loopStart,3), candlesLow[-1].time, candlesLow[-1].bid.c, candlesLow[-1].ask.c, rsiLowMaker.RSI)

    c = candlesLow[-1]

    rsi = rsiLowMaker.RSI
    if(pos1 is None):
        if(args.debug): pdb.set_trace()
        if((c.ask.o < askTrigger and  rsi<rsiLowMaker.oscLow*1.05) or(c.ask.o < mbid and withRandom == 'buy')):
            # it is low, we should buy
            pos1 = posMaker.make(True, c,args.size, c.bid.o  - args.risk*mspread, c.ask.o+args.profit*mspread)
            print("{0} -- Taking BUY position at Asking price of {1}  medians[bid={2}, 10Kspread={3}, spread={5}pips sd={4}pid] RSI={5}".format(\
                               c.time, c.ask.o, mbid,mspread*10000,sdev/pipFactor,mspread/pipFactor, rsi))
            if(args.debug): pdb.set_trace()
            withRandom = 'none'
        elif((c.bid.o > bidTrigger and  rsi>rsiLowMaker.oscHigh*0.95) or(c.bid.o>mask and withRandom == 'sell')):
            # it is high, we should sell
            pos1 = posMaker.make(False, c, args.size, c.ask.o + args.risk*mspread, c.bid.o-args.profit*mspread)
            print ("{0} -- Taking SELL position at Bidding price {1} of  medians[bid={2}, 10Kspread={3}, spread={6} pips, sd={4} pips] RSI={5}".format(c.time, c.ask.o, mbid,mspread*10000,sdev/pipFactor, rsi, mspread/pipFactor))
            if(args.debug): pdb.set_trace()
            withRandom = 'none'

        if(pos1 is not None and args.execute):
            tryIt = posMaker.executeTrade(api, account, args.select, pos1)
            if(tryIt is not None):
                account=tryIt[0]
                pos1 = tryIt[1]
            else:
                print("Position could not be executed because of market conditions or broker issues - or other exception")

    elif(pos1 is not None):
        event,todo,benef, benefRatio = pos1.timeToClose(c, rsiLowMaker.isLow(), rsiLowMaker.isHigh())
        if(todo=='close'):
            print( "{0} -- Expecting to Close with event {1} - with impact {2} ({4}%); RSI={3}".format(c.time, event, benef, rsi, benefRatio))
            print("[{},{}] [{}, {}], [{},{}] [{},{}] -- {}".format(c.bid.l, c.ask.l, c.bid.o,c.ask.o,c.bid.h,c.ask.h, c.bid.c, c.ask.c, pos1.relevantPrice(c)))

    if(time.time() - lastPush > 1.05*flushFrequency):
        lastPush = time.time()
        resp = api.instrument.candles(args.select, **kwargsHigh)
        candlesHigh = resp.get('candles',200)
        candlesHigh.sort(lambda a,b: cmp(a.time,b.time))

        for ch in candlesHigh:
            queue.add(ch)
            rsiHighMaker.add(ch)


        if(queue.full()):
            mbid,mask, mspread,sdev, bidTrigger, askTrigger = queueSecretSauce(queue)
        print "Median Bid: {}, Ask: {}; 10Kspread: {}, spread: {}pips, sdev={}pips".format(mbid, mask, 10000*mspread, mspread/pipFactor, sdev/pipFactor)
        print "Quiet range: bid>{} and ask<{}".format(bidTrigger,askTrigger)
        print "High RSI= {}\tLow RSI={}".format(rsiHighMaker.RSI, rsiLowMaker.RSI)
        if(pos1 is not None):
            print pos1
            print "Latest bid:{}, ask:{}".format(c.bid.o, c.ask.o)
        print "--------------------------------------------------------------------------------"

    remainder = loopFrequency - (time.time()-now)
    if(remainder>0.0):
        # print remainder
        time.sleep(1.1*remainder)
