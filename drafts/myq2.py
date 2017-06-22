#!/bin/env python
import argparse
import oandaconfig
import v20
from forwardInstrument import InstrumentWrapper, PathFinder
from teeth import MovingQueue
import pdb, time
from myt_support import candleTime, summarize, downloads, PositionFactory, frequency, queueSecretSauce, TradeLoop
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
parser.add_argument('--bf', default=20, type=float)

# parser.add_argument('--level', nargs='?', type=int, default=4)
args = parser.parse_args()

cfg = oandaconfig.Config()
cfg.load("~/.v20.conf")
api = v20.Context( cfg.hostname, cfg.port, token = cfg.token)

looper = TradeLoop(api, cfg.active_account, args.select, 200*1000.0)
looper.initialize()

def getSortedCandles(loopr, kwargs):
    candles = loopr.api.instrument.candles(loopr.instrumentName, **kwargs).get('candles',200)
    candles.sort(lambda a,b: cmp(a.time, b.time))
    return candles


pipFactor = looper.pipFactor

rsiHighMaker = OscillatorCalculation(args.rsi)
rsiLowMaker  = OscillatorCalculation(args.rsi)
posMaker = PositionFactory(50,50) if(args.pessimist) else PositionFactory(100,0)

positions = looper.findPositionsRaw()
if(len(positions)>1):
    raise ValueError("api returned too many positions for the same instrument...")


pos1 = None;pos1Id=None
pos2 = None;pos2Id=None

drag = args.drag if(len(positions)==0) else 0
slicing = args.slice.split("/")


kwargsHigh = { "count": (2*args.depth), "price": "BA", "granularity": slicing[0] }
kwargsLow =  { "count": (2*args.depth), "price": "BA", "granularity": slicing[1] }

candlesHigh = getSortedCandles(looper, kwargsHigh)
candlesLow  = getSortedCandles(looper, kwargsLow)


closings = 0
if(len(positions)==1):
    tradeIDs = (positions[0].long.tradeIDs if(positions[0].long.tradeIDs is not None)else positions[0].short.tradeIDs)
    # pdb.set_trace()
    if(tradeIDs is not None and len(tradeIDs)>0):
        pos1 = posMaker.makeFromExistingTrade(candlesHigh[0], looper.account, tradeIDs[0])
        if(pos1 is None):
            raise RuntimeError("Unable to find position correctly (bug?)")
        else:
            pos1Id = tradeIDs[0]
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


def PrintCurrentStats():
    if(not queue.full()):
        print "[no banner: queue is not full]"
        return
    bt = round(bidTrigger, looper.displayPrecision);at=round(askTrigger, looper.displayPrecision)
    print "Intrument: {}".format(looper.instrumentName)
    print "Median Bid: {}, Ask: {}; 10Kspread: {}, spread: {} pips, sdev: {}pips ".format(mbid, mask, 10000*mspread, mspread/pipFactor, sdev/pipFactor)
    print "Quiet range: "+ formatTwoNumberWith("base: {} - bid>{} or ask<{}",bt,at)
    print "High RSI= {}\tLow RSI={}".format(rsiHighMaker.RSI, rsiLowMaker.RSI)
    if(pos1 is not None):
        print "{} - {}".format(pos1, pos1Id)


def formatTwoNumberWith(msg, bidc, askc):
    bidc = str(bidc)
    askc = str(askc)
    base = ""
    baseL = 0
    for l in range(len(bidc)):
        if(bidc[0:l] == askc[0:l]):
            base = bidc[0:l]
            baseL=l
        else:
            base = base + "*"

    bidc=list(bidc)
    askc=list(askc)
    for l in range(len(bidc)):
        bidc[l] = " " if(l<baseL) else bidc[l]
    for l in range(len(askc)):
        askc[l] = " " if(l<baseL) else askc[l]

    bidc="".join(bidc)
    askc="".join(askc)
    maxlen=max(len(bidc), len(askc))
    while(len(bidc)<maxlen): bidc += "0"
    while(len(askc)<maxlen): askc += "0"

    return msg.format(base, bidc,askc)


def PrintCurrentRead(deltaTime, currentCandle,rsi):

    bidc = currentCandle.bid.c
    askc = currentCandle.ask.c

    position = "(none)"
    if(pos1 is not None):
        position = "[BUY]" if(pos1.forBUY) else "[SELL]"

    print "{} -- {} -- {} (recent close) - RSI:{} -{}".format(round(deltaTime,1), currentCandle.time[0:15], \
       formatTwoNumberWith("base:{} -- bid:{} -- ask:{}",bidc,askc), rsiLowMaker.RSI, position)
    # print "{} -- {} -- base: {} --  bid: {} -- ask: {} (recent close) - RSI:{}".format(round(deltaTime,1), currentCandle.time[0:15], base, currentCandle.bid.c,currentCandle.ask.c, rsiLowMaker.RSI)




print "Digest the higher candle data..."
for c in candlesHigh:
    queue.add(c)
    rsiHighMaker.add(c)
    if(queue.full()):
        mbid,mask, mspread, sdev, bidTrigger, askTrigger = queueSecretSauce(queue, args.trigger, args.sdf)


