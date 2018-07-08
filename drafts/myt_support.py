import datetime,time
import dateutil.parser
import numpy as np
from forwardInstrument import Opportunity
from robologger import corelog
import pdb, re

""" Might support (myt_support) for Forex Trading Robots based OandA v20 API"""
__dtconv = {} # a hash to remember conversion of time-strings to time-integers, so that we don't convert them twice (or over and over again)


def getSortedCandles(loopr, kwargs):
    resp = loopr.api.instrument.candles(loopr.instrumentName, **kwargs)
    if(str(resp.status) != '200'): corelog.warning(resp.body)
    candles = resp.get('candles',200)
    candles.sort(lambda a,b: cmp(a.time, b.time))
    return candles


def getBacktrackingCandles(loopr, highCount, highSlice, lowSlice, lowAheadOfHigh=True):
    """ get high and low slice candles from OANDA api.
        This will provide the number of highCount high-slice candles and the low-slice candles in between.
        See getCachedBacktrackingCandles for details on other parameters"""
    highKW = { "count": highCount, "price":"BA", "granularity":highSlice}
    lowKW  = { "price":"BA", "granularity":lowSlice}

    xoff = 1 if(not lowAheadOfHigh) else 0

    corelog.debug(highKW)
    highCandles = getSortedCandles(loopr, highKW)
    # when not lowAheadOfHigh starts with an empty backtracking list, otherwise starts with single high candle and no low candles
    backtracking = [ (highCandles[0],[]) ] if(not lowAheadOfHigh) else []
    for i in range(len(highCandles)-xoff):
        a = highCandles[i]
        lowKW["fromTime"] = a.time
        if(i+1<len(highCandles)):
            b = highCandles[i+1]
            lowKW["toTime"] = b.time
        corelog.debug(lowKW)
        lowCandles = getSortedCandles(loopr, lowKW)
        hc = highCandles[i+xoff]
        item = (hc, lowCandles)
        backtracking.append(item)

    return backtracking


def getCachedBacktrackingCandles(looper, dir, highSlice, lowSlice, since, till, lowAheadOfHigh=True):
    """ use cached data to provide candles for a high-slice and low-slice, on a [since,till] time range
        highSlice must be higher than lowSlice (e.g H1 for high slice, M1 for low slice)
        What is returned is a list L of pairs ([0],[1]), where the 1st element of the pair L[n][0] is the single high candle,
        and the 2nd element of the pair L[n][1] is the list of low candles contained under L[n][0].
        when lowAheadOfHigh is true, then all elements in L[n][1] have a time that is before L[n][0].
        When lowAheadOfHigh is false, then all elemetns in L[n+1][1] have a time that is before L[n][0]
        Example times for M15 vs M5 slices:
        lowAheadOfHigh:  [ (01:15:00, [ 01:15:00, 01:20:00, 01:25:00 ] ]), (01:30:00, [01:30:00, 01:35:00, 01:40:00 ]), ...]
        not lowAheadOfHigh: [ (01:15:00, [ 01:00:00, 01:05:00, 01:10:00 ] ]), (01:30:00, [01:15:00, 01:20:00, 01:25:00 ]), ...] """

    from candlecache import SliceRowIterator
    hIterator = SliceRowIterator(dir, looper.instrumentName, highSlice, since, till, looper.api)
    lIterator = SliceRowIterator(dir, looper.instrumentName, lowSlice, since, till, looper.api)

    highCandles = [c for c in hIterator]
    if(len(highCandles)<2):
        raise ValueError("cannot work on so few high slice candles...")

    hi =0
    backtracking = []
    pouch = []
    hitime = highCandles[hi].time
    hntime = highCandles[hi+1].time

    xoff = 1 if(not lowAheadOfHigh) else 0

    if(not lowAheadOfHigh):
        yup = (highCandles[0], [])
        backtracking.append(yup)
    
    for lc in lIterator:
        ctime = lc.time
        ci = cmp(ctime, hitime)
        cn = cmp(ctime, hntime)
        if(ci<0):
            continue
        elif(ci>=0 and cn<0):
            pouch.append(lc)
        elif(cn>=0):
            if(hi+xoff<len(highCandles)):
                yup = ( highCandles[hi+xoff], pouch )
                backtracking.append(yup)
            pouch = [ lc ]
            hitime = hntime
            hi += 1
            if(hi+1>=len(highCandles)):
                hntime = "9999-99-99T99:99:99.999999999Z"
            else:
                hntime = highCandles[hi+1].time

    if(lowAheadOfHigh):
        yup = ( highCandles[-1], pouch )
        backtracking.append(yup)


    return backtracking



