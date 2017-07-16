



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
            self.bidTrigger = self.mbid - self.trigger*self.mspread + self.sdf*self.sdev
            self.askTrigger = self.mask + self.trigger*self.mspread - self.sdf*self.sdev


    def digestLowCandle(self,candle):
        self.rsiLowMaker.add(candle)


    def decision(self, loopr, posMaker, logMsg=True):
        rsi = 50.0
        if(self.queue.full()):
            pos1 = None if(len(loopr.positions)==0) else loopr.positions[0]
            c = self.rsiLowMaker.mq.last()
            rsi = self.rsiLowMaker.RSI
            if(pos1 is None):
                #if(args.debug): pdb.set_trace()
                trailStart = self.trailSpecs[0][0]
                trailDistance = self.trailSpecs[0][1]
                pipFactor = loopr.pipFactor
                if((c.ask.o < self.askTrigger and  rsi<self.rsiLowMaker.oscLow*1.05)):
                    # it is low (and rsi is close to oversold), we should buy
                    pos1 = posMaker.make(True, c,self.defaultSize, c.bid.o  - self.risk*self.mspread, c.ask.o+self.profit*self.mspread,
                                          trailStart*self.mspread+c.ask.o, trailDistance*self.mspread)
                    if(logMsg):print("{0} -- Taking BUY position at Asking price of {1}  medians[bid={2}, 10Kspread={3}, spread={5}pips sd={4}pid] RSI={5}".format(\
                                       c.time, c.ask.o, self.mbid,self.mspread*10000,self.sdev/pipFactor,self.mspread/pipFactor, rsi))
                    # if(args.debug): pdb.set_trace()

                elif((c.bid.o > self.bidTrigger and  rsi>self.rsiLowMaker.oscHigh*0.95)):
                    # it is high (and rsi is close to overbought), we should sell
                    pos1 = posMaker.make(False, c, self.defaultSize, c.ask.o + self.risk*self.mspread, c.bid.o-self.profit*self.mspread,
                                          c.bid.o-trailStart*self.mspread, trailDistance*self.mspread)
                    if(logMsg):print ("{0} -- Taking SELL position at Bidding price {1} of  medians[bid={2}, 10Kspread={3}, spread={6} pips, sd={4} pips] RSI={5}".format(c.time, c.bid.o, self.mbid,self.mspread*10000,self.sdev/pipFactor, rsi, self.mspread/pipFactor))
                    # if(args.debug): pdb.set_trace()


                if(pos1 is not None):
                    pos1.calibrateTrailingStopLossDesireForSteppedSpecs(c,self.trailSpecs,self.mspread, loopr.instrument.minimumTrailingStopDistance)
                    pos1.trailingStopNeedsReplacement = False

                if(pos1 is None):
                    return "none", "wait", 0.0, 0.0, rsi, None
                else:
                    return "triggered", "take-position", 0.0, 0.0, rsi, pos1

            elif(pos1 is not None):
                # import pdb; pdb.set_trace()
                pos1.calibrateTrailingStopLossDesireForSteppedSpecs(c,self.trailSpecs,self.mspread, loopr.instrument.minimumTrailingStopDistance)
                event,todo,benef, benefRatio = pos1.timeToClose(c, self.rsiLowMaker.isLow(), self.rsiLowMaker.isHigh())
                return event, todo,benef,benefRatio, rsi, pos1
        else:
            return "none", "wait", 0.0, 0.0, rsi, None


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
