#!/bin/env python
import argparse, re, pdb, time, os, logging
import oandaconfig, timespecs
import v20
from robologger import corelog
from robologger import oscillog

logging.basicConfig(format='%(asctime)s %(name)s -%(levelname)s- %(message)s', datefmt = '%d-%m %H:%M:%S')
import Alfred
import Bibari
from myt_support import TradeLoop, trailSpecsFromStringParam, PositionFactory, \
                         getSortedCandles, getBacktrackingCandles, getCachedBacktrackingCandles, getLiveCandles, \
                         nicetime, setTimezoneForLogs

## Setting PARAMETER PARSING:
defCFG = os.environ('ZORRO_V20_CONFIG') if('ZORRO_V20_CONFIG' in os.environ) else "~/.v20.conf"
defSUPER = os.environ('ZORRO_SUPER') if('ZORRO_SUPER' in os.environ) else None
parser = argparse.ArgumentParser()
parser.add_argument('--bibari', action='store_true')
parser.add_argument('--ks', type=int, default=22, help='in Bibari, the #-periods for kijun')
parser.add_argument('--ts', type=int, default=5, help='in Bibari, the #-periods for tenkan')
parser.add_argument('--xos', type=int, default=5, help='in Bibari, number of period in the past to detect Kijun/Tenkan cross-over')


parser.add_argument('--tz', help='timezone to use when displaying market time', default=None)

parser.add_argument('--v20config', help='point to the v20-configuration yaml file', default=defCFG)
parser.add_argument('--size', nargs='?', type=float, default=1000.0,
                    help="size of the transaction in units (default 1000, which is a micro-lot in most pairs)");
parser.add_argument("--start", nargs='?', type=float, default=5000.0,
                    help="amount of money to start with for backtracking")
parser.add_argument('--select', nargs='?',
                    help="valid currency-pair")
parser.add_argument('--fstup', nargs='?', type=float, default=1.0,
                    help="factor to initiliaze the high candle at start-up, as quite candles are a possibility")
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
                    help="specify the trailing-stop approach (warning: there is a default value, so better specify this parameter)")
parser.add_argument('--tshrink', nargs='?', default='6:0.9',
                    help='specify the trail-shrink parameters, e.g 10:0.95 means factor of 0.95 and for 10 times the high candle frequency')
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
parser.add_argument('--cfreq', default=10.0, type=float,
                    help="frequency of showing current price / benefit/loss - default: 10 for 10%")
parser.add_argument('--dir', type=str, help='candle-cache directory')
parser.add_argument('--since', type=str, help="start simulation then, as RFC3339")
parser.add_argument('--till', type=str, help="end simulation then, as RFC3339")
parser.add_argument('--loglevel', type=int)
parser.add_argument('--pq', action='store_true', help='silence log messages about parsing parameters')
parser.add_argument('--super', nargs='?',
                    help='point to a super-args file', default=defSUPER)
parser.add_argument('--session', nargs='?',
                    help='provide a tag for the session, may be combined with --super to set default params for a session')
parser.add_argument('--tty', action='store_true',
                    help='will invoke unix command tty to use as session tag, but assign it to argument tty, but with /dev/ or /devices/ removed. This may be helpful instead of the session tag (or in combination with it)')

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

parser.add_argument('--calendar', nargs='?')

## Parse Arguments
args = parser.parse_args()

if(args.loglevel is not None and not args.pq):
    logging.basicConfig(level=logging.INFO)

if(args.tty):
    import subprocess
    _tty = subprocess.check_output('tty')
    args.tty = _tty.rstrip().replace("/devices/","").replace("/dev/","")
    if(args.session is not None and args.session == 'tty'):
        args.session = _tty

if(args.super):
    import superargs
    supersetsecurity=[ ['profit', 'trail'], ['insurance','trail','msm']]
    superargs.superimposeFromFile(parser, args, args.super, supersetsecurity)

# Adjust log levels
if(args.loglevel is not None):
    logging.basicConfig(format='%(asctime)s %(name)s -%(levelname)s- %(message)s', datefmt = '%d-%m %H:%M:%S')
    oscillog.setLevel(args.loglevel)
    corelog.setLevel(args.loglevel)


if(args.tz is not None):
    setTimezoneForLogs(args.tz)
    

def hourlydaily(lastTime,helloTime):
    if(args.hourly):
        return lastTime[:13] != helloTime[:13]
    return lastTime[:11] != helloTime[:11]

