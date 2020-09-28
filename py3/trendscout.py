# Scout for an instrument with an uptrend or a downtrend

from myt_support import TradeLoop, getSortedCandles
from teeth import MovingQueue
import numpy as np
import pdb

SignalForTrend = {
    "D": "H1",
    "W": "H4",
    "H4": "M15",
    "H8": "M30",
    "H1": "M5",
    "M15": "M1",
    "M30": "M2"
}


class Exponential_Moving_Average(object):
    def __init__(self, mvasize, smoothing=2, valuator=None):
        self.mvasize = mvasize
        self.valuator = valuator
        self.smoothing = smoothing
        self.phi0 = (smoothing / (1+mvasize))
        self.phi1 = 1 - self.phi0
        if(valuator is None):
            self.valuator = lambda c: c.mid.c
        
        self.mq = MovingQueue(mvasize)
        self.sma = None
        self.ema = None

    def add(self, candle):
        if(self.mq.full()):
            if(self.sma is None):
                self.sma = self.mq.reduced(lambda s,c: s+self.valuator(c)) / self.mq.currentSize()
            else:
                self.sma = self.sma + (self.valuator(candle)-self.valuator(self.mq.first()))/self.mq.currentSize()
            ma = self.sma if(self.ema is None) else self.ema
            self.ema = self.valuator(candle)*self.phi0 + ma*self.phi1
        self.mq.add(candle)



class AverageTrueRange(object):
    def __init__(self, depth=14, focus=lambda c: c.mid):
        self.depth = depth
        self.focus = focus
        self.mq = MovingQueue(depth)

        self.mq_tr = MovingQueue(depth)
        self.atr = None

    def add(self, candle):
        x = self.focus(candle)
        tr = np.abs(x.h - x.l)
        if(self.mq.currentSize()>0):
            prev = self.mq.last()
            y = self.focus(prev)
            tr_h = np.abs(x.h - y.c)
            tr_l = np.abs(x.l - y.c)
            tr = np.max([tr, tr_h, tr_l])
        self.mq_tr.add(tr)
        if(self.mq_tr.full()):
            self.atr = self.mq_tr.reduced(lambda s,tr: s+tr) / self.depth


    




    
    




def assessTrend(api, cfg, instrument_name, slice, mvasize=20):
    looper = TradeLoop(api, cfg.active_account, instrument_name, 200*1000.0)
    candles = getSortedCandles(looper, {"granularity":slice, "price":"MBA", "count":str(15*mvasize)})
    b = None
    trendPool = []
    isHHHL = lambda b,c: b.h < c.h and b.l < c.l  # higher high and higher low
    isLHLL = lambda b,c: b.h > c.h and b.l > c.l  # lower high and lower low

    ema = Exponential_Moving_Average(mvasize)
    

    for c in candles:
        ema.add(c)
        if(ema.ema is None):
            trendPool.append('-')
        else:
            if(ema.ema < c.bid.l):
                trendPool.append('^')
            elif(ema.ema > c.ask.h):
                trendPool.append('v')
            else:
                trendPool.append('-')
    start = - mvasize*5
    return "{} {} {}".format(candles[start].time, ''.join(trendPool[start:]), candles[-1].time)


