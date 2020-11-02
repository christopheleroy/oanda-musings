

from teeth import MovingQueue
import numpy as numpy


def defaultBollingerValuator(candle):
    # typical price for Bollinger:
    return (candle.bid.h + candle.bid.c + candle.bid.l)/3.0



class BollingerCalculation(object):

    def __init__(self, periods, shift, stdevs, valuator = defaultBollingerValuator):
        self.periods = periods
        self.shift   = shift
        self.stdevs  = stdevs

        self.mq = MovingQueue(self.periods)
        self.valuator = valuator
        

        



    def setSkipper(self, skipper):
        self.mq.skipper = skipper


    def full(self):
        return self.mq.full()

    def add(self, candleItem):
        if(self.mq.skipper is not None):
            if(self.mq.skipper(self.mq.last(), candleItem)):
                return

        self.mq.add(candleItem)

        if(self.mq.full()):
            valor = self.valuator
            TPn = list(map(lambda c: valor(c), self.mq.lastN(self.periods)))
            # https://www.investopedia.com/terms/b/bollingerbands.asp
            # std deviation 
            sigma = np.std(TPn)
            # moving average:
            avg = np.mean(TPn)
            # bollinger half-width:
            bolhw = self.stdevs*sigma
            bolu = avg + bolhw
            bold = avg - bolhw

            # bollinger bandwidth:
            # https://school.stockcharts.com/doku.php?id=technical_indicators:bollinger_band_width
            bolbw = (2*bolhw)/avg

            



