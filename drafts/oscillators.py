
from teeth import MovingQueue
from robologger import oscillog
import numpy as np

def defaultValuator(candle):
    return candle.bid.c

def roc(a,b):
    """ROC: the rate of change"""

    return (b-a)/a


class OscillatorCalculation(object):

    def __init__(self, sizeSpec, valuator = defaultValuator):

        import re

        if(type(sizeSpec)==int):
            self.size=sizeSpec
            self.oscHigh = 70.0
            self.oscLow  = 30.0
        elif(sizeSpec == "0" or sizeSpec == "" or sizeSpec.lower() == "none"):
            self.size = 0
            self.oscHigh = 100.0
            self.oscLow = 0.0
        else:
            m=re.match(r"(\d+):(\d+\.?\d*)-(\d+\.?\d*)", sizeSpec)
            if(m is None):
                raise ValueError("sizeSpec " + sizeSpec + " must be of the form 14:30.0-70.0 ...")
            else:
                g = m.groups()
                self.size = int(g[0])
                self.oscHigh = max(float(g[1]), float(g[2]))
                self.oscLow  = min(float(g[1]), float(g[2]))
                if(self.oscHigh == 0.0 and self.oscLow ==0.0):
                    self.oscHigh = 100.0

        self.valuator = valuator
        self.mq = MovingQueue(self.size+1)

        self.recentVal = 0
        self.avgGain = 0.0
        self.avgLoss = 0.0
        self.sumGain = 0.0
        self.sumLoss = 0.0

    def setSkipper(self, skipper):
        self.mq.skipper = skipper


    def full(self):
        return self.mq.full()

    def add(self, candleItem):
        valfun = self.valuator
        # import pdb; pdb.set_trace()
        val = valfun(candleItem)

        if(self.mq.currentSize()>0):
            if(self.mq.skipper is not None):
                if(self.mq.skipper(self.mq.last(), candleItem)):
                    return

            # reference: http://stockcharts.com/school/doku.php?id=chart_school:technical_indicators:relative_strength_index_rsi
            nGain = 0.0
            nLoss = 0.0
            if(val>self.recentVal):
                nGain = val - self.recentVal
            else:
                nLoss = self.recentVal - val

            if(not self.mq.full()):
                self.sumGain += nGain
                self.sumLoss += nLoss
            else:
                self.sumGain =self.avgGain*(self.size-1)+nGain
                self.sumLoss =self.avgLoss*(self.size-1)+nLoss

            self.avgGain = self.sumGain/self.size if(self.size>0) else 0.0
            self.avgLoss = self.sumLoss/self.size if(self.size>0) else 0.0
            self.RS = self.avgGain / self.avgLoss if(self.avgLoss>0) else 1.0
            self.RSI = 100*(self.RS/(1.0+self.RS))
            oscillog.info("{}\t{} vs {}\t{} vs {}\tRS={}\tRSI={}",val, nGain, nLoss, self.avgGain, self.avgLoss, self.RS, self.RSI)

        self.mq.add(candleItem)
        self.recentVal = val



    def isHighLow(self, oscName = 'RSI', isHigh=True):
        if(self.size==0): return False

        if(not self.mq.full()):
            raise RuntimeError("too early to call")
        if(oscName != 'RSI'):
            raise ValueError("oscName " + oscName+ " not supported")
        return (isHigh and (self.RSI > self.oscHigh)) or ((not isHigh) and (self.RSI<self.oscLow))

    def isHigh(self, oscName='RSI'):
        return self.isHighLow(oscName, True)

    def isLow(self, oscName='RSI'):
        return self.isHighLow(oscName, False)



