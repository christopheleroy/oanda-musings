import datetime
import dateutil.parser
import numpy as np
from forwardInstrument import Opportunity
import pdb

__dtconv = {}

def candleTime(c):
    if(not __dtconv.has_key(c.time)):
        __dtconv[ c.time ] = int(dateutil.parser.parse(c.time).strftime("%s"))
    return __dtconv[c.time]

def _find_(lam, coll):
    them = filter(lam, coll)
    if(len(them)>0):
        return them[0]
    return None

def summarize(forBUY, ci, lastExtreme,pf,trSize,iname,lastTime):
    deltaT = np.ceil(candleTime(ci) - candleTime(lastExtreme))

    opp = Opportunity(lastExtreme, ci, pf, trSize, iname)
    # deltaR = ci.bid.o - lastExtreme.bid.o
    deltaR = opp.delta(forBUY)
    deltaPips = opp.deltaPips(forBUY)
    # deltaS = ci.bid.o - lastExtreme.ask.o if(forBUY) else (lastExtreme.bid.o - ci.ask.o)
    # prof = deltaS*(100000*trSize)/ci.bid.o

    #pair=iname.split("_")
    #pair[0] = "$" if(pair[0]=='USD')else pair[0]
    # pdb.set_trace()
    timeStr = lastExtreme.time if(lastTime is None or lastExtreme.time != lastTime) else "     -------------  "
    return timeStr + " + " + str(np.floor(deltaT/60))+"m"+str(deltaT%60) + "s " + \
        ("increase" if(deltaR>0)else "decrease") + " " + str(abs(deltaR)) + "= " + str(abs(deltaPips)) + "pips -" +\
        "bid starting at: " + str(lastExtreme.bid.o)+ "  -" + \
        (("profits: +"+ str(opp.profitPips(forBUY)) + "pips ("+opp.pair[0]+str(opp.profitAmount(forBUY))+")") if(opp.ok(forBUY))else('no profit!')) + \
        "  (on a "+ ("BUY" if(forBUY) else "SELL")+" order)"



def downloads(slice):
    _ = {
        "M1":["S5","M1","M15","H1"],
        "M5":["M1","M5","M15","H1"],
        "M15": ["M1","M15","H1","H4"],
        "M30": ["M15", "M30", "H1", "H4"],
        "H1": ["M15", "H1", "H4", "D"],
        "D": ["H1", "D", "W"]
    }
    return _[slice]


def frequency(slice):
    _ = {
        "S": 1,
        "M": 60,
        "H": 3600,
        "D": 86400,
        "W": 86400*7
    }
    fst = slice[0]
    q   = int(slice[1:]) if(len(slice)>1)else 1
    return _[fst]*q


def queueSecretSauce(queue, trigger=3,sdf=0.3):
    spreads = map(lambda x: x.ask.o - x.bid.o, queue)
    bids = map (lambda x: x.bid.o, queue)
    asks = map (lambda x: x.ask.o, queue)
    sdev   = np.std(bids)
    mspread = np.median(spreads)
    mbid = np.median(bids)
    mask = np.median(asks)
    askTrigger = mbid - trigger*mspread + sdf*sdev
    bidTrigger = mask + trigger*mspread - sdf*sdev

    return mbid,mask, mspread, sdev, bidTrigger, askTrigger



