
import argparse, re, pdb, time, logging
import oandaconfig
import v20

import Alfred
from myt_support import TradeLoop, trailSpecsFromStringParam, PositionFactory, \
                         getSortedCandles, getBacktrackingCandles, getCachedBacktrackingCandles, getLiveCandles

## Setting PARAMETER PARSING:
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
parser.add_argument('--invert', action='store_true',
                    help="invert the logic on trigger/sdf for when to elect to take a position")
parser.add_argument('--trail', nargs='?', default='1:7,2:4,3:3,5:2,10:1',
                    help="specify the trailing-stop approache (warning: there is a default value, so better specify this parameter)")
parser.add_argument('--rsi', nargs='?', default="14:31-71",
                    help="RSI pattern, e.g 14:35-75, means use 14 intervals to compute RSI and consider oversold when < 35 and overbought>=75)")
parser.add_argument('--after', nargs='?', type=int, default=0)
parser.add_argument('--stop', nargs='?', type=int, default = 1000)
parser.add_argument('--debug', action='store_true')
parser.add_argument('--pessimist', action='store_true',
                    help="when estimating opening or closing prices, assume you close in a disadvantageous position between the open value and the more extreme value in the candle where you estimate you'll close, otherwise, estimate on the opening price in the candle")
parser.add_argument('--execute', action='store_true',
                    help='flag to confirm you want orders to be executed')

parser.add_argument('--sdf', default=0.3, type=float,
                    help="the weight of the standard deviation of bid around median bid in calculating how much we differ from median bid or median ask, when computing the trigger point (default 0.3)")
parser.add_argument('--bf', default=20, type=float,
                    help="frequency of displaying the 'banner', ever n times the tick is displayed")
parser.add_argument('--trace', action='store_true')
parser.add_argument('--dir', type=str, help='candle-cache directory')
parser.add_argument('--since', type=str, help="start simulation then, as RFC3339")
parser.add_argument('--till', type=str, help="end simulation then, as RFC3339")
parser.add_argument('--loglevel', type=int)
parser.add_argument('--instruments', action='store_true', help="force using cached-instrument definitions (use only with option --dir)")
parser.add_argument('--insurance', help='Risk-Management specs for 2nd, 3rd or n-th trade to counter risk of first position')
parser.add_argument('--msm', type=float, default=20, help="Max Size Multiple: maximum number of multiple of starting size for total engaged size, when insurance kicks in. eg. with a 2x insurance and size 1000, the msm of 20 will prevent taking positions totaling a size above 20000")
parser.add_argument('--rrsi', choices=("ok","normal","inverted"), default="normal",
                      help='whether or how to consider RSI when deciding to take a risk-management position')
parser.add_argument('--hourly', action='store_true', help='to display money progress on an hourly basis instead of daily')
parser.add_argument('--rsimode', default="+", choices=("+", "0","-"), help="whether and how to consider RSI when deciding to take an initial position")
parser.add_argument('--nzd', action='store_true', help='avoid the hourly/daily log of money amount if no difference')
parser.add_argument('--tzt', action='store_true', help='check on candle stream timing (will do nothing eventually)')
parser.add_argument('--hal', action='store_true', help='not lowAheadOfHigh or highAheadOfLow - see getCachedBacktrackingCandles')

## Parse Arguments
args = parser.parse_args()

# Adjust log levels
if(args.loglevel is not None):
    logging.basicConfig(level=args.loglevel)

def hourlydaily(lastTime,helloTime):
    if(args.hourly):
        return lastTime[:13] != helloTime[:13]
    return lastTime[:11] != helloTime[:11]

# Environment and Robot Set-Up
money = args.start
slices = args.slice.split("/")
trailSpecs = trailSpecsFromStringParam(args.trail)

cfg = oandaconfig.Config()
cfg.load("~/.v20.conf")
api = v20.Context( cfg.hostname, cfg.port, token = cfg.token)
posMaker = PositionFactory(50,50) if(args.pessimist) else PositionFactory(100,0)
looper = TradeLoop(api, cfg.active_account, args.select, 200*1000.0)
# Initialize looper / robot - handle caching if requested
if(args.instruments):
    from candlecache import findInstrument
    instDict  = findInstrument(args.dir, args.select)
    if(instDict is None):
        raise ValueError("instrument is not found in the cache...")
    looper.initialize(posMaker, instDict)
