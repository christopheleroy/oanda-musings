
from teeth import MovingQueue

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
            #print "{}\t{} vs {}\t{} vs {}\tRS={}\tRSI={}".format(val, nGain, nLoss, self.avgGain, self.avgLoss, self.RS, self.RSI)

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