# Environment and Robot Set-Up
money = args.start
slices = args.slice.split("/")
trailSpecs = trailSpecsFromStringParam(args.trail)
calendarSpecs = None
if(args.calendar):
    calendarSpecs = timespecs.parse(args.calendar)

cfg = oandaconfig.Config()
cfg.load(args.v20config)
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


if(args.bibari):
    robot = Bibari.TradeStrategy(args.trigger, args.profit, args.risk, args.select, args.size,
                                 args.ts, args.ks, args.xos,
                                 slices[0], slices[1],trailSpecs)
    tshrinkm = re.match(r"(\d+.?\d*):(0?.\d+)", args.tshrink)
    if(tshrinkm is not None):
        robot.setTrailingSpecShrinker(float(tshrinkm.groups()[1]), float(tshrinkm.groups()[0]))
    else:
        robot.setTrailingSpecShrinker()

else:
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
    rmArgs={}
    if(args.rrsi == 'ok'):
        logging.info("Risk Management will have 'rsiAlwaysOK' set to True")
        rmArgs['rsiAlwaysOK'] = True
            
    elif(args.rrsi=='inverted'):
        logging.info("Risk Management will have rsiInverted set to True")
        rmArgs['rsiInverted'] = True

    if(args.bibari):
            rmArgs['ichiMaker'] = True
        
    robot.riskManagement = Alfred.RiskManagementStrategy.parse(args.insurance,robot,rmArgs)
    robot.maxEngagedSize = args.msm * args.size
    logging.info("Risk Managment: {} specs parsed, max engage size will be : {}".format(len(robot.riskManagement), robot.maxEngagedSize))

counts = {}


dataset =  None
if(args.execute):
    initDepth = (args.ks*3+1) if(args.bibari) else (args.depth+1)
    dataset = getLiveCandles(looper, initDepth, slices[0], slices[1])
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
            print(("> {} -- {} {}".format(x.time[10:19], time.time(), zz)))
            tt.append(x.time[10:19] + zz)
        print("; ".join(tt))
        pq0 = next(pq[0]) if(args.execute) else pq[0]
        print(">> high: {} --- {} {}".format(pq0.time, time.time(), ("*" if(pq0.complete)else "!")))
    import sys
    sys.exit(99)



firstTime = "??" #dataset[0][0].time
lastTime = firstTime
helloTime = firstTime
helloMoney = money
logging.critical("{} - MONEY: {} - Diff: {}".format(helloTime, helloMoney, 0.0))
timeTag = "ok"
firstTime = None
executionReady = False