def assessOpportunity(api, cfg, instrument_name, instrument_piplocation, 
        slice1 = 'H1', 
        slice2 = 'M5', 
        mvasize=20, 
        atr_plus = 10,
        riskfactor = 1.4,
        showtrace=False):
    looper = TradeLoop(api, cfg.active_account, instrument_name, 200*1000.0)
    c1 = getSortedCandles(looper, {"granularity":slice1, "price":"MBA", "count":str(15*mvasize)})

    ema1 = Exponential_Moving_Average(mvasize)
    ema2 = Exponential_Moving_Average(mvasize)

    atr_plus_pips = atr_plus * 10**instrument_piplocation 

    ptrace = (lambda x: print(x)) if showtrace else lambda x: None
    

    trendPool = []

    for c in c1:
        ema1.add(c)
        if(ema1.ema is None):
            trendPool.append('-')
        else:
            if(ema1.ema < c.bid.l): # stringent
                trendPool.append('^')
            elif(ema1.ema > c.ask.h): # stringent
                trendPool.append('v')
            else:
                trendPool.append('-')

    trend = ''.join(trendPool[-5:])
    
    if(trend == '^^^^^' or trend == 'vvvvv'):
        trend = 'up' if(trend.startswith('^')) else 'down'

        c2 = getSortedCandles(looper, {"granularity":slice2, "price":"MBA", "count":str(15*mvasize)})
        atr = AverageTrueRange()
        # we seek 2 consecutive tops, top1, top2, with top1 before top2, top2 better than top1
        top1_candidate = None
        top1 = None
        top2_candidate = None
        top2 = None
        # a top is detected by finding a maximum, and at least 2 candles that pull back, so we track the age of the candidates
        age1 = 0
        age2 = 0
        # top22_candidate : is potential improvement on top2
        top22_candidate = None
        age22 = 0
        bidc = lambda x: '' if(x is None) else x.bid.c
        askc = lambda x: '' if(x is None) else x.ask.c

        betterTop = None
        if(trend == 'up'):
            betterTop = lambda c, t: c.bid.h > t.bid.h
            validCandle = lambda c, ema: c.bid.c > ema
            breakoutPrice = lambda c: c.ask.c
            stopLoss = lambda c,atr: c.ask.c - atr - atr_plus_pips
            takeProfit = lambda c, atr, rf: c.ask.c + rf*(atr+atr_plus_pips)
            timeToTrigger = lambda c, boPrice: c.ask.h > boPrice  
            timeToTakeProfit = lambda c, tpPrice: c.ask.h > tpPrice
            timeToSaveLoss = lambda c, slPrice: c.bid.l < slPrice
            message = lambda c, top1, top2, bPrice, opp, engaged: '{}: {} top1={} top2={} bPrice={}{}'.format(c.time, c.bid.c, bidc(top1), bidc(top2), bPrice, (opp+'*' if engaged is not None else ''))
            opp = 'BUY'
        else:
            betterTop = lambda c,t: c.ask.l < t.ask.l
            validCandle = lambda c,ema: c.ask.c < ema
            breakoutPrice = lambda c: c.bid.c
            stopLoss = lambda c,atr: c.bid.c + atr + atr_plus_pips
            takeProfit = lambda c, atr, rf: c.bid.c - rf*(atr+atr_plus_pips)
            timeToTrigger = lambda c, boPrice: c.bid.l < boPrice
            timeToTakeProfit = lambda c, tpPrice: c.bid.l < tpPrice
            timeToSaveLoss = lambda c, slPrice: c.ask.h > slPrice
            message = lambda c, top1, top2, bPrice, opp, engaged: '{}: {} top1={} top2={} bPrice={}{}'.format(c.time, c.ask.c, askc(top1), askc(top2), bPrice, (opp+'*') if engaged is not None else '')
            opp = 'SELL'

        sensible_order = None
        engaged_order = None
        orders = []
        breakout = None

        for c in c2:
            ptrace(message(c, top1, top2, breakout, opp, engaged_order))
            ema2.add(c)
            atr.add(c)

            # do we have an stop order and should we trigger it ?
            if(sensible_order is not None and engaged_order is None):
                if(timeToTrigger(c,sensible_order[2])):
                    _a,_b,_c,_d,_e,_f = sensible_order
                    engaged_order = (_a,_b,_c,_d,_e,_f, c.time)
            # do we have en engaged order and should we close it ?
            elif(engaged_order is not None):
                tp = engaged_order[4]
                sl = engaged_order[3]
                if(timeToTakeProfit(c, tp)):
                    profit = np.ceil(100*np.abs(engaged_order[4]-engaged_order[2])/ 10**instrument_piplocation)/100
                    _a,_b,_c,_d,_e,_f,_g = engaged_order
                    orders.append( (_a,_b,_c,_d,_e,_f,_g,c.time,profit))
                    breakout = top1 = top2 = sensible_order = engaged_order = None
                
                    ptrace('+{}pips'.format(profit))
                elif(timeToSaveLoss(c, sl)):
                    loss = np.ceil(100*np.abs(engaged_order[3]-engaged_order[2]) / 10**instrument_piplocation)/100
                    _a,_b,_c,_d,_e,_f,_g = engaged_order
                    orders.append( (_a,_b,_c,_d,_e,_f,_g,c.time, -loss) )
                    ptrace('-{}pips'.format(loss))
                    breakout = top1 = top2 = sensible_order = engaged_order = None
    
                    
            
            if(ema2.ema is None or atr.atr is None): continue
            if(ema2.ema is not None):
                if(not validCandle(c, ema2.ema)):
                        top1 = None
                        top2 = None
                        top1_candidate = None
                        top2_candidate = None
                        top22_candidate = None
                        age1 = age2 = age22 = 0
                        breakout = None
                        sensible_order = None
                        continue

                if(top1 is None):
                    # we are still looking for top1:
                    if(top1_candidate is None):
                        top1_candidate = c
                        age1 = 0
                    else:
                        if(betterTop(c, top1_candidate)):
                            top1_candidate = c
                            age1 = 0
                        else:
                            age1 += 1
                            if(age1>2):
                                # confirmed top:
                                top1 = top1_candidate
                                top1_candidate = None
                else:
                    # we have top1 already, let's find top2:
                    # well - if not a valid candle, lets' forget top1 ...
                    if(top2 is None):
                        if(top2_candidate is None):
                            if(betterTop(c, top1)):
                                top2_candidate = c
                                age2 = 0
                        elif(betterTop(c, top2_candidate)):
                            top2_candidate = c
                            age2 = 0
                        else:
                            age2 += 1
                            if(age2>2):
                                # confirmed top2:
                                top2 = top2_candidate
                                age2 = 0
                                top2_candidate = None
                    else:
                        # we have a top2, let's check that we may get even better...
                        if(top22_candidate is None):
                            if(c is None or top2 is None): pdb.set_trace()
                            if(betterTop(c,top2)):
                                top22_candidate = c
                                age22 = 0
                        else:
                            if(betterTop(c,top22_candidate)):
                                top22_candidate = c
                                age22 = 0
                            else:
                                age22 += 1
                                if(age22>2):
                                    top1 = top2
                                    top2 = top22_candidate
                                    top22_candidate = None
                                    age22 = None
                        
                        breakout  = breakoutPrice(top2)
                        SL = stopLoss(c, atr.atr)
                        TP = takeProfit(c, atr.atr, riskfactor)

                        if(sensible_order is not None and breakout != sensible_order[2]):
                            ptrace("breakout: {} >> {}  {}".format(sensible_order[2], breakout, c.time))

                        sensible_order = (opp, instrument_name, breakout, SL, TP, top2.time)
        return (sensible_order, orders)
    else:
        return None