def getLiveCandles(looper, depth, highSlice, lowSlice, price = "BA"):
    from livecandlehierarchy import DualLiveCandles
    dlc =  DualLiveCandles(looper, highSlice, depth, lowSlice, price, complete_policy = "both")
    return dlc;




def trailSpecsFromStringParam(paramValue, msgHead="trailing-stop-specs"):
    trailSpecs = []
    for spec in paramValue.split(","):
        mm = re.match(r"(\d+\.?\d*):(\d+\.?\d*)", spec)
        if(mm is None):
            raise ValueError("{} must be n:p, numerics, or n:p,m:q,... - {} is incompatible".format(msgHead,spec))
        else:
            mm_n = float(mm.groups()[0])
            mm_p = float(mm.groups()[1])
            trailSpecs.append( (mm_n, mm_p) )
    trailSpecs.sort(lambda x,y: cmp(x[0],y[0]))
    if(len(trailSpecs)>1):
        if(trailSpecs[0][0] == trailSpecs[1][0]):
            raise ValueError("{} cannot mention the same trigger level more than once".format(msgHead))
        for i in range(len(trailSpecs)):
            if(i>0 and trailSpecs[i][1]>= trailSpecs[i-1][1]):
                raise ValueError("{} cannot specify stop-loss distance that are decreasing when trigger level increase: {},{} vs {},{}".format(msgHead, trailSpecs[i-1][0],trailSpecs[i-1][1], trailSpecs[i][0],trailSpecs[i][1]))
    return trailSpecs

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
    bidTrigger = mbid - trigger*mspread + sdf*sdev
    askTrigger = mask + trigger*mspread - sdf*sdev

    return mbid,mask, mspread, sdev, bidTrigger, askTrigger





