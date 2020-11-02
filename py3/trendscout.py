# Scout for an instrument with an uptrend or a downtrend

from myt_support import TradeLoop, getSortedCandles, PositionFactory
from teeth import MovingQueue
from robologger import corelog
import numpy as np
import pdb

SignalForTrend = {
    "M": "D",
    "D": "H1",
    "W": "H4",
    "H4": "M15",
    "H8": "M30",
    "H1": "M5",
    "M15": "M1",
    "M30": "M2"
}
USE_INITIAL_TRAILING_STOP = True


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


def _extend(obj1, obj2):
    """add feature of obj2 to obj1 (modifed obj1 but not obj2)"""
    for k,v in obj2.items():
        obj1[k] = v
    return obj1


def nicepadding(p, prec):
    x = format(abs(float(p)), '1.10f')
    pm = "-" if(float(p)<0) else ""
    if(x.find(".")>0):
        x += "00000"
        return pm + x[0:(x.index(".")+1+prec)]
    return pm + x

def execOppurtunity(api,cfg, instrument_name, instrument_piplocation, units, opportunity):
    """since an opportunity has been found and we are bold to execute it, let's enter the market!"""
    looper = TradeLoop(api, cfg.active_account, instrument_name, 200*1000.0)
    pfact = PositionFactory()

    looper.initialize(pfact)
    oppType, iname, breakout, SL, TP, t2time = opportunity
    forBUY = (oppType == 'BUY')
    
    positions = looper.positions 
    # trades = looper.findTrades()
    orders = looper.findOrders()
    # pdb.set_trace()
    #if(instrument_name.startswith('{}_'.format(looper.account.currency))):
        #print("{} home currency = {}".format(units, int(units*breakout)))
        #units = int(units * breakout)
    
        
    if(len(positions)>0 or len(orders)>0):
        corelog.warn("Investigating, Not executing:for {}, {} positions and {} orders exist!".format(\
            instrument_name, len(positions), len(orders)))
        if(len(positions)>0):
            prec = looper.displayPrecision
            for p in positions:
                #pdb.set_trace()
                
                if(p.forBUY == forBUY):
                    pe = 1 if(forBUY) else -1
                    sldelta = pe * (SL - p.saveLoss)
                    tpdelta = pe * (TP - p.takeProfit)
                    corelog.warn("{}: sldelta = {}, tpdelta={}".format(instrument_name, nicepadding(sldelta,prec), nicepadding(tpdelta, prec)))
                    # if( pe*(p.entryPrice() - breakout)<0) : 
                    #     # we are in a winning position - is it time to adjust the Stop Loss ?
                    #     if(sldelta>0):
                            
                else:
                    corelog.warn("{}: reversal?")
        elif(len(orders)):
            # we want to recommend cancelling pending orders that go against the found opportunity
            # if a prending order is a SELL order when the opportunity if a BUY, it should be cancelled (and vice versa)
            cancellable = (lambda o: o.units<0) if(forBUY) else (lambda o: o.units>0)
            # non cancellables are adjustable
            adjustable = lambda o: not cancellable(o)
            
            for o in filter(cancellable, orders):
                print("Order {} should be cancelled.".format(o.id))

            
            for o in filter(adjustable,orders):
                print("Order {} is adjustable?".format(o.id))
                print("Opportunity {}".format(oppType))
                print("Breakout Price: {} vs {} (now)".format(o.price, breakout))
                print("Stop Loss: {} vs {} (now)".format(o.stopLossOnFill.price, SL))
                print("Take Profit: {} vs {} (now)".format(o.takeProfitOnFill.price, TP))

            
                
    else:
        kwargs = {}
        kwargs['instrument'] = instrument_name
        pf = 1 if(forBUY) else -1
        kwargs['units'] = pf * units
        if(USE_INITIAL_TRAILING_STOP):
            kwargs['trailingStopLossOnFill'] = {"distance": nicepadding(np.abs(SL-breakout), looper.displayPrecision)}

        kwargs['stopLossOnFill'] = {"price": nicepadding(SL, looper.displayPrecision)}
        kwargs['takeProfitOnFill'] = {"price": nicepadding(TP, looper.displayPrecision)}
        kwargs['price'] = nicepadding(breakout, looper.displayPrecision)
        corelog.debug(kwargs);print(kwargs)
        response = looper.api.order.limit(cfg.active_account, **kwargs)
        if(not(response.status == 201 or response.status == '201')):
            corelog.critical( "Position / Trade could not be executed...")
            corelog.critical(response.body)
        else:
            corelog.info("position taken for {}".format(instrument_name))


