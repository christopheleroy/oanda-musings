
import logging


class RSISentimentAnalyzer(object):
    def __init__(self, rsiAlwaysOK = False, rsiInverted=False):
        self.rsiAlwaysOK = rsiAlwaysOK
        self.rsiInverted = rsiInverted

    def confirm(self, forBUY, rsiMaker):
        rsiSwitch = forBUY if(not self.rsiInverted) else not forBUY
        rsiOK = self.rsiAlwaysOK or (rsiSwitch and rsiMaker.RSI < rsiMaker.oscLow*1.2) or (rsiMaker.RSI>rsiMaker.oscHigh*0.8 and not rsiSwitch)
        if(rsiOK):
            return True, rsiMaker.RSI, ""
        else:
            return False, rsiMaker.RSI, ("Hint to add extra trade for RISK management is pre-empted by RSI: {}".format(rsiMaker.RSI))


class RiskManagementStrategyBasicOption(object):
    def __init__(self, lossTrigger, sizeFactor, reRisk, profit, flipped=False, sentimentAnalyzer=None):

        self.lossTrigger = lossTrigger
        self.lossTrigger = lossTrigger
        self.sizeFactor  = sizeFactor
        self.reRisk      = reRisk
        self.profit      = profit
        self.flipped     = flipped
        if(sentimentAnalyzer is None):
            logging.debug("risk-management-basic-option with lossTrigger={}, sizeFactor={}, profit={}, re-risk={}".format(lossTrigger, sizeFactor, profit, reRisk));
            self.sentimentAnalyzer = RSISentimentAnalyzer()
        else:
            logging.debug("risk-management-basic-option with lossTrigger={}, sizeFactor={}, profit={}, re-risk={} and specific sentiment-analyzer".format(lossTrigger, sizeFactor, profit, reRisk));
            self.sentimentAnalyzer = sentimentAnalyzer


    def triggered(self, mspread, currentDelta, currentQuote):
        return  currentDelta < - self.lossTrigger*mspread

    def confirm(self, forBUY, strategyMaker):
        # if we're flipped, for a BUY order, we want to confirm if it is ok to flip to a SELL...
        forBUYactual = (not forBUY) if(self.flipped) else (forBUY)
        return self.sentimentAnalyzer.confirm(forBUYactual, strategyMaker)


