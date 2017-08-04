
from myt_support import frequency, getSortedCandles
import dateutil,time, datetime, logging


def RFC3339_to_INT(ctime):
    return int(dateutil.parser.parse(ctime).strftime("%s"))

def INT_to_RFC3339(itime):
    return datetime.datetime.utcfromtimestamp(itime).isoformat('T') + 'Z'

def slowmogrow(n,k):
    import math
    return  math.ceil(0.5+math.fabs(math.sin(math.exp(n%600))*k*math.log(n)*math.log(n/k)*math.log(k)))*3*math.log(2)

class LiveCandle(object):
    """ a live candle is an iterator that returns candles, where the next() will be waiting for the next time slot to start (or to finish)"""

    def __init__(self,loopr, slice,initial, price="BA", since=None, require_complete=False, waitMin=0.5, waitMax=60, duration=None):
        self.slice = slice
        self.looper = loopr
        self.frequency = frequency(slice)
        self.initial = initial
        self.price = price

        self.backlog = []
        self.lastGiven = None
        self.lastTimeGiven = None
        self.require_complete = require_complete
        self.waitMin = waitMin
        self.waitMax = waitMax

        self.timeLimit = None
        self.nextLimit = None
        self.expired = False
        self.since = since
        self.duration = duration

    def getRecentCandles(self, cnt, since=None):
        kwargs = {"price": self.price, "granularity": self.slice}
        if(cnt is not None):
            kwargs["count"] = cnt
        if(since is not None):
            kwargs["fromTime"] = since

        return getSortedCandles(self.looper, kwargs)

    def setBacklog(self):
        self.backlog = self.getRecentCandles(None, since = self.since) if(self.since is not None) \
                                else self.getRecentCandles(self.initial)

    def waitRecentCandles(self,reclevel=0):
        lt = self.lastGiven.time
        zoo = filter(lambda c: cmp(lt, c.time)<0 and (c.complete or not self.require_complete), self.backlog)
        if(len(zoo)==0):
            # import pdb; pdb.set_trace()
            # so the backlog has been exhausted, let's see if we should wait some more
            now = time.time()
            lastNow = self.lastTimeGiven
            ws = self.frequency - (now - lastNow)
            if(ws>self.waitMax): ws = self.waitMax
            if(ws<self.waitMin): ws = self.waitMin
            if(reclevel>20):
                # when waiting for a long time, we might be facing a very quiet time for the market - let's sleep more
                ws += slowmogrow(reclevel-20, self.waitMax)
            logging.debug("sleep for {} seconds for next {}".format(ws, self.slice))
            time.sleep(ws)
            self.backlog = self.getRecentCandles(3)
            return self.waitRecentCandles(reclevel+1)
        else:
            logging.debug("no need to wait...")
        return zoo


    def __iter__(self):
        if(len(self.backlog)==0):
            self.setBacklog()
            if(self.duration is not None):
                t0 = RFC3339_to_INT(self.backlog[0].time)
                texp = t0+self.duration
                self.timeLimit = INT_to_RFC3339(texp)

        return self

    def next(self):
        return self.__next__()

    def __next__(self):
        if(self.expired):
            raise StopIteration()

        if(self.nextLimit is not None):
            self.nextLimit -= 1
            if(self.nextLimit<0):
                self.expired = True
                raise StopIteration()

        lg = self.lastGiven
        if(self.lastGiven is None):
            if(len(self.backlog)==0):
                self.setBacklog()
            lg = self.backlog[0]
        else:
            zoo = self.waitRecentCandles()
            lg = zoo[0]


        if(self.timeLimit is not None and cmp(self.timeLimit, lg)<=0):
            self.expired = True
            raise StopIteration()

        self.lastTimeGiven = time.time()
        self.lastGiven = lg

        return self.lastGiven






class DualLiveCandles(object):

    def __init__(self,loopr, highSlice,initial, lowSlice, price="BA"):
        self.looper = loopr
        self.highSlice = highSlice
        self.lowSlice  = lowSlice
        self.initial   = initial
        self.price     = price

        self.highSliceFreq = frequency(self.highSlice)
        self.lowSliceFreq  = frequency(self.lowSlice)
        self.initialLow = self.highSliceFreq / self.lowSliceFreq

        self.highLC = None
        self.lowLC  = None

    def __iter__(self):
        if(self.highLC is None):
            self.highLC = LiveCandle(self.looper,self.highSlice, self.initial, self.price, waitMax = 5.0)

        return self

    def __next__(self):

        if(self.highLC.lastGiven is None):
            return ( self.highLC, [] )
        else:
            self.lowLC = LiveCandle(self.looper, self.lowSlice, self.initialLow, self.price,
                                    waitMax = 5.0, since = self.highLC.lastGiven.time, duration = self.highSliceFreq)

            return (self.highLC, self.lowLC )

    def next(self):
        return self.__next__()