def lackOfOpportunityCleanUp(api, cfg, instrument_name, instrument_piplocation):
    looper = TradeLoop(api, cfg.active_account, instrument_name, 200*1000.0)
    pfact = PositionFactory()

    looper.initialize(pfact)
    
    positions = looper.positions 
    trades = looper.findTrades()
    orders = looper.findOrders()
    
    if(len(orders)>0):
        print("Cancelling {} order(s) [stop or limit]".format(len(orders)))
        for o in orders:
            api.order.cancel(cfg.active_account, o.id)
    

def assessOpportunity(api, cfg, instrument_name, instrument_piplocation, 
        slice1 = 'H1', 
        slice2 = 'M5', 
        mvasize=20, 
        atr_plus = 10,
        riskfactor = 1.4,
        showtrace=False,
        as_if_at=None,  
        debug_after=None):

    wTo = {"price":"MBA"} if(as_if_at is None) else {"to": as_if_at, "price":"MBA"}
    looper = TradeLoop(api, cfg.active_account, instrument_name, 200*1000.0)
    # import pdb;pdb.set_trace()
    c1 = getSortedCandles(looper, _extend({"granularity":slice1, "count":str(15*mvasize)}, wTo))

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

        c2 = getSortedCandles(looper, _extend({"granularity":slice2, "count":str(15*mvasize)}, wTo))
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
            breakoutPrice = lambda c: np.min([c.bid.c, c.ask.l])
            stopLoss = lambda c,atr: c.ask.l - atr - atr_plus_pips
            takeProfit = lambda c, atr, rf: c.ask.h + rf*(atr+atr_plus_pips)
            timeToTrigger = lambda c, boPrice: c.ask.h > boPrice  
            timeToTakeProfit = lambda c, tpPrice: c.ask.h > tpPrice
            timeToSaveLoss = lambda c, slPrice: c.bid.l < slPrice
            message = lambda c, top1, top2, bPrice, opp, engaged: '{}: {} top1={} top2={} bPrice={}{}'.format(c.time, c.bid.c, bidc(top1), bidc(top2), bPrice, (opp+'*' if engaged is not None else ''))
            opp = 'BUY'
        else:
            betterTop = lambda c,t: c.ask.l < t.ask.l
            validCandle = lambda c,ema: c.ask.c < ema
            breakoutPrice = lambda c: np.max([c.bid.c, c.ask.l])
            stopLoss = lambda c,atr: c.bid.h + atr + atr_plus_pips
            takeProfit = lambda c, atr, rf: c.bid.l - rf*(atr+atr_plus_pips)
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
            if(debug_after is not None and c.time >= debug_after): 
                print( engaged_order if(engaged_order is not None) else sensible_order )

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
    parser.add_argument('--avoid', nargs='+', help='symbols of currencies or instruments to avoid')
    parser.add_argument('--slices', nargs='*', default=['H1'])
    parser.add_argument('--sp', nargs='*', default=[])
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--rf', type=float, default=1.4)
    parser.add_argument('--gains', action='store_true')
    parser.add_argument('--swift', action='store_true')
    parser.add_argument('--asifat', help='iso8601 time, as it we ran at that time')
    parser.add_argument('--dba', help='debug after (see --trace for good time format)')
    parser.add_argument('--exec', action='store_true')
    parser.add_argument('--cleanobs', action='store_true', help='clean-up pending order that are no longer supported by a detected opportunity')
    parser.add_argument('--lot', type=float, default=0.05)
    
    
    
    
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
        if(args.avoid is not None and len(args.avoid)>0):
            if(len(list([a for a in args.avoid if a in i['name'] ]))>0):
                if(not args.swift):
                    print("skipping {}".format(i['name']))
                continue
        
        if(not args.swift): 
            print("Scanning {} ... ".format(i['name']))

        oppCounter = 0
        for sp in slicepairs:
            prognosis = assessOpportunity(api, cfg, i['name'], float(i['pipLocation']), 
                     sp[0], sp[1], riskfactor= args.rf, showtrace=args.trace,
                     as_if_at=args.asifat,
                     debug_after=args.dba)
            if(prognosis is not None):
                opp, gains = prognosis
                if(opp is not None): 
                    oppCounter += 1
                if(opp and args.exec):
                    execOppurtunity(api,cfg, i['name'], float(i['pipLocation']),args.lot*100000, opp)
                    break # skip the search over other pairs

                if(args.swift and opp is None): continue
                print((sp, opp))
                if(args.gains):
                    for g in gains:
                        print(g)


        if(args.cleanobs and oppCounter == 0):
            lackOfOpportunityCleanUp(api, cfg, i['name'], None)