class RiskManagementStrategy(object):
    def __init__(self):
        self.warningsSentiment  = 0
        self.warningsSize = 0

        self.options = []


    def _addOption(self,option):
        self.options.append(option)


    def watchTrigger(self, mspread, currentDelta, currentQuote, rsiMaker, parentPos, posMaker, trailStart, trailDistance,
                    currentlyEngagedSize, maxEngagedSize):
        for opt in self.options:
            if(opt.triggered(mspread, currentDelta, currentQuote)):
                # so, supposed parentPos is in loss, we're taking a position that is going to be a buy
                # at a lower value than parent pos to hope to get a little less loss ...
                # but we won't BUY at an overbought position
                feelingOK, val, msg = opt.confirm(parentPos.forBUY, rsiMaker)
                if(not feelingOK):
                    if(self.warningsSentiment < 3 or self.warningsSentiment % 3 == 0):
                        logging.warning(msg)
                    self.warningsSentiment +=1
                elif(maxEngagedSize <= currentlyEngagedSize):
                    if(self.warningsSize<2 or self.warningsSize % 30 == 0): logging.warning("Risk-management position is not attempted because engaged size was reached")
                    self.warningSize+=1
                else:
                    c = currentQuote
                    size = parentPos.size * opt.sizeFactor
                    sizeMax = (maxEngagedSize - currentlyEngagedSize)
                    if(opt.flipped):
                        afterFlip = currentlyEngagedSize - parentPos.size - size
                        if(afterFlip<0):
                            if(afterFlip < -maxEngagedSize):
                                # ces - parSize - size < -mes ==> size > ces + mes - parSize
                                sizeMax = currentlyEngagedSize + maxEngagedSize - parentPos.sizeMax
                            else:
                                sizeMax = size

                    if(size>sizeMax):
                        logging.warning("risk-management position, size {} reduced to {}, because of max-size limit".format(size, sizeMax))
                        size=sizeMax

                    self.warningsSize = 0
                    self.warningsSentiment  = 0
                    forBUY = parentPos.forBUY if(not opt.flipped) else (not parentPos.forBUY)
                    relevantRisk = (c.bid.o - opt.reRisk * mspread) if(forBUY) else (c.ask.o + opt.reRisk*mspread)
                    relevantProfit = (c.ask.o + opt.profit * mspread) if (forBUY) else (c.bid.o - opt.profit*mspread)
                    trailStopTrigger = (c.ask.o + trailStart * mspread) if(forBUY) else (c.bid.o - trailStart*mspread)
                    ##

                    forBUY = parentPos.forBUY

                    benef = 0.0
                    benefRatio = 0.0
                    todo = "take-position"
                    # with oanda API we can close a 1 lot BUY and open a 2 lot SELL by placing a 3 lot SELL.
                    # so we play this trick:
                    if(opt.flipped):
                        forBUY = not forBUY
                        size += parentPos.size
                        # how much do we lose on parenPos?
                        benef = parentPos.quoteProfit(currentQuote, True)
                        benefRatio = 100.0*benef/parentPos.expLoss
                        todo = "flip-position"

                    pos2 = posMaker.make(forBUY, currentQuote,
                                          size, relevantRisk, relevantProfit,
                                          trailStopTrigger, trailDistance*mspread)
                    logging.critical("{} - recommend taking risk-management position ({}) size={}, at {} with take-profit:{} and save-loss:{} (RSI:{})".format(
                                  currentQuote.time, ("BUY" if(forBUY) else "SELL"), size,
                                  (c.bid.o if(forBUY) else c.ask.o),
                                  relevantProfit, relevantRisk, val))
                    if(opt.flipped):
                        pos2 = (pos2, parentPos)

                    return ("risk-mgt-trigger", todo, benef, benefRatio, val, pos2)





    @staticmethod
    def parse(desc, robot, rmArgs= {}, bark=""):
        import re
        descs = desc.split(",")
        them = []
        rgx = re.compile(r"^(\d+.?\d*|sr\d+.?\d*):([fxpr\d\.]+)$")
        sgx = re.compile(r"(\d+\.?\d*)([fxpr])")
        for dx in descs:
            dx = dx.lower()
            alternatives = dx.split("/")
            rmx_dx = RiskManagementStrategy()
            for d in alternatives:
                if(rgx.match(d)):
                    sr = False # support and resistance?
                    lt_x = rgx.match(d).groups()[0]
                    if(lt_x.startswith("sr")):
                        lt_x = lt_x[2:]
                        sr=True
                    lt = float(lt_x)
                    rem = rgx.match(d).groups()[1] # rem: remaining string to parse (substring of d)
                    mapped = {}
                    while(len(rem)>0):
                        bam = sgx.match(rem)
                        if(bam is None):
                            raise ValueError("{} - cannot parse {} as risk-management specs, fails on {}".format(bark, d, rem))
                        xrp = bam.groups()[1]
                        nnn = float(bam.groups()[0])
                        if(nnn<=0):
                            raise ValueError("{} - cannot use zero in risk management specs, fails on {}". format(bark,ren))
                        if(mapped.has_key(xrp)):
                            raise ValueError("{} - cannot specify {} multiply time in risk-mgt-specs, fails on {}".format(bark, xrp, rem))
                        mapped[xrp]=nnn
                        st = bam.start()
                        en = bam.end()
                        rem = rem[0:st] + rem[en:]
                    sf = mapped['x'] if(mapped.has_key('x')) else (mapped['f'] if(mapped.has_key('f')) else 2.0)
                    flipped = mapped.has_key('f')
                    if(mapped.has_key('f') and mapped.has_key('x')):
                        raise ValueError("{} - parsing {}, cannot specify both x (extend by factor) and f (flip trade)".format(bark, rem))
                    pr = mapped['p'] if(mapped.has_key('p')) else (lt/sf)
                    ri = mapped['r'] if(mapped.has_key('r')) else (lt/sf)
                    sal = robot.makeSentimentAnalyzer(rmArgs)
                    rmx_dx._addOption( RiskManagementStrategyBasicOption( lt, sf, ri, pr, flipped, sal) )
                    logging.info("parsed risk-management-option {} as lossTrigger={}, sizeFactor={}, profit={}, re-risk={}".format(d, lt, sf, pr, ri))
                else:
                    raise ValueError("{} - cannot parse risk-management spec {}".format(bark,d))
            logging.info("adding risk-management-spec made of {} option{} (from :{})".format(len(rmx_dx.options), ("s" if(len(rmx_dx.options)>1) else ""), dx))
            them.append( rmx_dx )

        return them


