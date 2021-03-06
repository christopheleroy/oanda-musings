#!python
import argparse
#import common.config
import oandaconfig
import v20
from myt_support import PositionFactory, TradeLoop, trailSpecsFromStringParam


parser = argparse.ArgumentParser()
parser.add_argument('--size', nargs='?', type=float);
parser.add_argument('--select', nargs='?')
parser.add_argument('--sell', action='store_true')
parser.add_argument('--sl', type=float, help='stop-loss value when entering the trade or when modifying an existing trade (--id)')
parser.add_argument('--tsl', type=float, help='when modifying an existing trade, provide the trailing-stop-loss value')
parser.add_argument('--distance', type=float, default=None)
parser.add_argument('--tp', type=float, help='take-profit value when entering the trade or when modifying an existing trade (--id)')
parser.add_argument('--list', action='store_true', help='list current positions for the selected pair')
parser.add_argument('--id', nargs='?', help='point to a specific trade (position or order?) for modification')
parser.add_argument('--verbose', action='store_true')
parser.add_argument('--close', action='store_true')
parser.add_argument('--trail', nargs='?', default='none')


args = parser.parse_args()

cfg = oandaconfig.Config()
cfg.load("~/.v20.conf")
api = v20.Context( cfg.hostname, cfg.port, token = cfg.token)
mker = PositionFactory(50,5)
onceOnly = TradeLoop(api, cfg.active_account, args.select)
import pdb;pdb.set_trace()
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
    print(onceOnly.instrument)
    if(onceOnly.positions is not None and len(onceOnly.positions)>0):
        for p in onceOnly.positions:
            if(args.verbose): print(p)
            print("Trade {} (SL: {}, TP: {}): {}".format(p.tradeID, p.saveLossOrderId, p.takeProfitOrderId, p))
            if(p.trailingStopLossOrderId is not None):
                print("(with trailing-stop-loss, value={}, distance={}, id={})".format(p.trailingStopValue, p.trailingStopDistance, p.trailingStopLossOrderId))
                if(args.trail != 'none'):
                    trailSpecs = trailSpecsFromStringParam(args.trail)
                    p.calibrateTrailingStopLossDesireForSteppedSpecs(candles[-1], trailSpecs, cspread)
    else:
        print("No positions for {}".format(onceOnly.instrumentName))

    for p in onceOnly.findTrades():
        print(p)

    import sys;sys.exit(0)
elif(args.id is not None):
    poss = [p for p in onceOnly.positions if p.tradeID == args.id]
    if(len(poss)>0):
        if(args.verbose): print(poss[0])
        if(args.close):
            if(args.size is None):
                respCL = onceOnly.api.trade.close(cfg.active_account, args.id)
            else:
                respCL = onceOnly.api.trade.close(cfg.active_account, args.id, units=str(args.size))

            print("CLOSE order{}\n{}".format(respCL.status, respCL.body))
        if(args.tsl is not None):
            if(args.distance is None): args.distance = 5
            distance = args.distance*10**(onceOnly.instrument.pipLocation) if(poss[0].trailingStopLossOrderId is None and args.distance>0) else (poss[0].trailingStopDistance)
            tslargs = {"price": str(args.tsl), "tradeID": args.id, "distance":  distance }
            if(poss[0].trailingStopLossOrderId is None):
                respTSL = onceOnly.api.order.trailing_stop_loss(cfg.active_account, **tslargs)
            else:
                respTSL = onceOnly.api.order.trailing_stop_loss_replace(cfg.active_account, poss[0].trailingStopLossOrderId, **tslargs)
            print("TSL order: {}\n{}".format(respTSL.status, respTSL.body))
        elif(args.distance is not None):
            distance = args.distance*10**(onceOnly.instrument.pipLocation)
            if(poss[0].trailingStopLossOrderId is not None):
                tslargs = {"price":str(poss[0].trailingStopValue), "tradeID": args.id, "distance": distance}
                respTSL = onceOnly.api.order.trailing_stop_loss_replace(cfg.active_account, poss[0].trailingStopLossOrderId, **tslargs)
                print("TSL order:{}\n{}".format(respTSL.status, respTSL.body))
        if(args.sl is not None):
            slrpargs={"price":str(args.sl), "tradeID": args.id }
            respSL = onceOnly.api.order.stop_loss_replace(cfg.active_account, poss[0].saveLossOrderId, **slrpargs) #201 is ok answer
            #respSL = onceOnly.api.order.trailing_stop_loss(cfg.active_account, **slrpargs)
            print("SL order: {}\n{}".format(respSL.status, respSL.body))
        if(args.tp is not None):
            tprpargs={"price": args.tp, "tradeID": args.id}
            respTP = onceOnly.api.order.take_profit_replace(cfg.active_account, poss[0].takeProfitOrderId, **tprpargs) #201 is ok answer
            print("TP order: {}".format(respTP.status))
    import sys;sys.exit(0)


if(args.size is None or args.sl is None or args.tp is None):
    print("Missing: size, sl or tp")
    import sys;sys.exit(100)

pos = mker.make(not args.sell, candles[-1], args.size, args.sl, args.tp)

tryIt = mker.executeTrade(onceOnly, pos)
if(tryIt is not None):
    pos = tryIt[0]
    posId = tryIt[1]
    print("Position is on Trade ID {}: {} ".format(posId, pos))
else:
    print("Position could not be executed because of market conditions or broker issues - or other exception")