class TradeLoop(object):
    def __init__(self, api, accountId, instrumentName, freshFrequency_ms=120000.0):
        self.api = api
        self.accountId = accountId
        self.instrumentName = instrumentName
        self.freshFrequency_ms = freshFrequency_ms
        self.positions = []
        self.simulation = False
        self.simulatedPositions = []


    def initialize(self, posFactory=None, instrumentDict = None):
        api = self.api
        accountId = self.accountId

        if(instrumentDict is None) :
            accountResp = api.account.get(accountId)
            instResp    = api.account.instruments(accountId)
            account = accountResp.get('account', '200')
            instruments = instResp.get('instruments','200')
            selectedInstruments = filter(lambda p: p.name == self.instrumentName, instruments)

            if(len(selectedInstruments)==0):
                raise ValueError("Select instrument not found for  account: " + self.instrumentName)
            zInstrument = selectedInstruments[0]
        else:
            from candlecache import InstrumentCache, AccountCache
            zInstrument = InstrumentCache(instrumentDict)
            account = AccountCache()

        pipLocation = zInstrument.pipLocation
        displayPrecision = zInstrument.displayPrecision

        pipFactor = 10**(pipLocation)

        self.pipLocation = pipLocation
        self.pipFactor   = pipFactor
        self.displayPrecision = displayPrecision
        self.instrument = zInstrument
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
                for tradeID in tradeIDs:
                    ppos = positionFactory.makeFromExistingTrade(self.mkCandlestickTemplate(), self.account, tradeID)
                    freshPositions.append(ppos)
            else:
                corelog.debug("(trade less position)")

        # make sure the position array is sorted by openTime
        freshPositions.sort(lambda a,b: cmp(a.entryQuote.time, b.entryQuote.time))
        self.positions = freshPositions

    def mkCandlestickTemplate(self, withMid = False, wTime = None):
        tmpl = {"ask":{"c":0,"o":0,"l":0,"h":0},"bid":{"c":0,"o":0,"l":0,"h":0}}
        if(withMid):
            tmpl["mid"] = {"c":0,"o":0, "l":0,"h":0}

        if(wTime is not None):
            tmpl["time"] = wTime

        return self.api.instrument.Candlestick.from_dict(tmpl, self.api)


    def findPositionsRaw(self):
        self.refresh()
        me = self.instrumentName

        return filter(lambda p: p.instrument == me, self.account.positions)

    def refreshIsDue(self):
        return time.time() - self.accountTime > self.freshFrequency_ms/1000.0

    def refresh(self, force=False, raiseX=True):
        if(self.simulation): return

        if(force or self.refreshIsDue()):
            try:
                whenT = time.time()
                accountResp = self.api.account.get(self.accountId)
                self.account = accountResp.get('account', '200')
                self.accountTime = time.time()
            except:
                corelog.critical( "issue refreshing account ... skipping ..." )
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

    def make(self,forBUY, quote,size,saveLoss, takeProfit, trailingTriggerPrice=None, trailingDistance=None):
        pos= Position(forBUY,quote,size,saveLoss,takeProfit, (self.current, self.extreme))
        pos.trailingStopTriggerPrice = trailingTriggerPrice
        pos.trailingStopDesiredDistance = trailingDistance
        return pos

    def makeFromExistingTrade(self, quoteTmpl, v20Account, tradeID):
        trade = _find_(lambda t: t.id == tradeID, v20Account.trades)
        orders = (filter(lambda t: t.tradeID == tradeID, v20Account.orders))
        tp0 = _find_(lambda t: t.type == 'TAKE_PROFIT', orders)
        sl0 = _find_(lambda t: t.type == 'STOP_LOSS', orders)
        tsl0 = _find_(lambda t: t.type == 'TRAILING_STOP_LOSS', orders)
        if(trade is not None and tp0 is not None and sl0 is not None):
            iu = float(trade.currentUnits)
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
            npos.saveLossOrderId = sl0.id
            npos.takeProfitOrderId = tp0.id
            if(tsl0 is not None):
                npos.trailingStopLossOrderId = tsl0.id
                npos.trailingStopValue = tsl0.trailingStopValue
                npos.trailingStopDistance = tsl0.distance
            return npos

        return None

    def findTradeInAccount(self, looper, pos, force=False):
        looper.refresh(force)

    def nicepadding(self, x,prec):
        x = str(x)
        if(x.find(".")>0):
            x += "00000"
            return x[0:(x.index(".")+1+prec)]
        return x

    def executeTrailingStop(self, looper, pos, wait=1200, noMore=5):
        """Bring an executed position (with tradeID) to be set with the expected trailing-stop parameters"""
        mtsd = looper.instrument.minimumTrailingStopDistance
        if(pos.tradeID is not None):
            distance = pos.trailingStopDesiredDistance
            if(distance<mtsd):
                distance = mtsd
            # price = (pos.trailingStopValue+distance*(1 if(pos.forBUY) else -1)) if(pos.trailingStopValue is not None) else pos.trailingStopTriggerPrice
            distance = self.nicepadding(distance, looper.displayPrecision)
            # price    = self.nicepadding(price, looper.displayPrecision)
            tslargs = {"tradeID": str(pos.tradeID), "distance":  distance }
            corelog.debug(tslargs)
            respTSL = None
            if(pos.trailingStopLossOrderId is None):
                respTSL = looper.api.order.trailing_stop_loss(looper.accountId,  **tslargs)
            else:
                corelog.debug( "replace order {}", pos.trailingStopLossOrderId)
                respTSL = looper.api.order.trailing_stop_loss_replace(looper.accountId,  pos.trailingStopLossOrderId, **tslargs)
            corelog.debug("status code:{}\nbody:{}",respTSL.status, respTSL.body)
            if(str(respTSL.status)=='201'):
                time.sleep(float(wait)/1000.0)
                looper.refreshPositions(self,True)
        else:
            raise RuntimeError("cannot call executeTrailingStop on a position that has not been entered/traded")

    def executeClose(self, looper, pos, size=None, wait=1200, noMore=5):
        """ when the close executes, this returns a pair (position, trade-id).
            If the position is actually closed, then the position is returned as None, so what is returned is (None, trade-id).
            If the close fails, None is returned """
        kwargs = {}
        if(size is not None):
            fsize = float(size)
            if(pos.size>fsize):
                kwargs["units"] = str(size)
            else:
                raise ValueError("Cannot use executeClose to with a size greater than current position: {} is great than current {}".format(size, pos.size))

        response = looper.api.trade.close(looper.accountId, pos.tradeID, **kwargs)
        if(response.status.code == "200" or response.status.code ==200):
            corelog.debug("Closing trade {} with {} was successful".format(pos.tradeID, kwargs))
        else:
            corelog.critical("Unable to close trade: {}\n{}".format(response.status, response.body))
            return None


        myTrade = None
        while(myTrade is None and noMore>0):
            time.sleep(wait/1000.0)
            looper.refreshPositions(self, force=True)
            myTrades = filter(lambda t: t.id == pos.tradeID, looper.account.positions)
            if(len(myTrades)>0):
                if(float(myTrades[0].currentUnits) < float(pos.size)):
                    myTrade = myTrades[0]
            else:
                if(size is None):
                    # the position is not on the account (not open, but gone, closed) and we didn't pass a size, so it is all good.
                    break
                else:
                    noMore -= 1

        if(myTrade is not None):
            newPosVersion = self.makeFromExistingTrade(pos.entryQuote, looper.account, myTrade.id)
            return newPosVersion, myTrade.id
        else:
            return None, pos.tradeID




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
        corelog.debug(kwargs)
        response = looper.api.order.market(
            looper.accountId,
            **kwargs
        )
        if(not(response.status == 201 or response.status == '201')):
            corelog.critical( "Position / Trade could not be executed...")
            corelog.critical(response.body)
        else:
            newTrades =[]
            prevTradeIDs = map(lambda t: t.id, looper.account.trades)

            while(len(newTrades)==0):
                time.sleep(wait/1000.0)
                looper.refreshPositions(self, force=True)
                newTrades = [ t for t in looper.account.trades if t.id not in prevTradeIDs and t.instrument == looper.instrumentName ]
                if(len(newTrades)==0):
                    noMore -= 1
                    if(noMore>0):
                        corelog.info("new trade not executed yet - waiting again...")
                    else:
                        corelog.warning("new trade not executed yet - but continuing...")
                        return pos, None

            newPos = self.makeFromExistingTrade(pos.entryQuote, looper.account, newTrades[0].id)
            # if(pos.trailingSpecs is not None):
            #     newPos.calibrateTrailingStopLossDesireForSteppedSpecs(pos.traillingSpecs,
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
        self.trailingStopTriggerPrice = None    # price where the trailingStop will be starting
        self.trailingStopDesiredDistance = 0    # distance that is desired for the trailing stop - as soon as it is triggered
        self.medianSpread = None                # medianSpread is record when we calibrate - it may be used if the position is in trailing-stop step mode.

        if(self.forBUY):
            self.expLoss = self.entryQuote.ask.o - self.saveLoss
            self.expGain = self.takeProfit - self.entryQuote.ask.o
        else:
            self.expLoss = self.saveLoss - self.entryQuote.bid. o
            self.expGain = self.entryQuote.bid.o - self.takeProfit

        self.fracCurrent = fracTuple[0]
        self.fracExtreme = fracTuple[1]
        self.fracSum     = fracTuple[0]+fracTuple[1]
        self.tradeID = None                  # tradeID for the trade for this position (once executed)
        self.saveLossOrderId = None          # stop loss order id for the trade for this position  (once executed)
        self.takeProfitOrderId = None        # take profit order if for the trade for this position (once executed)
        self.trailingStopLossOrderId = None   # current orderId we are tracking with the account for this position, if engaged / triggered
        self.trailingStopValue       = None   # if trailing stop is engaged, this is the trailingStop value for it
        self.trailingStopDistance    = None   # if the trailing stop  is engaged, this is the trialing stop distance
        self.trailSpecs              = None   # if we are i "traiing stop step mode", these are the steps, an array of 2-uples. t[0] = price triggering the level, t[1] = level (distance) - these are expressed as factors of the median spread. (t[0] is above(buy)/below(sell) the trade price)
        self.trailingStopNeedsReplacement = False # set to true whenever we realize the trailing stop conditions have changed


    # def calibrateTrailingStopLossDesire(self, trailStart, trailDistance):
    #     if(self.trailSpecs is not None): raise ValueError("cannot call calibrateTrailingStopLossDesire when position is in step-mode")
    #     if(self.forBUY):
    #         profit = self.takeProfit - self.entryQuote.ask.o
    #         self.trailingStopTriggerPrice = self.entryQuote.ask.o + trailStart*profit
    #         self.trailingStopDesiredDistance =  trailDistance*profit
    #     else:
    #         profit = self.entryQuote.bid.o - self.takeProfit
    #         self.trailingStopTriggerPrice = self.entryQuote.bid.o - trailStart*profit
    #         self.trailingStopDesiredDistance = trailDistance*profit


    def calibrateTrailingStopLossDesireForSteppedSpecs(self, currentQuote, trailSpecs, mspread, minimumTrailingStopDistance):
        """ calibrate the Position trailing stop details for the new current quote.
            TrailSpecs and mspread can be passed as None if you just want to use the latest calibrated values for trailSpecs and mspread
            currentquote can be passed as None to calibrate the position at the very beginning."""

        if(currentQuote is None and (trailSpecs is None or mspread is None)):
            raise ValueError("need either curentQuote or trailSpecs + mspread")

        if(mspread is None):
            mspread = self.medianSpread
        else:
            self.medianSpread = mspread

        self.minimumTrailingStopDistance = minimumTrailingStopDistance

        plusMinus = 1.0 if(self.forBUY) else -1.0

        if(currentQuote is None):
            self.trailingStopDesiredDistance = mspread*trailSpecs[0][1]
            self.trailingStopTriggerPrice    = mspread*trailSpecs[0][0]* plusMinus + (self.entryPrice())
            self.trailSpecs               = trailSpecs
            return

        if(trailSpecs is None): trailSpecs = self.trailSpecs
        currentDistance = self.trailingStopDistance
        unitProfit = self.quoteProfit(currentQuote, True)
        if(unitProfit>0.0):
            okSpec = None
            for spec in trailSpecs:
                if(unitProfit>mspread*spec[0] and (currentDistance is None or mspread*spec[1]<currentDistance)):
                    okSpec = spec
                elif(okSpec is not None):
                    break

            if(okSpec is None): return

            newDesiredDistance = round(mspread*okSpec[1],7)
            if(newDesiredDistance<minimumTrailingStopDistance): newDesiredDistance = minimumTrailingStopDistance

            if(newDesiredDistance < self.trailingStopDesiredDistance or self.trailingStopDesiredDistance<=0):
                corelog.info("new desired distance {} spreads = {}".format(okSpec[1], newDesiredDistance))
                self.trailingStopDesiredDistance = newDesiredDistance
                self.trailingStopNeedsReplacement = True
            if(self.trailingStopDistance is not None):
                # then trailing stop is already engage, note a needed replacement only if trailingStopDistance is different than new distance, the moving stop value is taken care by the broker
                self.trailingStopNeedsReplacement = (newDesiredDistance != round(self.trailingStopDistance,7))
                corelog.info("current trailing stop distance:%s, new desired distance:%s, replacement-needed:%s",
                              self.trailingStopDistance, newDesiredDistance, self.trailingStopNeedsReplacement)
            return


    def entryPrice(self):
        """ price trade when trade was entered"""
        return self.entryQuote.ask.o if(self.forBUY) else self.entryQuote.bid.o

    def quoteProfit(self, currentQuote, normalized=True):
        p = self.relevantPrice(currentQuote)
        profit = (p - self.entryPrice()) *(1.0 if(self.forBUY) else -1.0)
        if(not normalized):
            profit = profit * self.size
        return profit



    def relevantPrice(self, currentQuote, highOnly=False):
        """return relevantPrice to estimate for a position, given current candle.
           highOnly: to find the relevant price that has the highest impact on profit / stop loss"""
        if(self.forBUY):
            # if we close, we sell, we look at the bid price
            if(highOnly): return currentQuote.bid.h
            return (self.fracCurrent * currentQuote.bid.o + self.fracExtreme*currentQuote.bid.l)/self.fracSum
        else:
            # if we close, we buy, we look at the ask price
            if(highOnly): return currentQuote.ask.l
            return (self.fracCurrent*currentQuote.ask.o + self.fracExtreme*currentQuote.ask.h)/self.fracSum


    def __str__(self):

        if(self.trailingStopValue is None):
            return "[{}: {} units at {} with save-loss {} and take-profit {}, tstop-trigger:{}, *tstop:{} / {}]".format(\
                ("BUY" if(self.forBUY)else "SELL"),\
                self.size,
                (self.entryQuote.ask.o if(self.forBUY)else self.entryQuote.bid.o),\
                self.saveLoss,self.takeProfit, self.trailingStopTriggerPrice, self.trailingStopValue, self.trailingStopDesiredDistance)
        else:
            return "[{}: {} units at {} with save-loss {} and take-profit {}, tstop-trigger:{}, tstop:{} / {}]".format(\
                ("BUY" if(self.forBUY)else "SELL"),\
                self.size,
                (self.entryQuote.ask.o if(self.forBUY)else self.entryQuote.bid.o),\
                self.saveLoss,self.takeProfit, self.trailingStopTriggerPrice, self.trailingStopValue, self.trailingStopDistance)


    def hasTrade(self):
        return self.tradeID is not None

    def updateTrailingStopValue(self, currentQuote):

        avgPrice = self.relevantPrice(currentQuote)

        if(self.forBUY):
            if(self.trailingStopValue is not None and self.trailingStopValue+self.trailingStopDistance<avgPrice):
                self.trailingStopValue = avgPrice - self.trailingStopDistance
                corelog.info("updated trailing stop value to %f with distance %f",self.trailingStopValue, self.trailingStopDistance)
        else:
            if(self.trailingStopValue is not None and self.trailingStopValue-self.trailingStopDistance>avgPrice):
                self.trailingStopValue = avgPrice+self.trailingStopDistance
                corelog.info("updated trailing stop value to %f with distance %f",self.trailingStopValue, self.trailingStopDistance)
        


    def expectedTrailingStopValue(self, currentQuote):
        """for current quote, and current trailing-stop conditions, what should be the trailing-stop value? """
        bestPrice = self.relevantPrice(currentQuote, True)
        if(self.forBUY):
            if(self.trailingStopDistance>0.0 and
                ( (self.trailingStopValue is None and bestPrice >= self.trailingStopTriggerPrice) or
                  (self.trailingStopValue is not None and bestPrice > (self.trailingStopValue+self.trailingStopDistance)) )):
                return bestPrice - self.trailingStopDistance
        else:
            if(self.trailingStopDistance>0.0 and
                 ( (self.trailingStopValue is None and bestPrice <= self.trailingStopTriggerPrice) or
                   (self.trailingStopValue is not None and bestPrice < (self.trailingStopValue -self.trailingStopDistance)) )):
                return bestPrice + self.trailingStopDistance

        return self.trailingStopValue


    def setTrailingStop(self,currentQuote):
        """ set original trailing stop conditions, if trail stop is satisfied - call only once!"""
        avgPrice = self.relevantPrice(currentQuote)

        if(self.tradeID is not None):
            raise RuntimeError("cannot call setTrailingStop on executed position - please use 'executeTrailingStop'")
        if(self.trailingStopDesiredDistance<=0.0):
            raise RuntimeError("cannot call setTrailingStop when desire stop-loss distance is not set, or negative")

        if(self.forBUY):
            if(self.trailingStopDesiredDistance>0.0 and avgPrice >= self.trailingStopTriggerPrice and self.trailingStopValue is None):
                self.trailingStopValue = avgPrice - self.trailingStopDistance
                self.trailingStopDistance = self.trailingStopDesiredDistance
        else:
            if(self.trailingStopDesiredDistance>0.0 and avgPrice <= self.trailingStopTriggerPrice and self.trailingStopValue is None):
                self.trailingStopValue  = avgPrice + self.trailingStopDesiredDistance
                self.trailingStopDistance = self.trailingStopDesiredDistance




    def timeToClose(self, currentQuote, strategyMaker):
        """is it time to close (take-profit, save-loss, stop-loss triggered), or update stop-loss-value?"""
        avgPrice = self.relevantPrice(currentQuote)
        newStopValue = self.expectedTrailingStopValue(currentQuote)
        benefRatio = 0.0
        lossRatio = 0.0
        holdRatio = 0.0

        if(newStopValue is not None and self.trailingStopValue is not None):
            if((self.forBUY and newStopValue < 0.9999*self.trailingStopValue) or
               (not self.forBUY and 0.9999*newStopValue > self.trailingStopValue)):
               corelog.critical( "WARNING: stop value calculations are retrograde!" )
               import pdb; pdb.set_trace()
               newStopValue2 = self.expectedTrailingStopValue(currentQuote)

        # import pdb; pdb.set_trace()

        if(self.forBUY):
            delta = avgPrice - self.entryQuote.ask.o
            benefRatio = 100*delta/self.expGain
            lossRatio  = -100*delta/self.expLoss
            # whe losing, use lossRatio and make it negative
            holdRatio  = -lossRatio if(delta<0)else benefRatio

            if(avgPrice < self.saveLoss ):
                return ('save-loss', 'close', delta, lossRatio)
            elif(avgPrice > self.takeProfit):
                return ('take-profit', 'close', delta, benefRatio)
            elif(self.trailingStopValue is None and newStopValue is not None):
                return ('trailing-stop', 'trailing-stop', delta, holdRatio)
            elif(self.trailingStopValue is not None and newStopValue is not None and round(newStopValue,7) != round(self.trailingStopValue,7)):
                return ('trailing-stop', 'trailing-progress', delta,holdRatio)
            elif(self.trailingStopValue is not None and self.trailingStopValue>avgPrice):
                delta = self.trailingStopValue - self.entryQuote.ask.o
                return ('trailing-stop', 'close', delta, benefRatio)

        else:

            delta = self.entryQuote.bid.o - avgPrice
            benefRatio = 100*delta/self.expGain
            lossRatio  = -100*delta/self.expLoss
            holdRatio  = benefRatio if(delta>0)else -lossRatio

            if(avgPrice > self.saveLoss ):
                expLoss = self.saveLoss - self.entryQuote.ask.o
                return ('save-loss', 'close', delta, lossRatio)
            elif(avgPrice < self.takeProfit ):
                return ('take-profit', 'close', delta, benefRatio)
            elif(newStopValue is not None and self.trailingStopValue is None):
                return ('trailing-stop', 'trailing-stop', delta, holdRatio)
            elif(self.trailingStopValue is not None and newStopValue is not None and round(newStopValue,7) != round(self.trailingStopValue,7)):
                return ('trailing-stop', 'trailing-progress',delta,holdRatio)
            elif(self.trailingStopValue is not None and self.trailingStopValue < avgPrice):
                delta = self.entryQuote.bid.o - self.trailingStopValue
                return ('trailing-stop', 'close', delta, benefRatio)

        if(self.trailingStopNeedsReplacement):
            return ('trailing-stop', 'trailing-update', delta, holdRatio)

        return ('hold', 'hold', delta, holdRatio)