else:
    looper.initialize(posMaker)

# pm may be used to invert the profit/sdf strategy - just to check in backtracking
pm = -1 if(args.invert) else 1

robot = Alfred.TradeStrategy(args.trigger*pm, args.profit, args.risk,
               args.depth, args.select, args.size,
               slices[0], slices[1],
               args.rsi, args.sdf*pm, trailSpecs)

# set the simulation booleans
robot.simulation  = not args.execute
looper.simulation = robot.simulation

robot.initialize()
robot.rsiMode = args.rsimode
if(args.insurance):
    robot.riskManagement = Alfred.RiskManagementStrategy.parse(args.insurance)
    robot.maxEngagedSize = args.msm * args.size
    logging.info("Risk Managment: {} specs parsed, max engage size will be : {}".format(len(robot.riskManagement), robot.maxEngagedSize))
    if(args.rrsi == 'ok'):
        logging.info("Risk Management will have 'rsiAlwaysOK' set to True")
        for rm in robot.riskManagement: rm.rsiAlwaysOK = True
    elif(args.rrsi=='inverted'):
        logging.info("Risk Management will have rsiInverted set to True")
        for rm in robot.riskManagement: rm.rsiInverted = True

counts = {}


dataset =  None
if(args.execute):
    dataset = getLiveCandles(looper, args.depth+1, slices[0], slices[1])
elif(args.dir is None):
    dataset = getBacktrackingCandles(looper, args.depth*args.drag, slices[0], slices[1], lowAheadOfHigh = not args.hal)
else:
    def extOnModel(ts, tsm):
        """ if since/till are only partial specs, we expand to meaningful specifications from a model"""
        if(ts is not None and len(ts)<len(tsm)):
            return ts + tsm[ len(ts): ]
        return ts

    sinceModel = "XXXX-01-01T00:00:00.000000000Z"
    tillModel  = "XXXX-12-31T23:59:59.999999999Z"
    if(len(args.since)<4 or (args.till is not None and len(args.till) < 4)):
        raise ValueError("since / till parameters must be at least 4 characters of a RFC3339 string")
    dataset = getCachedBacktrackingCandles(looper, args.dir,slices[0], slices[1], extOnModel(args.since, sinceModel), extOnModel(args.till, tillModel), lowAheadOfHigh = not args.hal)

# adding quick way to check on order of candles
if(args.tzt):
    import  pdb; pdb.set_trace()
    for pq in dataset:
        tt = []
        for x in pq[1]:
            zz = "*" if (x.complete) else "!"
            print "> {} -- {} {}".format(x.time[10:19], time.time(), zz)
            tt.append(x.time[10:19] + zz);
        print "; ".join(tt)
        pq0 = pq[0].next() if(args.execute) else pq[0]
        print ">> high: {} --- {} {}".format(pq0.time, time.time(), ("*" if(pq0.complete)else "!"))
    import sys
    sys.exit(99)



firstTime = "??" #dataset[0][0].time
lastTime = firstTime
helloTime = firstTime
helloMoney = money
logging.critical("{} - MONEY: {} - Diff: {}".format(helloTime, helloMoney, 0.0))

