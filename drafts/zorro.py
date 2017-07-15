

import argparse, re, pdb, time
import oandaconfig
import v20

import Alfred
from myt_support import TradeLoop, trailSpecsFromStringParam, getSortedCandles, getBacktrackingCandles, PositionFactory

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
parser.add_argument('--trail', nargs='?', default='1:7,2:4,3:3,5:2,10:1')
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
money = args.start

slices = args.slice.split("/")
trailSpecs = trailSpecsFromStringParam(args.trail)

cfg = oandaconfig.Config()
cfg.load("~/.v20.conf")
api = v20.Context( cfg.hostname, cfg.port, token = cfg.token)
posMaker = PositionFactory(50,50) if(args.pessimist) else PositionFactory(100,0)
looper = TradeLoop(api, cfg.active_account, args.select, 200*1000.0)
looper.initialize(posMaker)


robot = Alfred.TradeStrategy(args.trigger, args.profit, args.risk,
               args.depth, args.select, args.size,
               slices[0], slices[1],
               args.rsi, args.sdf, trailSpecs)

# set the simulation booleans
robot.simulation  = not args.execute
looper.simulation = robot.simulation

robot.initialize()


dataset =  getBacktrackingCandles(looper, args.depth*args.drag, slices[0], slices[1])

for d in dataset:
    highCandle = d[0]
    lowCandles = d[1]
    robot.digestHighCandle(highCandle)
    for c in lowCandles:
        robot.digestLowCandle(c)
        #print(c)
        event,todo,benef,benefRatio,rsi,pos1 = robot.decision(looper, posMaker)
        if(not args.execute):
            if(todo == "take-position"):
                looper.positions.append(pos1)
            elif(todo=='close'):
                print( "{0} -- Expecting to Close with event {1} - with impact {2} ({4}%); RSI={3}".format(c.time, event, benef, rsi, benefRatio))
                # print("[{},{}] [{}, {}], [{},{}] [{},{}] -- {}".format(c.bid.l, c.ask.l, c.bid.o,c.ask.o,c.bid.h,c.ask.h, c.bid.c, c.ask.c, pos1.relevantPrice(c))
                money += benef*pos1.size
                looper.positions = []
                print "Money: {}".format(money)
            elif(todo=='trailing-stop'):
                print("{} --Time to set trailing stop".format(c.time))
                pos1.setTrailingStop(c)
            elif(todo=='trailing-update'):
                print "{} -- time to advance trailing stop".format(c.time)
                pos1.updateTrailingStop(c)
            elif(todo=='hold' or todo=="wait"):
                continue
            else:
                print "{} -- not sure what to do with {}".format(c.time, todo)
