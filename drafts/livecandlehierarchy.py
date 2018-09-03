import pdb
from myt_support import frequency, getSortedCandles
import dateutil,time, datetime, logging
from robologger import oscillog

def addSeconds(ctime, sec):
    dt = dateutil.parser.parse(ctime)
    dtp = dt + dateutil.relativedelta.relativedelta(seconds=sec)
    return dtp.isoformat('T').replace("+00:00", ".000000000Z")


def slowmogrow(n,k):
    import math
    return  math.ceil(0.5+math.fabs(math.sin(math.exp(k+n%600))*k))*2*math.log(2)
    #return  math.ceil(0.5+math.fabs(math.sin(math.exp(n%600))*k*math.log(n)*math.log(n/k)*math.log(k)))*3*math.log(2)

class LiveCandle(object):
    """ a live candle is an iterator that returns candles, where the next() will be waiting for the next time slot to start (or to finish)"""

    def __init__(self,loopr, slice,initial, price="BA", since=None, require_complete=False, waitMin=0.5, waitMax=60, duration=None, name='nameless'):
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
        self.name = name
        self.islive = False
        #print( ('Create', name, duration, since, initial) )

    def getRecentCandles(self, cnt, since=None):
        kwargs = {"price": self.price, "granularity": self.slice}
        if(cnt is not None):
            kwargs["count"] = cnt
        if(since is not None):
            kwargs["fromTime"] = since
        #print(kwargs)
        return getSortedCandles(self.looper, kwargs)

    def setBacklog(self):
        """setBacklog is expected to be called once, and sets the backlog to a number of (backtracking) candles in the past"""
        # if 'since' is not specified, we still have to follow 'since' for high-candles, so we do so
        since = self.since
        if(since is None):
            # heartbeat:
            heartbeat = self.getRecentCandles(1)
            t = heartbeat[-1].time
            since = addSeconds(t, - self.initial * self.frequency)
        
        self.backlog = self.getRecentCandles(None, since = since)



    def waitRecentCandles(self,reclevel=0):
        lt = self.lastGiven.time
        zoo = filter(lambda c: cmp(lt, c.time)<0 and (c.complete or not self.require_complete), self.backlog)
        if(len(zoo)==0):
            # logging.debug( map (lambda c: c.time[10:19], self.backlog))
            # so the backlog has been exhausted, let's see if we should wait some more
            now = time.time()
            lastNow = self.lastTimeGiven
            ws = self.frequency - (now - lastNow)
            if(ws>self.waitMax): ws = self.waitMax
            if(ws<self.waitMin): ws = self.waitMin
            if(reclevel>20):
                # when waiting for a long time, we might be facing a very quiet time for the market - let's sleep more
                ws += slowmogrow(reclevel-20, self.waitMax)
            #oscillog.debug("sleep for {} seconds for next {}".format(ws, self.slice))
            time.sleep(ws)
            self.backlog = self.getRecentCandles(3)
            if(not self.islive and len(self.backlog)>0):
                latest = self.backlog[0]
                live = filter(lambda c: cmp(c.time, latest.time) >=0 and not c.complete, self.backlog)
                if(cmp( live[0].time, addSeconds(latest.time, 2*self.frequency) )<=0):
                    # pdb.set_trace()
                    self.islive = True
            #print(map(lambda c: c.time, self.backlog))
            return self.waitRecentCandles(reclevel+1)
        else:
            logging.debug("no need to wait...")

        return zoo


    def __iter__(self):
        if(len(self.backlog)==0):
            self.setBacklog()
            if(self.duration is not None):
                t0 = (self.backlog[0].time if(self.since is None) else self.since)
                self.timeLimit = addSeconds(t0, self.duration)
                #print(('init', self.name, self.timeLimit))

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


        if(self.timeLimit is not None and cmp(self.timeLimit, lg.time)<0):
            self.expired = True
            #print(('Expiring', self.name, lg.time, self.timeLimit))
            raise StopIteration()

        self.lastTimeGiven = time.time()
        self.lastGiven = lg
        #print(('Given', self.name, lg.time))
        return self.lastGiven






class DualLiveCandles(object):

    def __init__(self,loopr, highSlice,initial, lowSlice, price="BA", complete_policy="high", mult=1.0):
        self.looper = loopr
        self.highSlice = highSlice
        self.lowSlice  = lowSlice
        self.initial   = round(initial*mult)
        self.price     = price

        self.highSliceFreq = frequency(self.highSlice)
        self.lowSliceFreq  = frequency(self.lowSlice)
        self.initialLow = self.highSliceFreq / self.lowSliceFreq

        self.highLC = None
        self.lowLC  = None
        self.complete_policy = complete_policy
        if(not (complete_policy in ["high", "low", "both", "none"])):
            raise ValueError("DualLiveCandles: complete_policy must be either high, low or both")

    def isnowlive(self):
        if(self.lowLC is not None and self.lowLC.islive): return True
        if(self.highLC is not None and self.highLC.islive): return True
        return False

    def __iter__(self):
        if(self.highLC is None):
            self.highLC = LiveCandle(self.looper,self.highSlice, self.initial, self.price, waitMax = 5.0, require_complete = (self.complete_policy in ["high", "both"]), name='high:'+self.highSlice)

        return self

    def __next__(self):

        if(self.highLC.lastGiven is None):
            return ( self.highLC, [] )
        else:
            lt = self.highLC.lastGiven.time
            lt0 = lt
            if( self.complete_policy in ["high", "both"] ):
                lt = addSeconds(lt, + self.highSliceFreq)

            waitMax = 5.0 if(self.lowSliceFreq/5.0 < 5.0) else float(int(self.lowSliceFreq/5.0))
            waitMin = 0.5 if(self.lowSliceFreq<30) else int(self.lowSliceFreq / 30.0)
            self.lowLC = LiveCandle(self.looper, self.lowSlice, self.initialLow, self.price,
                                    waitMin = waitMin, waitMax = waitMax, since = lt, duration = self.highSliceFreq,
                                    require_complete = (self.complete_policy in ["low", "both"]), name='low:' + self.lowSlice)

            return (self.highLC, self.lowLC )

    def next(self):
        return self.__next__()