class PositionFactory(object):
    def __init__(self, current=50,extreme=50):
        self.current = float(current)
        self.extreme = float(extreme)

    def make(self,forBUY, quote,size,saveLoss, takeProfit):
        return Position(forBUY,quote,size,saveLoss,takeProfit, (self.current, self.extreme))

    def makeFromExistingTrade(self, quoteTmpl, v20Account, tradeID):
        trade = _find_(lambda t: t.id == tradeID, v20Account.trades)
        orders = (filter(lambda t: t.tradeID == tradeID, v20Account.orders))
        tp0 = _find_(lambda t: t.type == 'TAKE_PROFIT', orders)
        sl0 = _find_(lambda t: t.type == 'STOP_LOSS', orders)
        if(trade is not None and tp0 is not None and sl0 is not None):
            iu = float(trade.initialUnits)
            pr = float(trade.price)
            forBUY = iu>0
            size = np.abs(iu)
            c = quoteTmpl
            c.ask.o = c.ask.c = c.ask.h = c.ask.l = pr
            c.bid.o = c.bid.c = c.bid.h = c.bid.l = pr
            saveLoss = float(sl0.price)
            takeProfit = float(tp0.price)
            c.time = trade.openTime
            return Position(forBUY, c, size, saveLoss, takeProfit, (self.current, self.extreme) )
        return None

    def executeTrade(self, api, v20Account, instrument, pos,wait=1200):
        kwargs = {}
        kwargs['instrument'] = instrument
        # kwargs['price']=pos.entryQuote.ask.o if(pos.forBUY) else pos.entryQuote.bid.o
        kwargs['units']=(pos.size if(pos.forBUY) else -pos.size)
        #kwargs['timeInForce']='GTC'
        kwargs['stopLossOnFill'] = {"price": round(pos.saveLoss,5)}
        kwargs['takeProfitOnFill'] = {"price": round(pos.takeProfit,5)}
        print kwargs
        response = api.order.market(
            v20Account.id,
            **kwargs
        )
        if(not(response.status == 201 or response.status == '201')):
            print "Position / Trade could not be executed..."
            print response.body
        else:
            import time
            newTrades =[]
            v20AccountNew = None
            while(len(newTrades)==0):
                time.sleep(wait/1000.0)
                accResponse = api.account.get(v20Account.id)
                v20AccountNew = accResponse.get('account', '200')
                prevTradeIDs = map(lambda t: t.id, v20Account.trades)
                import pdb; pdb.set_trace()
                newTrades = [ t for t in v20AccountNew.trades if t.id not in prevTradeIDs and t.instrument == instrument ]
                if(len(newTrades)==0): print "new trade not executed yet - waiting again..."

            newPos = self.makeFromExistingTrade(pos.entryQuote, v20AccountNew, newTrades[0].id)
            return v20AccountNew, newPos
        return None









class Position(object):
    """ A Position we take, with a plan to take-profit and save-loss from an actual quote at which we take the position"""
    def __init__(self,forBUY, quote, size, saveLoss, takeProfit, fracTuple=(50.0,50.0)):
        self.forBUY = forBUY
        self.entryQuote = quote
        self.size = size
        self.saveLoss = saveLoss
        self.takeProfit = takeProfit

        if(self.forBUY):
            self.expLoss = self.entryQuote.ask.o - self.saveLoss
            self.expGain = self.takeProfit - self.entryQuote.ask.o
        else:
            self.expLoss = self.saveLoss - self.entryQuote.bid. o
            self.expGain = self.entryQuote.bid.o - self.saveLoss

        self.fracCurrent = fracTuple[0]
        self.fracExtreme = fracTuple[1]
        self.fracSum     = fracTuple[0]+fracTuple[1]

    def relevantPrice(self, currentQuote):
        if(self.forBUY):
            # if we close, we sell, we look at the bid price
            return (self.fracCurrent * currentQuote.bid.o + self.fracExtreme*currentQuote.bid.l)/self.fracSum
        else:
            # if we close, we buy, we look at the ask price
            return (self.fracCurrent*currentQuote.ask.o + self.fracExtreme*currentQuote.ask.h)/self.fracSum

    def __str__(self):

        return "[{}: {} units at {} with save-loss {} and take-profit {}]".format(\
            ("BUY" if(self.forBUY)else "SELL"),\
            self.size,
            (self.entryQuote.ask.o if(self.forBUY)else self.entryQuote.bid.o),\
            self.saveLoss,self.takeProfit)

    def timeToClose(self, currentQuote, rsiLow, rsiHigh):
        avgPrice = self.relevantPrice(currentQuote)

        if(self.forBUY):
            delta = self.entryQuote.ask.o - avgPrice

            if(avgPrice < self.saveLoss and not rsiHigh):
                return ('save-loss', 'close', -delta, 100*delta / self.expLoss)
            elif(avgPrice > self.takeProfit and not rsiLow):
                expGain = self.takeProfit - self.entryQuote.ask.o
                return ('take-profit', 'close', -delta, -100*delta/ self.expGain)
        else:
            delta = self.entryQuote.bid.o - avgPrice
            if(avgPrice > self.saveLoss and not rsiLow):
                expLoss = self.saveLoss - self.entryQuote.ask.o
                return ('save-loss', 'close', delta, 100*delta / self.expLoss)
            elif(avgPrice < self.takeProfit and not rsiHigh):
                return ('take-profit', 'close', delta, 100 * delta / self.expGain)

        return ('hold', 'hold', 0.0, 0.0)
