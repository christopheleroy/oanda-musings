
from robologger import robolog
from Alfred import RiskManagementStrategy
from oscillators import IchimokuCalculation
from functools import reduce




class IchimokuSentimentAnalyzer(object):
    def __init__(self,strongRequired = True, consistentRequired=False, alwaysGood = False, ichiMaker = False):
        self.strongRequired = strongRequired
        self.consistentRequired = consistentRequired
        self.alwaysGood = alwaysGood
        self.ichiMakerBool = ichiMaker

    def confirm(self, forBUY, ichiMaker):
        okSET = ["strong"] if(self.strongRequired) else ["strong", "medium"]
        okVALS = ["BUY", "SELL"]

        if(self.alwaysGood):
            return True, ichiMaker, ""

        if(self.consistentRequired and (ichiMaker[0] in okVALS and ichiMaker[0] in okVALS and ichiMaker[0]!=ichiMaker[1])):
            # when consistent required, we can't have one say BUY and the other SELL and count this as a good sentiment
            return False, ichiMaker, "inconsistent signals"

        try:
            yeepey = (True, ichiMaker, "")
            needed = "BUY" if(forBUY) else "SELL"

            if(ichiMaker[0] == needed and ichiMaker[1] in okSET): return yeepey
            if(ichiMaker[2] == needed and ichiMaker[3] in okSET): return yeepey

        except:
            print(ichiMaker)
            raise

        return False, ichiMaker, "not decisive"