for d in dataset:
    highCandle = d[0]
    lowCandles = d[1]

    for c in lowCandles:
        lastTime = c.time
        if(hourlydaily(lastTime, helloTime) and (helloMoney != money or not args.nzd)):
            logging.critical("{} - MONEY: {} - Diff: {}".format(lastTime, money, money - helloMoney))
            helloMoney = money
            helloTime = lastTime

        robot.digestLowCandle(c)
        #print(c)
        decisions = robot.decision(looper, posMaker)
        for dec in decisions:
            event,todo,benef,benefRatio,rsi,pos1 = dec

            if(todo == "take-position"):
                pos1.calibrateTrailingStopLossDesireForSteppedSpecs(c,trailSpecs, robot.mspread, looper.instrument.minimumTrailingStopDistance)
                if(args.execute):
                    tryIt = posMaker.executeTrade(looper, pos1)
                    if(tryIt is not None):
                        logging.warning("Info position taken with id={}: {}".format(tryIt[1], tryIt[0]))
                    else:
                        logging.critical("Unable to take position {} for various reasons".format(pos1))
                else:
                    looper.positions.append(pos1)
            elif(todo=='close'):
                logging.warning( "{0} -- Expecting to Close with event {1} - with impact {2} ({4}%); size={5}; RSI={3}".format(c.time,
                                   event, benef, round(rsi,2), round(benefRatio,2), pos1.size))
                # print("[{},{}] [{}, {}], [{},{}] [{},{}] -- {}".format(c.bid.l, c.ask.l, c.bid.o,c.ask.o,c.bid.h,c.ask.h, c.bid.c, c.ask.c, pos1.relevantPrice(c))
                tag = ("BUY " if(pos1.forBUY)else "SELL") + " - " + (event+"        ")[0:15] + " - " + ("gain" if(benef>0)else("loss"))
                counts[tag] = 1+ (counts[tag] if(counts.has_key(tag))else 0)
                if(args.execute):
                    looper.refresh(True)
                else:
                    money += benef*pos1.size
                    pos1Time,beforeCount = pos1.entryQuote.time, len(looper.positions)
                    looper.positions = filter(lambda p: p.entryQuote.time != pos1Time, looper.positions)
                    if(len(looper.positions) != beforeCount-1):
                        raise RuntimeError("failure/bug in removing expected closed position")
                    logging.warning("Money: {}".format(money))

            elif(todo=='trailing-stop'):
                logging.info("{} --Time to set trailing stop - {}".format(c.time,pos1.relevantPrice(c)))
                if(args.execute):
                    posMaker.executeTrailingStop(looper,pos1)
                    looper.refresh(True)
                else:
                    pos1.setTrailingStop(c)
                    logging.debug( pos1 )

            elif(todo=='trailing-progress'):
                logging.info("{} -- time to advance trailing stop value - {}".format(c.time, pos1.relevantPrice(c)))
                if(args.execute):
                    looper.refresh(True)
                else:
                    pos1.updateTrailingStopValue(c)
                    logging.debug( pos1 )

            elif(todo=='trailing-update'):
                logging.info("{} -- time to (re)set trailing stop - {} - for distance {} instead of {}".format(c.time, pos1.relevantPrice(c), pos1.trailingStopDesiredDistance, pos1.trailingStopDistance))
                pos1.trailingStopDistance = pos1.trailingStopDesiredDistance
                if(args.execute):
                    posMaker.executeTrailingStop(looper,pos1)
                    looper.refresh(True)
                else:
                    pos1.trailingStopNeedsReplacement = False
                    logging.debug( pos1 )

            elif(todo=='hold' or todo=="wait"):
                rvp = "n/a"
                if(pos1 is not None):
                    pos1.calibrateTrailingStopLossDesireForSteppedSpecs(c,trailSpecs, robot.mspread, looper.instrument.minimumTrailingStopDistance)
                    rvp = pos1.relevantPrice(c)
                    import random
                    if(random.randint(0,100)<=10):
                        logging.info(pos1)
                        logging.info("{} -- {}% -- RSI={} rvp={} - {}".format(c.time, round(benefRatio,3), round(rsi,3), rvp,pos1))
                    else:
                        logging.debug(pos1)
                if(args.trace): logging.debug("{} -- {}% -- RSI={} rvp={} - {}".format(c.time, round(benefRatio,3), round(rsi,3), rvp,pos1))

                continue
            else:
                logging.critical( "{} -- not sure what to do with {}".format(c.time, todo))

    if(args.execute):
        # when execute - we're using this special "iterator" approach for high-candle
        # we must use the iterator.next() only now to make sure we get it at the right time...
        for hc in highCandle:
            robot.digestHighCandle(hc)
            break # use only once..
    else:
        robot.digestHighCandle(highCandle)




logging.warning( "Money: {}".format(money) )
logging.warning("First time: {}  -- Last time: {}".format(firstTime,lastTime))
for x in counts.keys():
    logging.warning("{}: {}".format(x, counts[x]))
