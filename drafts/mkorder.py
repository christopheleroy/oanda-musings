#!python
import argparse
#import common.config
import oandaconfig
import v20
from myt_support import PositionFactory, TradeLoop, trailSpecsFromStringParam


parser = argparse.ArgumentParser()
parser.add_argument('--size', nargs='?', type=float, default=1000.0);
parser.add_argument('--select', nargs='?')
parser.add_argument('--sell', action='store_true')
parser.add_argument('--sl', type=float)
parser.add_argument('--tsl', type=float)
parser.add_argument('--distance', type=float, default=None)
parser.add_argument('--tp', type=float)
parser.add_argument('--list', action='store_true')
parser.add_argument('--id', nargs='?')
parser.add_argument('--verbose', action='store_true')
parser.add_argument('--trail', nargs='?', default='none')


args = parser.parse_args()

cfg = oandaconfig.Config()
cfg.load("~/.v20.conf")
api = v20.Context( cfg.hostname, cfg.port, token = cfg.token)
mker = PositionFactory(50,5)
onceOnly = TradeLoop(api, cfg.active_account, args.select)
onceOnly.initialize(mker)



kwargs = {}
kwargs['count'] = 1
kwargs['price'] = 'BA'
kwargs['granularity'] = 'S5'
resp = api.instrument.candles(args.select, **kwargs)
candles = resp.get('candles', 200)
cspread = candles[-1].ask.o - candles[-1].bid.o
#import pdb; pdb.set_trace()

if(args.list):
    print onceOnly.instrument
    if(onceOnly.positions is not None and len(onceOnly.positions)>0):
        for p in onceOnly.positions:
            if(args.verbose): print p
            print "Trade {} (SL: {}, TP: {}): {}".format(p.tradeID, p.saveLossOrderId, p.takeProfitOrderId, p)
            if(p.trailingStopLossOrderId is not None):
                print "(with trailing-stop-loss, value={}, distance={}, id={})".format(p.trailingStopValue, p.trailingStopDistance, p.trailingStopLossOrderId)
                if(args.trail != 'none'):
                    trailSpecs = trailSpecsFromStringParam(args.trail)
                    p.calibrateTrailingStopLossDesireForSteppedSpecs(candles[-1], trailSpecs, cspread)
    else:
        print "No trades for {}".format(onceOnly.instrumentName)
    import sys;sys.exit(0)
elif(args.id is not None):
    poss = filter(lambda p: p.tradeID == args.id, onceOnly.positions)
    if(len(poss)>0):
        if(args.verbose): print poss[0]
        if(args.tsl is not None):
            if(args.distance is None): args.distance = 5
            distance = args.distance*10**(onceOnly.instrument.pipLocation) if(poss[0].trailingStopLossOrderId is None and args.distance>0) else (poss[0].trailingStopDistance)
            tslargs = {"price": str(args.tsl), "tradeID": args.id, "distance":  distance }
            if(poss[0].trailingStopLossOrderId is None):
                respTSL = onceOnly.api.order.trailing_stop_loss(cfg.active_account, **tslargs)
            else:
                respTSL = onceOnly.api.order.trailing_stop_loss_replace(cfg.active_account, poss[0].trailingStopLossOrderId, **tslargs)
            print "TSL order: {}\n{}".format(respTSL.status, respTSL.body)
        elif(args.distance is not None):
            distance = args.distance*10**(onceOnly.instrument.pipLocation)
            if(poss[0].trailingStopLossOrderId is not None):
                tslargs = {"price":str(poss[0].trailingStopValue), "tradeID": args.id, "distance": distance}
                respTSL = onceOnly.api.order.trailing_stop_loss_replace(cfg.active_account, poss[0].trailingStopLossOrderId, **tslargs)
                print "TSL order:{}\n{}".format(respTSL.status, respTSL.body)
        if(args.sl is not None):
            slrpargs={"price":str(args.sl), "tradeID": args.id }
            respSL = onceOnly.api.order.stop_loss_replace(cfg.active_account, poss[0].saveLossOrderId, **slrpargs) #201 is ok answer
            #respSL = onceOnly.api.order.trailing_stop_loss(cfg.active_account, **slrpargs)
            print "SL order: {}\n{}".format(respSL.status, respSL.body)
        if(args.tp is not None):
            tprpargs={"price": args.tp, "tradeID": args.id}
            respTP = onceOnly.api.order.take_profit_replace(cfg.active_account, poss[0].takeProfitOrderId, **tprpargs) #201 is ok answer
            print "TP order: {}".format(respTP.status)
    import sys;sys.exit(0)



pos = mker.make(not args.sell, candles[-1], args.size, args.sl, args.tp)

tryIt = mker.executeTrade(onceOnly, pos)
if(tryIt is not None):
    pos = tryIt[0]
    posId = tryIt[1]
    print "Position is on Trade ID {}: {} ".format(posId, pos)
else:
    print("Position could not be executed because of market conditions or broker issues - or other exception")