if __name__ == '__main__':
    import argparse, re, pdb, time
    import oandaconfig
    import v20, csv, json

    from myt_support import TradeLoop, trailSpecsFromStringParam, getSortedCandles, getBacktrackingCandles, PositionFactory
    from extractor import listInstruments


    parser = argparse.ArgumentParser()

    parser.add_argument('--ref', nargs='?',
                        help="reference currency for scan", default='USD')
    parser.add_argument('--slices', nargs='*', default=['H1'])
    parser.add_argument('--sp', nargs='*', default=[])
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--rf', type=float, default=1.4)
    parser.add_argument('--gains', action='store_true')
    
    
    args = parser.parse_args()
    
    cfg = oandaconfig.Config()
    cfg.load("~/.v20.conf")
    api = v20.Context( cfg.hostname, cfg.port, token = cfg.token)

    stuff = list(filter(lambda v: args.ref in v['name'], listInstruments(api, cfg)))

    print("will scan {} instruments...".format(len(stuff)))
    slicepairs = list([ (p, SignalForTrend[p]) for p in args.slices])
    if(args.sp is not None and len(args.sp)>0):
        if(len(args.sp) %2 == 1):
            args.sp.append( SignalForTrend[  args.sp[-1] ])
        slicepairs = list ([ (args.sp[2*i], args.sp[2*i+1]) for i in range(len(args.sp)) if(len(args.sp)>2*i+1) ])
       

    for i in stuff:
        print("Scanning {} ... ".format(i['name']))
        for sp in slicepairs:
            opp = assessOpportunity(api, cfg, i['name'], float(i['pipLocation']), 
                     sp[0], sp[1], riskfactor= args.rf, showtrace=args.trace)
            if(opp is not None):
                opp, gains = opp
                print((sp, opp))
                if(args.gains):
                    for g in gains:
                        print(g)
                    