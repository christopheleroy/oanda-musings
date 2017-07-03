#!/bin/env python
import argparse, re, pdb, time
import oandaconfig
import v20
from forwardInstrument import InstrumentWrapper, PathFinder
from teeth import MovingQueue

from myt_support import candleTime, summarize, downloads, PositionFactory, frequency, queueSecretSauce, TradeLoop
import numpy as np
from oscillators import OscillatorCalculation

parser = argparse.ArgumentParser()
parser.add_argument('--size', nargs='?', type=float, default=1000.0,
                    help="size of the transaction in units (default 1000, which is a micro-lot in most pairs)");
parser.add_argument("--start", nargs='?', type=float, default=5000.0,
                    help="amount of money to start with for backtracking")
parser.add_argument('--select', nargs='?',
                    help="valid currency-pair")
parser.add_argument('--depth', nargs='?', type=int, default=20,
                    help="number of intervals of the high slice to be used when calculating the medians (moving median across a DEPTH window)")
parser.add_argument('--drag', nargs='?', type=int, default=50,
                    help="for backtracking, number of DEPTH-intervals of the high-slice to consider")
parser.add_argument('--slice', nargs='?', default='M5/M1',
                    help="e.g M5/M1, calculate medians on M5 (last DEPTH candles), but keep an eye on the market based on M1. The first is called the high-slice must always be slower than the 2nd, which we call the low-slice, 'or else'... ")
parser.add_argument('--trigger', nargs='?', type=float, default=2.0,
                    help="multiple of median-spread for the bid/ask to be above/below of median bid/ask to consider opening a sell/buy trade (but see also --rsi and --random)")
parser.add_argument('--risk', nargs='?', type=float, default=1.0,
                    help="stop-loss, as a multiple of median-spread")
parser.add_argument('--profit', nargs='?', type=float, default=3.0,
                    help="take-profit, as a multiple of median-spread")
parser.add_argument('--trail', nargs='?', default='2:3')
parser.add_argument('--rsi', nargs='?', default="14:31-71",
                    help="RSI pattern, e.g 14:35-75, means use 14 interval to compute RSI and consider oversold when < 35 and overbought>=75)")
parser.add_argument('--after', nargs='?', type=int, default=0)
parser.add_argument('--stop', nargs='?', type=int, default = 1000)
parser.add_argument('--debug', action='store_true')
parser.add_argument('--pessimist', action='store_true',
                    help="when estimating openingn or closing prices, assume you close in a disadvantageous positoin between the open value and the more extreme value in the candle where you estimate you'll close, otherwise, estimate on the opening price inthe candle")
parser.add_argument('--execute', action='store_true',
                    help='flag to confirm you want orders to be executed')
parser.add_argument('--random', default='none',
                    help='(debug purposes) pass "buy" or "sell", for random buy, the buy will be triggered as soon as ASK is below median Ask and regardless of RSI')
parser.add_argument('--sdf', default=0.3, type=float,
                    help="the weight of the standard deviation of bid around median bid in calculating how much we differ from median bid or median ask, when computing the trigger point (default 0.3)")
parser.add_argument('--bf', default=20, type=float,
                    help="frequency of displaying the 'banner', ever n times the tick is displayed")
# parser.add_argument('--bt', action='store_true',
#                     help="turns back-track on")

# parser.add_argument('--level', nargs='?', type=int, default=4)
args = parser.parse_args()

rsiHighMaker = OscillatorCalculation(args.rsi)
rsiLowMaker  = OscillatorCalculation(args.rsi)
posMaker = PositionFactory(50,50) if(args.pessimist) else PositionFactory(100,0)

trailStart = 0
trailDistance=0

if(args.trail != 'none'):
    mm = re.match(r"(\d+\.?\d*):(\d+\.?\d*)", args.trail)
    if(mm is None):
        raise ValueError("parameter --trail must be n:p, numerics where n<p")
    else:
        mm_n = float(mm.groups()[0])
        mm_p = float(mm.groups()[1])
        if(mm_n < mm_p):
            trailStart = mm_n/mm_p
            trailDistance=1.0/mm_p
        else:
            raise ValueError("parameter --trail must be n:p, numerics where n<p; and n>1.0 is very advisable")







cfg = oandaconfig.Config()
cfg.load("~/.v20.conf")
api = v20.Context( cfg.hostname, cfg.port, token = cfg.token)

looper = TradeLoop(api, cfg.active_account, args.select, 200*1000.0)
looper.initialize(posMaker)

def getSortedCandles(loopr, kwargs):
    candles = loopr.api.instrument.candles(loopr.instrumentName, **kwargs).get('candles',200)
    candles.sort(lambda a,b: cmp(a.time, b.time))
    return candles


pipFactor = looper.pipFactor

pos1 = None;pos1Id=None
pos2 = None;pos2Id=None


def RefreshPositions():
    looper.refreshPositions(posMaker)
    xpos1=None;xpos2=None;xpos1Id=None;xpos2Id=None
    if(len(looper.positions)>0):
        xpos1 = looper.positions[0]
        xpos1Id = xpos1.tradeID
        if(trailDistance>0.0): xpos1.calibrateTrailingStopLossDesire(trailStart, trailDistance)
        if(len(looper.positions)>1):
            xpos2 = looper.positions[1]
            xpos2Id = xpos2.tradeID
    return (xpos1,xpos1Id,xpos2,xpos2Id)