for c in candlesLow:
    rsiLowMaker.add(c)



PrintCurrentStats()

loopFrequency = float(frequency(slicing[1]))
flushFrequency = float(frequency(slicing[0]))

lastPush = time.time()
kwargsHigh['count']=2
kwargsLow['count']=4

loopStart = time.time()
tradeErrorMax = 10
tradeErrorSleep = 600
tradeErrorCount = 0
lastBanner = 1

while(True):
    now = time.time()
    time.sleep(loopFrequency-2 if(loopFrequency>5)else(loopFrequency-1 if(loopFrequency>1)else loopFrequency))
    looper.refresh()
    blip = time.time()
    candlesLow = getSortedCandles(looper, kwargsLow)

    timeCost = time.time()-blip
    if(timeCost > 2.0):
        print "Warning - network is too slow for this {} ...".format(timeCost)

    for c in candlesLow:
        rsiLowMaker.add(c)

    # print "{} -- {} -- bid: {} -- ask: {} (recent close) - RSI:{}".format(round(blip-loopStart,1), candlesLow[-1].time, candlesLow[-1].bid.c, candlesLow[-1].ask.c, rsiLowMaker.RSI)
    PrintCurrentRead(blip-loopStart, candlesLow[-1], rsiLowMaker.RSI)
    if(lastBanner>args.bf):
        PrintCurrentStats()
        lastBanner=0
    lastBanner+=1

    c = candlesLow[-1]

    rsi = rsiLowMaker.RSI
    if(pos1 is None):
        if(args.debug): pdb.set_trace()
        if((c.ask.o < askTrigger and  rsi<rsiLowMaker.oscLow*1.05) or(c.ask.o < mbid and withRandom == 'buy')):
            # it is low (and rsi is close to oversold), we should buy
            pos1 = posMaker.make(True, c,args.size, c.bid.o  - args.risk*mspread, c.ask.o+args.profit*mspread)
            print("{0} -- Taking BUY position at Asking price of {1}  medians[bid={2}, 10Kspread={3}, spread={5}pips sd={4}pid] RSI={5}".format(\
                               c.time, c.ask.o, mbid,mspread*10000,sdev/pipFactor,mspread/pipFactor, rsi))
            if(args.debug): pdb.set_trace()
            withRandom = 'none'
        elif((c.bid.o > bidTrigger and  rsi>rsiLowMaker.oscHigh*0.95) or(c.bid.o>mask and withRandom == 'sell')):
            # it is high (and rsi is close to overbought), we should sell
            pos1 = posMaker.make(False, c, args.size, c.ask.o + args.risk*mspread, c.bid.o-args.profit*mspread)
            print ("{0} -- Taking SELL position at Bidding price {1} of  medians[bid={2}, 10Kspread={3}, spread={6} pips, sd={4} pips] RSI={5}".format(c.time, c.ask.o, mbid,mspread*10000,sdev/pipFactor, rsi, mspread/pipFactor))
            if(args.debug): pdb.set_trace()
            withRandom = 'none'

        if(pos1 is not None and pos1Id is None and args.execute):
            tryIt = posMaker.executeTrade(looper, pos1)
            if(tryIt is not None):
                pos1   = tryIt[0]
                pos1Id = tryIt[1]
            else:
                print("Position could not be executed because of market conditions or broker issues - or other exception")
                tradeErrorCount+=1
                if(tradeErrorCount % tradeErrorMax == 0):
                    print "Pausing {} seconds because of too many trade errors".format(tradeErrorSleep)
                    time.sleep(tradeErrorSleep)

    elif(pos1 is not None):
        event,todo,benef, benefRatio = pos1.timeToClose(c, rsiLowMaker.isLow(), rsiLowMaker.isHigh())
        if(todo=='close'):
            if(args.execute): pdb.set_trace()
            print( "{0} -- Expecting to Close with event {1} - with impact {2} ({4}%); RSI={3}".format(c.time, event, benef, rsi, benefRatio))
            print("[{},{}] [{}, {}], [{},{}] [{},{}] -- {}".format(c.bid.l, c.ask.l, c.bid.o,c.ask.o,c.bid.h,c.ask.h, c.bid.c, c.ask.c, pos1.relevantPrice(c)))

    if(time.time() - lastPush > 1.05*flushFrequency):
        lastPush = time.time()
        candlesHigh = getSortedCandles(looper, kwargsHigh)

        for ch in candlesHigh:
            queue.add(ch)
            rsiHighMaker.add(ch)


        if(queue.full()):
            mbid,mask, mspread,sdev, bidTrigger, askTrigger = queueSecretSauce(queue)
        PrintCurrentStats()
        if(pos1 is not None):
            print pos1
            print "Latest bid:{}, ask:{}".format(c.bid.o, c.ask.o)
        print "--------------------------------------------------------------------------------"

    remainder = loopFrequency - (time.time()-now)
    if(remainder>0.0):
        # print remainder
        time.sleep(1.1*remainder)