class TradeStrategy(object):

    def __init__(self,trigger, profit, risk, select, size,tenkanSize, kijunSize, xoverSize, highSlice, lowSlice,trailSpecs):
        self.trigger = trigger
        self.profit = profit
        self.risk   = risk
        self.select = select
        self.defaultSize   = size
        self.tenkanSize = tenkanSize
        self.kijunSize  = kijunSize
        self.xoverSize  = xoverSize
        self.highSlice  = highSlice
        self.lowSlice   = lowSlice
        self.trailSpecs = trailSpecs

        self.riskManagement = []
        self.maxEngagedSize = None
        self.latestCandle = None
        self.mspread= None
        self.trailingSpecShrinker = None
        self.dual = True

    def turnSingle(self):
        # be in single mode = only the low candle is fed and is inspected
        self.dual = False


    def initialize(self):
        robolog.info("Initializing Bibari")
        self.highIchimoku = IchimokuCalculation(self.tenkanSize, self.kijunSize, name= '+high')
        self.lowIchimoku = IchimokuCalculation(self.tenkanSize, self.kijunSize,  name='-low-')


    def digestHighCandle(self,candle):
        self.highIchimoku.add(candle)

    def digestLowCandle(self, candle):
        self.lowIchimoku.add(candle)
        self.latestCandle = candle
        self.mspread = self.lowIchimoku.tenkanMedianSpread

    def setTrailingSpecShrinker(self, factor = 0.9, cfreq = None, shrinker=None):
        if(shrinker is not None):
            self.trailingSpecShrinker = shrinker
        else:
            from myt_support import frequency, TrailSpecShrinker
            highSlice = self.highSlice if(self.dual) else self.lowSlice
            if(cfreq is None):    
                freq1 = frequency(self.lowSlice) * self.kijunSize
                freq2 = frequency(highSlice) * self.tenkanSize
                freq = round(0.5(freq1+freq2) if(freq1 > freq2*2 or freq2 > freq1*2) else (freq2 if(freq2>freq1) else freq1)) + 60
                self.trailingSpecShrinker = TrailSpecShrinker(freq, factor)
            else:
                freq = round(cfreq * frequency(highSlice))
                self.trailingSpecShrinker = TrailSpecShrinker(freq, factor)


    def makeSentimentAnalyzer(self, rmArgs):
        return IchimokuSentimentAnalyzer(**rmArgs)


    def riskManagementDecisions(self, candle, loopr, ichiMaker, posMaker):
       """ apply classic risk management rules on current position to provide "decisions" based on current candle """
       reply = []
       trailStart = self.trailSpecs[0][0]
       trailDistance = self.trailSpecs[0][1]
       hSig,hStr,lSig,lStr,lhScore = ichiMaker
       tsshrink = None
       if(self.trailingSpecShrinker is not None):
           tsshrink = lambda eq,cq,ts: self.trailingSpecShrinker.trailSpecShrink(eq,cq,ts)

       currentlyEngagedSize = reduce(lambda s,x: s + x.size , loopr.positions, 0)
       for n in range(len(loopr.positions)):
           posN = loopr.positions[n]
           posN.calibrateTrailingStopLossDesireForSteppedSpecs(candle,
                             self.trailSpecs,self.mspread, 
                             loopr.instrument.minimumTrailingStopDistance, 
                             tsshrink)
           # timeTocClose expects hints as to whether the RSI is low (time to buy?) or RSI is high (time to sell?)
           wawa = [ hSig, lSig ]
           rsiLow = ('BUY' in wawa ) and not ('SELL' in wawa)
           rsiHigh = ('SELL' in wawa) and not ('BUY' in wawa)
           event,todo,benef, benefRatio = posN.timeToClose(candle, ichiMaker)
           if( n +1 == len(loopr.positions) and len(self.riskManagement)>n and event == 'hold'):
               management = self.riskManagement[n].watchTrigger(self.lowIchimoku.kijunMedianSpread, benef, candle,
                                                   ichiMaker, posN, posMaker,
                                                   trailStart, trailDistance, currentlyEngagedSize, self.maxEngagedSize)
               if(management is not None):
                   reply.append(management)

           reply.append( (event,todo,benef,benefRatio, lhScore, posN) )

       return reply


    def decision(self, loopr, posMaker, logMsg=True):
        if(not ( (self.highIchimoku.full() or not self.dual) and self.lowIchimoku.full())):
            #print(("high ichimoku", self.highIchimoku.size, self.highIchimoku.mq.currentSize()))
            #print(("low ichimoku", self.lowIchimoku.size, self.lowIchimoku.mq.currentSize()))
            return [ ("none", "wait", 0.0, 0.0, 0, None)]

        nah=False
        
        lSig, lStr, lDepth, lPrice, lxoTime  = self.lowIchimoku.pronostic(self.xoverSize)
        hSig, hStr, hDepth, hPrice, hxoTime  = (self.highIchimoku.pronostic(self.xoverSize) if(self.dual) else ('none', 'none', 0, None, None))
        robolog.debug("High: {}, Low: {} ".format( (hSig,hStr,hPrice,hxoTime), (lSig,lStr,lPrice,lxoTime)))

        # if(hSig=='SELL' and lSig=='BUY' and hStr == 'weak' and lStr == 'weak'):
        #     import pdb; pdb.set_trace()
        #     ZZ = self.lowIchimoku.pronostic(self.xoverSize)

        if(lStr in ['strong','medium'] or hStr in ['strong','medium']):
            lScore = (10 if(lStr == 'strong')else(5 if(lStr=='medium')else 0))
            hScore = (10 if(hStr=='strong')else(5 if(hStr=='medium')else 0))
            robolog.debug("*hScore={}, lScore={}".format(hScore,lScore))

            if(lSig == 'BUY'):
                lv = self.lowIchimoku.lastVal.distanceToCloudTop(lPrice, self.lowIchimoku.kijunMedianSpread)
                lScore +=  lv
                if(hSig=='SELL'):
                    nah = True
            elif(lSig=='SELL'):
                lv = - self.lowIchimoku.lastVal.distanceToCloudBottom(lPrice, self.lowIchimoku.kijunMedianSpread)
                lScore += lv
                if(hSig == 'BUY'):
                    nah=True

            if(hSig == 'BUY'):
                lv = self.highIchimoku.lastVal.distanceToCloudTop(hPrice, self.highIchimoku.tenkanMedianSpread)
                hScore += lv
            elif(hSig == 'SELL'):
                lv = - self.highIchimoku.lastVal.distanceToCloudBottom(hPrice, self.highIchimoku.tenkanMedianSpread)
                hScore += lv

            # for weak signals, the score will be negative (most likely), let's mimimize their impact
            if(lStr == 'weak'): lScore /= 5.0
            if(hStr == 'weak'): hScore /= 5.0

            robolog.debug("hScore={}, lScore={}".format(hScore,lScore))

        else:
            lScore = 0
            hScore = 0

        if(loopr.refreshIsDue()): loopr.refreshPositions(posMaker)
        if(len(loopr.positions)==0):
            if(lScore+hScore>self.trigger and not nah):
                trailStart = self.trailSpecs[0][0]
                trailDistance = self.trailSpecs[0][1]
                c = self.lowIchimoku.mq.last()
                mspread = self.lowIchimoku.tenkanMedianSpread
                if(lSig=='BUY' or hSig =='BUY'):
                    pos1 = posMaker.make(True, c,self.defaultSize, c.bid.o  - self.risk*mspread, c.ask.o+self.profit*mspread,
                                          trailStart*mspread+c.ask.o, trailDistance*mspread)
                elif(lSig=='SELL' or hSig =='SELL'):
                    pos1 = posMaker.make(False, c, self.defaultSize, c.ask.o + self.risk*mspread, c.bid.o-self.profit*mspread,
                                          c.bid.o-trailStart*mspread, trailDistance*mspread)

                if(pos1 is not None):
                    robolog.info("Position to take: {}".format(pos1))
                    pos1.calibrateTrailingStopLossDesireForSteppedSpecs(c,self.trailSpecs,mspread, loopr.instrument.minimumTrailingStopDistance)
                    pos1.trailingStopNeedsReplacement = False

                if(pos1 is None):
                    return [ ("none", "wait", 0.0, 0.0, lScore+hScore, None ) ]
                else:
                    robolog.critical("High: {}, Low: {}".format( (hSig,hStr,hScore), (lSig, lStr, lScore) ) )
                    robolog.critical("Recommend taking position: {}".format(pos1))
                    return  [ ("triggered", "take-position", 0.0, 0.0, lScore+hScore, pos1) ]
            return [ ("none", "wait", 0.0, 0.0, 0, None) ]

        else:
            c = self.lowIchimoku.mq.last()
            return self.riskManagementDecisions(c, loopr, (hSig, hStr, lSig, lStr, lScore+hScore),posMaker)