pos1,pos1Id,pos2,pos2Id = RefreshPositions()
drag = args.drag if(pos1 is None) else 0
slicing = args.slice.split("/")


kwargsHigh = { "count": (2*args.depth), "price": "BA", "granularity": slicing[0] }
kwargsLow =  { "count": (2*args.depth), "price": "BA", "granularity": slicing[1] }

candlesHigh = getSortedCandles(looper, kwargsHigh)
candlesLow  = getSortedCandles(looper, kwargsLow)


closings = 0
# if(len(positions)==1):
#     tradeIDs = (positions[0].long.tradeIDs if(positions[0].long.tradeIDs is not None)else positions[0].short.tradeIDs)
#     pdb.set_trace()
#     if(tradeIDs is not None and len(tradeIDs)>0):
#         pos1 = posMaker.makeFromExistingTrade(candlesHigh[0], looper.account, tradeIDs[0])
#         if(pos1 is None):
#             raise RuntimeError("Unable to find position correctly (bug?)")
#         else:
#             pos1Id = tradeIDs[0]
#             print "Found trade on the account..."

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
    maxlen=max(len(bidc), len(askc))
    base = ""
    baseL = 0
    for l in range(maxlen):
        if(bidc[0:l] == askc[0:l]):
            base = bidc[0:l]
            baseL=l
        else:
            base = base + "*"

    bidc=list(bidc)
    askc=list(askc)
    for l in range(len(bidc)):
        bidc[l] = " " if(l<baseL-1) else bidc[l]
    for l in range(len(askc)):
        askc[l] = " " if(l<baseL-1) else askc[l]

    bidc="".join(bidc)
    askc="".join(askc)

    while(len(bidc)<maxlen): bidc += "0"
    while(len(askc)<maxlen): askc += "0"

    return msg.format(base, bidc,askc)


def PrintCurrentRead(deltaTime, currentCandle,rsi):

    bidc = currentCandle.bid.c
    askc = currentCandle.ask.c

    position = "(none)"
    if(pos1 is not None):
        position = "[BUY]" if(pos1.forBUY) else "[SELL]"

    print "{} -- {} -- {} (recent close) - RSI:{} -{}".format(round(deltaTime,1), currentCandle.time[0:19], \
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

# v20.errors.V20Timeout

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
            pos1 = posMaker.make(True, c,args.size, c.bid.o  - args.risk*mspread, c.ask.o+args.profit*mspread, trailStart*args.profit*mspread+c.ask.o, trailDistance*mspread*args.profit)
            print("{0} -- Taking BUY position at Asking price of {1}  medians[bid={2}, 10Kspread={3}, spread={5}pips sd={4}pid] RSI={5}".format(\
                               c.time, c.ask.o, mbid,mspread*10000,sdev/pipFactor,mspread/pipFactor, rsi))
            if(args.debug): pdb.set_trace()
            withRandom = 'none'
        elif((c.bid.o > bidTrigger and  rsi>rsiLowMaker.oscHigh*0.95) or(c.bid.o>mask and withRandom == 'sell')):
            # it is high (and rsi is close to overbought), we should sell
            pos1 = posMaker.make(False, c, args.size, c.ask.o + args.risk*mspread, c.bid.o-args.profit*mspread, c.bid.o-trailStart*mspread*args.profit, trailDistance*mspread*args.profit)
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
            #if(args.execute): pdb.set_trace()
            print( "{0} -- Expecting to Close with event {1} - with impact {2} ({4}%); RSI={3}".format(c.time, event, benef, rsi, benefRatio))
            print("[{},{}] [{}, {}], [{},{}] [{},{}] -- {}".format(c.bid.l, c.ask.l, c.bid.o,c.ask.o,c.bid.h,c.ask.h, c.bid.c, c.ask.c, pos1.relevantPrice(c)))
            if(args.execute):
                looper.refresh(True)
                pos1,pos1Id,pos2,pos2Id = RefreshPositions()
        elif(todo=='trailing-stop'):
            print("{} --Time to set trailing stop".format(c.time))
            if(args.execute):
                posMaker.executeTrailingStop(looper,pos1)
                pos1,pos1Id,pos2,pos2Id = RefreshPositions()
        elif(todo=='trailing-update'):
            print "{} -- time to advance trailing stop".format(c.time)
            pos1.updateTrailingStop(c)



    if(time.time() - lastPush > 1.05*flushFrequency):
        lastPush = time.time()
        candlesHigh = getSortedCandles(looper, kwargsHigh)

        for ch in candlesHigh:
            queue.add(ch)
            rsiHighMaker.add(ch)


        if(queue.full()):
            mbid,mask, mspread,sdev, bidTrigger, askTrigger = queueSecretSauce(queue)
        PrintCurrentStats()
        pos1,pos1Id,pos2,pos2Id = RefreshPositions()
        if(pos1 is not None):
            print pos1
            print "Latest bid:{}, ask:{}".format(c.bid.o, c.ask.o)
        print "--------------------------------------------------------------------------------"

    remainder = loopFrequency - (time.time()-now)
    if(remainder>0.0):
        # print remainder
        time.sleep(1.1*remainder)
