
import logging


class RiskManagementStrategy(object):
    def __init__(self, lossTrigger, sizeFactor, reRisk, profit):
        self.lossTrigger = lossTrigger
        self.sizeFactor  = sizeFactor
        self.reRisk      = reRisk
        self.profit      = profit
        self.warningsRSI  = 0
        self.warningsSize = 0
        self.rsiAlwaysOK = False
        self.rsiInverted = False

    def watchTrigger(self, mspread, currentDelta, currentQuote, rsiMaker, parentPos, posMaker, trailStart, trailDistance,sizeMax):
        if(currentDelta < -mspread*self.lossTrigger):
                # so, supposed parentPos is in loss, we're taking a position that is going to be a buy
                # at a lower value than parent pos to hope to get a little less loss ...
                # but we won't BUY at an overbought position
                rsiSwitch = parentPos.forBUY if(not self.rsiInverted) else not parentPos.forBUY
                rsiOK = self.rsiAlwaysOK or (rsiSwitch and rsiMaker.RSI < rsiMaker.oscLow*1.2) or (rsiMaker.RSI > rsiMaker.oscHigh*0.8 and not rsiSwitch)
                if(not rsiOK):
                    if(self.warningsRSI < 3 or self.warningsRSI % 3 == 0):
                        logging.warning("Hint to add extra trade for RISK management is pre-empted by RSI: {}".format(rsiMaker.RSI))
                    self.warningsRSI +=1
                elif(sizeMax<=0):
                    if(self.warningsSize<2 or self.warningsSize % 30 == 0): logging.warning("Risk-management position is not attempted because engaged size was reached")
                    self.warningSize+=1
                else:
                    c = currentQuote
                    rsi = None if(self.rsiAlwaysOK and rsiMaker is None) else rsiMaker.RSI
                    size = parentPos.size * self.sizeFactor
                    if(size>sizeMax):
                        logging.warning("risk-management position, size {} reduced to {}, because of max-size limit".format(size, sizeMax))
                        size=sizeMax

                    self.warningsSize = 0
                    self.warningsRSI  = 0
                    relevantRisk = (c.bid.o - self.reRisk * mspread) if(parentPos.forBUY) else (c.ask.o + self.reRisk*mspread)
                    relevantProfit = (c.ask.o + self.profit * mspread) if (parentPos.forBUY) else (c.bid.o - self.profit*mspread)
                    trailStopTrigger = (c.ask.o + trailStart * mspread) if(parentPos.forBUY) else (c.bid.o - trailStart*mspread)
                    ##
                    pos2 = posMaker.make(parentPos.forBUY, currentQuote,
                                          size, relevantRisk, relevantProfit,
                                          trailStopTrigger, trailDistance*mspread)
                    logging.warning("{} - taking risk-management position ({}) size={}, at {} with take-profit:{} and save-loss:{} (RSI:{})".format(
                                  currentQuote.time, ("BUY" if(parentPos.forBUY) else "SELL"), size,
                                  (c.bid.o if(parentPos.forBUY) else c.ask.o),
                                  relevantProfit, relevantRisk, rsi))
                    return ("risk-mgt-trigger", "take-position", 0.0, 0.0, rsi, pos2)





    @staticmethod
    def parse(desc, bark=""):
        import re
        descs = desc.split(",")
        them = []
        rgx = re.compile(r"(\d+):([xpr\d\.]+)$")
        sgx = re.compile(r"(\d+\.?\d*)([xpr])")
        for d in descs:
            d = d.lower()
            if(rgx.match(d)):
                lt = float( rgx.match(d).groups()[0])
                rem = rgx.match(d).groups()[1]
                mapped = {}
                while(len(rem)>0):
                    bam = sgx.match(rem)
                    if(bam is None):
                        raise ValueError("{} - cannot parse {} as risk-management specs, fails on {}".format(bark, d, rem))
                    xrp = bam.groups()[1]
                    nnn = float(bam.groups()[0])
                    if(nnn<=0):
                        raise ValueErorr("{} - cannot use zero in risk management specs, fails on {}". format(bark,ren))
                    if(mapped.has_key(xrp)):
                        raise ValueError("{} - cannot specify {} multiply time in risk-mgt-specs, fails on {}".format(bark, xrp, rem))
                    mapped[xrp]=nnn
                    st = bam.start()
                    en = bam.end()
                    rem = rem[0:st] + rem[en:]
                sf = mapped['x'] if(mapped.has_key('x')) else 2.0
                pr = mapped['p'] if(mapped.has_key('p')) else (lt/sf)
                ri = mapped['r'] if(mapped.has_key('r')) else (lt/sf)
                them.append( RiskManagementStrategy(lt, sf, ri, pr) )
                logging.info("parsed risk-management-spec {} as lossTrigger={}, sizeFactor={}, profit={}, re-risk={}".format(d, lt, sf, pr, ri))
            else:
                raise ValueError("{} - cannot parse risk-management spec {}".format(bark,d))

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
           event,todo,benef, benefRatio = posN.timeToClose(candle, self.rsiLowMaker.isLow(), self.rsiLowMaker.isHigh())
           if( n +1 == len(loopr.positions) and len(self.riskManagement)>n and event == 'hold'):
               sizeMax = self.maxEngagedSize - currentlyEngagedSize
               management = self.riskManagement[n].watchTrigger(self.mspread, benef, candle,
                                                   self.rsiLowMaker, posN, posMaker,
                                                   trailStart, trailDistance, sizeMax)
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