class IchimokuPoint(object):
    """ an IchimokuPoint is a point for an Ichimoku cloud, relative to a time."""
    def __init__(self, itime, tenkan, kijun, counterChikou, senkouA, senkouB,rClose, pastSenkouPair):
        self.time  = itime
        self.tenkan = tenkan
        self.kijun = kijun
        self.counterChikou = counterChikou
        self.senkouA = senkouA
        self.senkouB  = senkouB
        self.relevantClosePrice = rClose
        self.pastSenkouPair = pastSenkouPair



    def __str__(self):
        return "[{}: K={}; T={}; cC={};, A,B={},{}][P={}]".format(self.time, self.tenkan, self.kijun, self.counterChikou, self.senkouA, self.senkouB,self.relevantClosePrice)


    def isAboveCloud(self, p):
        return p > self.senkouA  and p > self.senkouB

    def isBelowCloud(self, p):
        return p< self.senkouA and p<self.senkouB

    def isInCloud(self,p):
        return not (self.isAboveCloud(p) or self.isBelowCloud(p))

    def distanceToCloudTop(self,p,mspread=1.0):
        sTop = (self.senkouA if(self.senkouA>self.senkouB) else self.senkouB)
        oscillog.debug("p={}|senkou A:{} vs B:{}; Top = {}; distance = {}  distance/spread={}".format(p,self.senkouA, self.senkouB, sTop, p-sTop, (p-sTop)/mspread))
        return (p-sTop)/mspread

    def distanceToCloudBottom(self,p,mspread=1.0):
        sBottom = (self.senkouA if(self.senkouA<self.senkouB) else self.senkouB)
        oscillog.debug("p={}|senkou A:{} vs B:{}; Bottom = {}; distance = {} distance/spread={}".format(p,self.senkouA, self.senkouB, sBottom, p-sBottom, (p-sBottom)/mspread))
        return (p-sBottom)/mspread

    def chikouSpanCross(self):
        if(self.pastSenkouPair is None):
            return ("none", "n/a")

        psA, psB = self.pastSenkouPair
        c = self.counterChikou
        abovePastKumo = c > psA and c> psB
        belowPastKumo = c < psA and c < psB
        inPastKumo = not (abovePastKumo or belowPastKumo)
        # unfinished






class midpoint(object):
    def __init__(self, starter=None):
        self.mid = None
        self.hh  = None
        self.ll  = None

        if(starter is not None):
            self.actualize(starter)


    def actualize(self,valH, valL):
        self.hh = valH if(self.hh is None) else (valH if(self.hh<valH) else self.hh)
        self.ll = valL if(self.ll is None) else (valL if(self.ll>valL) else self.ll)
        self.mid = 0.5* (self.hh + self.ll)
        return self
        # return self, so as to be able to use in reduce...


