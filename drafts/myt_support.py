import datetime
import time
import dateutil.parser
import numpy as np
from forwardInstrument import Opportunity
import pdb

__dtconv = {} # a hash to remember conversion of time-strings to time-integers, so that we don't convert them twice (or over and over again)

def candleTime(c):
    """ translate the time-strings from oanda service candle-times (start time or end time of a candle) to time-integers.
         Note: this uses a cache. if you have very long running processes, the cache perhaps should be cleaned to save memory.
         No such provision yet."""
    if(not __dtconv.has_key(c.time)):
        __dtconv[ c.time ] = int(dateutil.parser.parse(c.time).strftime("%s"))
    return __dtconv[c.time]


def _find_(lam, coll):
    """return the first element that satisfy a lambda-criterion in a collection """
    for that in coll:
        ok = lam(that)
        if(ok): return that

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
    """ return the slice of neighboring magnitude to a slice. eg for M5, slices M1, M5, M15, H1 are considered of neighboring magnitudes"""
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
    """for a slice name (M1, M5, S1, D or W etc) of the oanda services, return the frequency in seconds"""
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



class TradeLoop(object):
    def __init__(self, api, accountId, instrumentName, freshFrequency_ms=1200000.0):
        self.api = api
        self.accountId = accountId
        self.instrumentName = instrumentName
        self.freshFrequency_ms = freshFrequency_ms
        self.accountPositions = []


    def initialize(self, posFactory=None):
        api = self.api
        accountId = self.accountId
        accountResp = api.account.get(accountId)
        instResp    = api.account.instruments(accountId)
        account = accountResp.get('account', '200')
        instruments = instResp.get('instruments','200')
        selectedInstruments = filter(lambda p: p.name == self.instrumentName, instruments)

        if(len(selectedInstruments)==0):
            raise ValueError("Select instrument not found for  account: " + args.instrumentName)
        zInstrument = selectedInstruments[0]

        pipLocation = zInstrument.pipLocation
        pipFactor = 10**(pipLocation)

        self.pipLocation = pipLocation
        self.pipFactor   = pipFactor
        self.displayPrecision = zInstrument.displayPrecision
        self.instrument = zInstrument
        print "Display Precision: {}".format(self.displayPrecision)
        self.account = account
        self.accountTime = time.time()
        if(posFactory is not None):
            self.refreshPositions(posFactory)


    def refreshPositions(self, positionFactory, force=False):
        self.refresh(force)
        freshPositions = []
        for pos in self.findPositionsRaw():
            tradeIDs = (pos.long.tradeIDs if(pos.long.tradeIDs is not None)else pos.short.tradeIDs)
            if(tradeIDs is not None):
                if(len(tradeIDs)==1):
                    ppos = positionFactory.makeFromExistingTrade(self.mkCandlestickTemplate(), self.account, tradeIDs[0])
                    freshPositions.append(ppos)
                else:
                    print "WARNING: too many tradeIDs for this position -- tough luck!"
                    raise ValueError("too many trades for single position?")
            else:
                print "(trade less position)"

        self.positions = freshPositions

    def mkCandlestickTemplate(self, withMid = False):
        tmpl = {"ask":{"c":0,"o":0,"l":0,"h":0},"bid":{"c":0,"o":0,"l":0,"h":0}}
        if(withMid):
            tmpl["mid"] = {"c":0,"o":0, "l":0,"h":0}

        return self.api.instrument.Candlestick.from_dict(tmpl, self.api)


    def findPositionsRaw(self):
        self.refresh()
        me = self.instrumentName

        return filter(lambda p: p.instrument == me, self.account.positions)

    def refresh(self, force=False, raiseX=True):
        if(force or time.time() - self.accountTime > self.freshFrequency_ms/1000.0):
            try:
                whenT = time.time()
                accountResp = self.api.account.get(self.accountId)
                self.account = accountResp.get('account', '200')
                self.accountTime = time.time()
            except:
                print "issue refreshing account ... skipping ..."
                if(force or raiseX): raise







class PositionFactory(object):
    """A factory class to prepare Position object"""
    def __init__(self, current=50,extreme=50):
        """instantiate a factory, with current/extreme ratio factors. Default 50 / 50.
           the current/extreme ratio factors help decide the likely price one would think they can expect from a candle.
           For example if a candle has a ask open=110, highest=120, lowest=105, close=105, with 50/50
           the expect price (on BUY) would be (110+120)/2 = 115. With 70/30, it would be (70*110+30*120)/(70+30) = 113. """
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
            npos = Position(forBUY, c, size, saveLoss, takeProfit, (self.current, self.extreme) )
            npos.tradeID = tradeID
            return npos

        return None

    def findTradeInAccount(self, looper, pos, force=False):
        looper.refresh(force)


    def executeTrade(self, looper, pos,wait=1200,noMore=5):
        """Execute a trade for a position, and a looper.
           On success, returns a 2-tuple: position object identified after successful trade, trade id
           When trade-id is None, the position object is the same as originally thought, the trade hasn't happened yet
           On failure, the 2-tuple is not returned, but None is returned. Some other issue at the broker (or with the order) have occurred"""

        kwargs = {}
        kwargs['instrument'] = looper.instrumentName
        # kwargs['price']=pos.entryQuote.ask.o if(pos.forBUY) else pos.entryQuote.bid.o
        kwargs['units']=(pos.size if(pos.forBUY) else -pos.size)
        #kwargs['timeInForce']='GTC'
        # saveLoss / takeProfit - user minimal minimumTrailingStopDistance to not annoy the broker
        mtsd = looper.instrument.minimumTrailingStopDistance
        sl = pos.saveLoss;tp=pos.takeProfit
        
        def nicepadding(x,prec):
            x = str(x)
            if(x.find(".")>0):
                x += "00000"
                return x[0:(x.index(".")+1+prec)]
            return x

        kwargs['stopLossOnFill'] = {"price": nicepadding(sl, looper.displayPrecision)}
        kwargs['takeProfitOnFill'] = {"price": nicepadding(tp, looper.displayPrecision)}
        print kwargs
        response = looper.api.order.market(
            looper.accountId,
            **kwargs
        )
        if(not(response.status == 201 or response.status == '201')):
            print "Position / Trade could not be executed..."
            print response.body
        else:
            newTrades =[]
            prevTradeIDs = map(lambda t: t.id, looper.account.trades)

            while(len(newTrades)==0):
                time.sleep(wait/1000.0)
                looper.refresh(True)
                newTrades = [ t for t in looper.account.trades if t.id not in prevTradeIDs and t.instrument == looper.instrumentName ]
                if(len(newTrades)==0):
                    noMore -= 1
                    if(noMore>0):
                        print "new trade not executed yet - waiting again..."
                    else:
                        print "new trade not executed yet - but continuing..."
                        return pos, None

            newPos = self.makeFromExistingTrade(pos.entryQuote, looper.account, newTrades[0].id)
            return newPos, newTrades[0].id
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
        self.tradeID = None

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

    def hasTrade(self):
        return self.tradeID is not None

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