for d in dataset:
    highCandle = d[0]
    lowCandles = d[1]

    for c in lowCandles:
        lastTime = c.time
        firstTime = firstTime if(firstTime is not None) else lastTime
        if(hourlydaily(lastTime, helloTime) and (helloMoney != money or not args.nzd)):
            logging.critical("{} - MONEY: {} - Diff: {}".format(nicetime(lastTime), money, money - helloMoney))
            helloMoney = money
            helloTime = lastTime

        robot.digestLowCandle(c)
        if(args.execute and not executionReady): 
            if(not dataset.isnowlive()):
                logging.debug("--still waiting to be execution ready--")
                continue
            else:
                # import pdb;pdb.set_trace()
                logging.critical("-- now execution ready !! --")
                executionReady = True

        if(calendarSpecs is not None): timeTag = timespecs.timeTag(c.time, calendarSpecs,"ok")
        decisions = robot.decision(looper, posMaker)
        for dec in decisions:
            event,todo,benef,benefRatio,rsi,pos1 = dec
            #print((c.time, todo))

            if(todo == "take-position"):
                if(timeTag not in ["open","ok"]):
                    logging.warning("Decision to 'take-position' is skipped timeTag={}".format(timeTag))
                else:
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
                logging.critical( "{0} -- Expecting to Close with event {1} - with impact {2} ({4}%); size={5}; RSI={3}".format(nicetime(c.time),
                                   event, benef, round(rsi,2), round(benefRatio,2), pos1.size))
                # print("[{},{}] [{}, {}], [{},{}] [{},{}] -- {}".format(c.bid.l, c.ask.l, c.bid.o,c.ask.o,c.bid.h,c.ask.h, c.bid.c, c.ask.c, pos1.relevantPrice(c))
                tag = ("BUY " if(pos1.forBUY)else "SELL") + " - " + (event+"        ")[0:15] + " - " + ("gain" if(benef>0)else("loss"))
                counts[tag] = 1+ (counts[tag] if(tag in counts)else 0)
                if(args.execute):
                    looper.refreshPositions(posMaker,True)
                else:
                    money += benef*pos1.size
                    pos1Time,beforeCount = pos1.entryQuote.time, len(looper.positions)
                    looper.positions = [p for p in looper.positions if p.entryQuote.time != pos1Time]
                    if(len(looper.positions) != beforeCount-1):
                        raise RuntimeError("failure/bug in removing expected closed position")
                    logging.warning("Money: {}".format(money))

            elif(todo=="flip-position"):
                # when flip-position, the pos1 item is actual a pair of positions. (newer position, closing position)
                closePos = pos1[1]
                pos1 = pos1[0]

                if(timeTag not in ["ok", "open","flips"]):
                    logging.info("Decision to 'flip-position' is skip because timeTag={}".format(timeTag))
                else:

                    logging.critical("{} -- Flipping position with event {} - with impact {} ({}%)".format(nicetime(c.time), event, benef, round(benefRatio,2)))
                    tag = ("BUY " if(pos1.forBUY)else "SELL") + " - " + (event+"        ")[0:15] + " - " + ("gain" if(benef>0)else("loss"))
                    counts[tag] = 1+ (counts[tag] if(tag in counts)else 0)

                    if(args.execute):
                        tryIt = posMaker.executeTrade(looper, pos1)
                        if(tryIt is not None):
                            logging.warning("Info position taken with id={}: {}".format(tryIt[1], tryIt[0]))
                        else:
                            logging.critical("Unable to take position {} for various reasons".format(pos1))

                    else:
                        # with the oanda API, to flip from 1lot BUY to a 2lot SELL, we push a  3lot SELL through the API
                        # in simulation, the robot will send a 3lot SELL, so let's account for it correctly here.
                        newPosArray = [p for p in looper.positions if p.entryQuote.time != closePos.entryQuote.time]
                        if(len(newPosArray) != len(looper.positions)-1):
                            raise RuntimeError("bug - unable to remove closing postion (in simulation)")
                        pos1.size -= closePos.size
                        if(pos1.size<0):
                            raise RuntimeError("bug - position size rendered negative...")
                        elif(pos1.size>0):
                            newPosArray.append(pos1)
                            logging.warning("Position flip was same as closing position...")
                        money += benef*closePos.size
                        looper.positions = newPosArray


            elif(todo=='trailing-stop'):
                logging.info("{} --Time to set trailing stop - {}".format(nicetime(c.time),pos1.relevantPrice(c)))
                if(args.execute):
                    posMaker.executeTrailingStop(looper,pos1)
                    looper.refresh(True)
                else:
                    pos1.setTrailingStop(c)
                    logging.debug( pos1 )

            elif(todo=='trailing-progress'):
                logging.info("{} -- time to advance trailing stop value - {}".format(nicetime(c.time), pos1.relevantPrice(c)))
                if(args.execute):
                    looper.refresh(True)
                else:
                    pos1.updateTrailingStopValue(c)
                    logging.debug( pos1 )

            elif(todo=='trailing-update'):
                logging.info("{} -- time to (re)set trailing stop - {} - for distance {} instead of {}".format(nicetime(c.time), pos1.relevantPrice(c), pos1.trailingStopDesiredDistance, pos1.trailingStopDistance))
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
                    if(random.randint(0,100)<=args.cfreq):
                        logging.debug(pos1)
                        logging.info("{} -- {}% -- RSI={} rvp={} - {}".format(nicetime(c.time), round(benefRatio,3), round(rsi,3), rvp,pos1))
                    else:
                        logging.debug(pos1)
                if(args.trace): logging.debug("{} -- {}% -- RSI={} rvp={} - {}".format(nicetime(c.time), round(benefRatio,3), round(rsi,3), rvp,pos1))

                continue
            else:
                logging.critical( "{} -- not sure what to do with {}".format(nicetime(c.time), todo))
    # import pdb;pdb.set_trace()
    if(args.execute):
        # when execute - we're using this special "iterator" approach for high-candle
        # we must use the iterator.next() only now to make sure we get it at the right time...
        for hc in highCandle:
            robot.digestHighCandle(hc)
            break # use only once..
    else:
        robot.digestHighCandle(highCandle)




logging.critical( "Money: {}".format(money) )
logging.critical("First time: {}  -- Last time: {}".format(nicetime(firstTime),nicetime(lastTime)))
for x in list(counts.keys()):
    logging.warning("{}: {}".format(x, counts[x]))