class IchimokuCalculation(object):
    def __init__(self, tenkanSize=9, kijunSize=None, onBid = True, name = None):

        if(kijunSize is None):
            kijunSize = 3 * tenkanSize -1


        senkouSize = 2*kijunSize

        if(kijunSize<=tenkanSize):
            raise ValueError("kijun size must be more than tenkan size")

        self.tenkanSize  = tenkanSize
        self.kijunSize = kijunSize
        self.senkouSize = senkouSize

        self.size = senkouSize+kijunSize
        self.mq   = MovingQueue(self.size)
        self.mqTK = MovingQueue(kijunSize)
        self.onBid = onBid
        self.roarr = lambda midp,c: midp.actualize(c.bid.h, c.bid.l)
        if(not onBid):
            self.roarr = lambda midp,c: midp.actualize(c.ask.h, c.ask.l)


        self.mqVals = MovingQueue(self.size)
        self.lastVal= None
        self.liveVal = None
        self.kijunMedianSpread = None
        self.tenkanMedianSpread = None

        self.addMsg = "added: %s "
        self.skippedMsg = "skipped: %s"
        self.name = name
        if(name is not None):
            self.addMsg = "(" + name + ") "+self.addMsg
            self.skippedMsg = "(" + name + ") " + self.skippedMsg


    def add(self, candle):
        rvc = candle.bid.c if(self.onBid) else candle.ask.c
        skipping = self.mq.skip(candle)
        self.mq.add(candle)


        if(self.mq.currentSize()>=self.kijunSize):
            mql = list(self.mq)
            kijun = mql[-self.kijunSize: ]
            tenkan  = mql[ -self.tenkanSize: ]
            self.kijunMedianSpread = np.median (map(lambda c: c.ask.c - c.bid.c, kijun))
            self.tenkanMedianSpread = np.median (map(lambda c: c.ask.c - c.bid.c, tenkan))
            kijunV = (reduce(self.roarr, kijun, midpoint())).mid
            tenkanV  = (reduce(self.roarr,tenkan, midpoint())).mid
            #chikouV = candle.bid.c if(self.onBid) else candle.ask.c
            cChikouV = kijun[0].bid.c if(self.onBid) else kijun[0].ask.c
            eChikouV = rvc

            # example with tenkan size of 3 and kijun size of 8
            # 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19
            # <---------------------> kijun array of past candles, kijunV = midpoint
            #                 <-----> tenkan  array of post candles, tenkanV = midpoint
            #  *                      cChikouV = counter-Chickou, closing price on t=01
            #                        * eChikouV = effective-Chikou closing price on now (t=08).
            # when using Chikou span, you effectively compare the eChikouV to cChikouV
            # when eChikouV is above cChikouV, this is a BULLISH trend (buy)
            # when eChikouV is below cChikouV, this is a BEARISH trend (sell)
            if(not skipping):

                self.mqTK.add( (tenkanV, kijunV, cChikouV, eChikouV, candle.time) )

            if(self.mq.full()):
                senkou = mql[ : self.senkouSize ]
                senkouB = (reduce(self.roarr, senkou, midpoint())).mid
                k,t,cc,ec,ctime = self.mqTK.first()
                senkouA  = 0.5*(t+k)

                pastSenkou = None
                if(self.mqVals.currentSize()>self.kijunSize):
                    pv = (self.mqVals.lastN(self.kijunSize))[0]
                    pastSenkou = (pv.senkouA, pv.senkouB)

                p = IchimokuPoint(candle.time, tenkanV, kijunV, cChikouV, senkouA, senkouB, rvc, pastSenkou)

                if(not skipping):
                    self.mqVals.add(p)
                    oscillog.info(self.addMsg, p)
                else:
                    osccilog.debug(self.skippedMsg, p)

                self.lastVal = p
        else:
            oscillog.debug("... still augmenting tenkan/kinjun queue ... -- value was %f %s", rvc, ("!" if self.name is None else self.name))


    def setSkipper(self, skipper):
        self.mq.skipper = skipper

    def full(self):
        return self.mq.full()


    def pronostic(self,depth=5,skipping=0):
        if(self.mq.full()):
            mqv5 = self.mqVals.lastN(depth+skipping)
            mqv5.reverse()
            next_t_over_k = None
            next_x = None
            itCnt = 0
            # next: is the previous value in the reversed iteration - so next_x is for a time after x
            for x in mqv5:
                if(skipping>0):
                    skipping -= 1
                    continue
                    
                itCnt+=1
                tok = True if(x.tenkan > x.kijun) else(False if(x.tenkan<x.kijun) else None)
                if(next_t_over_k is None and tok is not None):
                    next_t_over_k = tok
                else:
                    if(tok is not None):
                        if(tok != next_t_over_k):
                            # we have cross-over
                            #cross over price
                            cop = 0.25*(x.tenkan + x.kijun + next_x.tenkan + next_x.kijun)
                            # when tok == True, then next_t_over_k is False, so the cross-over shows a tenkan cross-over below kijun
                            signal = "SELL" if(tok) else "BUY"
                            if(not tok):
                                # from: http://www.kumotrader.com/ichimoku_wiki/index.php?title=Ichimoku_trading_strategies
                                #  If the cross is a "Buy" signal and the chikou span is above the price curve at
                                #  that point in time, this will add greater strength to that buy signal.
                                if(x.isAboveCloud(x.relevantClosePrice) and x.relevantClosePrice > x.counterChikou):
                                    strength = "strong" if(x.isAboveCloud(cop)) else ("medium" if (x.isInCloud(cop)) else "weakish")
                                else:
                                    strength = "weak" if(x.isBelowCloud(cop)) else "weird"
                            else:
                                if(x.isBelowCloud(x.relevantClosePrice) and x.relevantClosePrice < x.counterChikou):
                                    strength = "strong" if(x.isBelowCloud(cop)) else ("medium" if(x.isInCloud(cop)) else "weakish")
                                else:
                                    strength = "weak" if(x.isAboveCloud(cop)) else "weird"
                            return (signal, strength, itCnt, cop, x.time)
                            next_over_k = tok
                next_x = x

            return ("none", "n/a", depth, None,None)
        else:
            return ("none", "n/a", 0, None,None)