class TradeStrategy(object):

    def __init__(self, trigger, profit, risk, depth, select, defaultSize, highSlice, lowSlice, rsiSpecs, sdf, trailingSpecs):
        self.trigger = trigger
        self.profit  = profit
        self.risk    = risk
        self.depth   = depth
        self.select  = select
        self.defaultSize= defaultSize
        self.highSlice = highSlice
        self.lowSlice  = lowSlice
        self.sdf     = sdf
        self.trailSpecs = trailingSpecs
        self.rsiSpecs = rsiSpecs
        self.simulation = True
        self.lastTick = None
        self.riskManagement = []
        self.maxEngagedSize = defaultSize
        self.rsiMode = "+"






    def initialize(self):
        import oscillators
        import teeth

        self.queue = teeth.MovingQueue(self.depth)
        self.rsiHighMaker = oscillators.OscillatorCalculation(self.rsiSpecs)
        self.rsiLowMaker  = oscillators.OscillatorCalculation(self.rsiSpecs)

        self.mspread = None
        self.mbid = None
        self.mask = None
        self.sdev=None
        self.askTrigger = None
        self.bidTrigger = None
        skipIdenticalCandles = (lambda c1,c2:  c1.time >= c2.time)

        self.queue.skipper = skipIdenticalCandles
        self.rsiHighMaker.setSkipper(skipIdenticalCandles)
        self.rsiLowMaker.setSkipper(skipIdenticalCandles)


    def makeSentimentAnalyzer(self, rmArgs):
        """ for Rollover / Insurance : sentiment analyzer """
        return RSISentimentAnalyzer(**rmArgs)

    def digestHighCandle(self, candle):
        self.queue.add(candle)
        self.rsiHighMaker.add(candle)
        self.secretSauce()

    def secretSauce(self):
        import numpy as np
        if(self.queue.full()):
            spreads = map(lambda x: x.ask.o - x.bid.o, self.queue)
            bids = map (lambda x: x.bid.o, self.queue)
            asks = map (lambda x: x.ask.o, self.queue)
            self.sdev   = np.std(bids)
            self.mspread = np.median(spreads)
            self.mbid = np.median(bids)
            self.mask = np.median(asks)
            bidTrigger = self.mbid + self.trigger*self.mspread - self.sdf*self.sdev
            askTrigger = self.mask - self.trigger*self.mspread + self.sdf*self.sdev
            changes=False
            if(self.bidTrigger is None or self.askTrigger is None):
                logging.info("Trigger set: [{}, {}]  medians=[{},{}]". format(bidTrigger, askTrigger, self.mbid, self.mask))
                changes=True
            elif(bidTrigger != self.bidTrigger or askTrigger != self.askTrigger):
                db = round((bidTrigger - self.bidTrigger), 6)
                da = round( (askTrigger - self.askTrigger),6)
                logging.info("Trigger changes [{} , {} ] [{}, {}] medians=[{},{}]".format(db,da,bidTrigger,askTrigger, self.mbid, self.mask))
                changes = True
            self.bidTrigger = bidTrigger
            self.askTrigger = askTrigger

            if(changes):
                logging.info("BID component (median={} - (trigger={} * mspread={} == {})  + (sdf={} * sdef={}) =={}) =  {}".format(
                     self.mbid, self.trigger, self.mspread, self.trigger*self.mspread,
                                self.sdf, self.sdev, self.sdf*self.sdev,
                                bidTrigger))
                logging.info("ASK component (median={} + (trigger={} * mspread={} == {})  - (sdf={} * sdef={}) =={}) =  {}".format(
                     self.mask, self.trigger, self.mspread, self.trigger*self.mspread,
                                self.sdf, self.sdev, self.sdf*self.sdev,
                                askTrigger))


    def digestLowCandle(self,candle):
        self.rsiLowMaker.add(candle)

    def riskManagementDecisions(self, candle, rsi, loopr, posMaker):
       """ apply classic risk management rules on current position to provide "decisions" based on current candle """
       reply = []
       trailStart = self.trailSpecs[0][0]
       trailDistance = self.trailSpecs[0][1]
       currentlyEngagedSize = reduce(lambda s,x: s + x.size , loopr.positions, 0)
       for n in range(len(loopr.positions)):
           posN = loopr.positions[n]
           posN.calibrateTrailingStopLossDesireForSteppedSpecs(candle,self.trailSpecs,self.mspread, loopr.instrument.minimumTrailingStopDistance)
           event,todo,benef, benefRatio = posN.timeToClose(candle, self.rsiLowMaker)
           if( n +1 == len(loopr.positions) and len(self.riskManagement)>n and event == 'hold'):
               sizeMax = self.maxEngagedSize - currentlyEngagedSize
               management = self.riskManagement[n].watchTrigger(self.mspread, benef, candle,
                                                   self.rsiLowMaker, posN, posMaker,
                                                   trailStart, trailDistance, currentlyEngagedSize, self.maxEngagedSize)
               if(management is not None):
                   reply.append(management)

           reply.append( (event,todo,benef,benefRatio, rsi, posN) )
       return reply


    def decision(self, loopr, posMaker, logMsg=True):
        rsi = 50.0
        trailStart = self.trailSpecs[0][0]
        trailDistance = self.trailSpecs[0][1]
        if(self.queue.full()):
            if(loopr.refreshIsDue()): loopr.refreshPositions(posMaker)
            pos1 = None if(len(loopr.positions)==0) else loopr.positions[0]
            c = self.rsiLowMaker.mq.last()
            rsi = self.rsiLowMaker.RSI
            lowRSI = (rsi < self.rsiLowMaker.oscLow *1.05)
            highRSI = (rsi > self.rsiLowMaker.oscHigh * 0.95)
            rsiOKForBuy = lowRSI if(self.rsiMode == "+") else (highRSI if(self.rsiMode=="-") else True)
            rsiOKForSell= highRSI if(self.rsiMode == "+") else (lowRSI if(self.rsiMode=="-") else True)

            if(pos1 is None):
                pipFactor = loopr.pipFactor
                if(c.ask.o < self.askTrigger and  rsiOKForBuy ):
                    # it is low (and rsi is close to oversold), we should buy
                    pos1 = posMaker.make(True, c,self.defaultSize, c.bid.o  - self.risk*self.mspread, c.ask.o+self.profit*self.mspread,
                                          trailStart*self.mspread+c.ask.o, trailDistance*self.mspread)
                    msg = "{0} -- Taking BUY position at Asking price of {1}  medians[bid={2}, 10Kspread={3}, spread={4} pips sd={5} pips] RSI={6}".format(
                                       c.time, c.ask.o,
                                       self.mbid,self.mspread*10000,round(self.mspread/pipFactor,3),
                                       round(self.sdev/pipFactor,3), round(rsi,2))
                    if(logMsg):
                        logging.warning(msg)
                    else:
                        logging.info(msg)
                    # if(args.debug): pdb.set_trace()

                elif(c.bid.o > self.bidTrigger and  rsiOKForSell):
                    # it is high (and rsi is close to overbought), we should sell
                    pos1 = posMaker.make(False, c, self.defaultSize, c.ask.o + self.risk*self.mspread, c.bid.o-self.profit*self.mspread,
                                          c.bid.o-trailStart*self.mspread, trailDistance*self.mspread)
                    msg = "{0} -- Taking SELL position at Bidding price of {1}  medians[bid={2}, 10Kspread={3}, spread={4} pips sd={5} pips] RSI={6}".format(
                                       c.time, c.bid.o,
                                       self.mbid,self.mspread*10000,round(self.mspread/pipFactor,3),
                                       round(self.sdev/pipFactor,3), round(rsi,2))
                    if(logMsg):
                        logging.warning(msg)
                    else:
                        logging.info(msg)
                    # if(args.debug): pdb.set_trace()
                else:
                    msgs = []
                    if(c.bid.o<=self.bidTrigger):
                        msgs.append("{} Bid {} too low (trigger={})".format(c.time,c.bid.o,self.bidTrigger))
                    elif(not rsiOKForSell):
                        msgs.append("{} Bid {} high enough for trigger (={}) but RSI={} not ok".format(c.time,c.bid.o, self.bidTrigger, rsi))

                    if(c.ask.o>=self.askTrigger):
                        msgs.append("{} Ask {} too high (trigger={})".format(c.time, c.ask.o, self.askTrigger))
                    elif(not rsiOKForBuy):
                        msgs.append("{} Ask {} low enough for trigger (={}) but RSI={} not ok".format(c.time,c.ask.o, self.askTrigger, rsi))


                    for m in msgs:
                        logging.info(m)


                if(pos1 is not None):
                    pos1.calibrateTrailingStopLossDesireForSteppedSpecs(c,self.trailSpecs,self.mspread, loopr.instrument.minimumTrailingStopDistance)
                    pos1.trailingStopNeedsReplacement = False

                if(pos1 is None):
                    return [ ("none", "wait", 0.0, 0.0, rsi, None ) ]
                else:
                    return [ ("triggered", "take-position", 0.0, 0.0, rsi, pos1) ]

            elif(pos1 is not None):
                return self.riskManagementDecisions(c,rsi, loopr, posMaker)
                #return event, todo,benef,benefRatio, rsi, pos1
        else:
            return [( "none", "wait", 0.0, 0.0, rsi, None)]


    def forCandles(self, high=False, counts=None):
       """prepare query object for oanda API to obtain candles"""
       if(counts==None):
           counts = 2*self.depth
       gran = self.highSlice if(high) else self.lowSlice
       return {"count": counts, "price":"BA", "granularity":gran}


    def pause(self, factor=1.05, tick=True):
        if(not self.simulation):

            from myt_support import frequency
            import time
            now = time.time()
            if(self.lastTick is None):
                if(not tick):
                    raise RuntimeError("calling unticked pause on uninitialized heart beat")
                else:
                    self.lastTick = now
                    return

            freq = frequency(self.lowSlice)
            p = (now - lastTick)
            if(p>freq):
                time.sleep(p-freq)
            if(tick):
                self.lastTick = time.now()
