import pdb
import math

class InstrumentWrapper(object):

    def __init__(self,data):
        self.pair = data['pair']
        self.instrument = data['i']
        self.S5 = data['S5']
        self.M15 = data['M15']
        self.M1  = data['M1']
        self.S5inx  = self._indexByTime(self.S5)
        self.M15inx = self._indexByTime(self.M15)
        self.M1inx =  self._indexByTime(self.M1)

        c = {}
        c['S5'] = self.S5inx
        c['M1'] = self.M1inx
        c['M15']= self.M15inx
        self.inx = c

    def _indexByTime(self, array):
        inx = {}
        for a in array:
            inx[ a.time ] = a
        return inx


    def passesThrough(self, step):
        return self.pair[0]==step or self.pair[1]==step

    def betterVolume(self, dim='S5', n=10):
        # pdb.set_trace()
        xq = (self.S5 if(dim=='S5') else self.M15)
        xq = list(xq)
        xq.sort(lambda x,y: x.volume>y.volume)
        return reduce((lambda x,y: x+y.volume), xq[-n:],0)

    def commonTimes(self, dim='S5', times=[]):
        cTimes = []
        inx = self.S5inx if(not self.inx.has_key(dim))else self.inx[dim]
        for t in times:
            if(inx.has_key(t)):
                cTimes.append(t)
        return cTimes

    def dataFor(self, dim='S5'):
        return self.inx[dim] if(self.inx.has_key(dim)) else self.S5inx


# an InstrumentStep is an wrapped instrument with a direction to be used (forward vs backward) in a path
# e.g for USB-to--GDP, we need to use the intrument GBP/USB backward
class InstrumentStep(object):
    def __init__(self, wrapper,forward):
        self.wrapper = wrapper
        self.forward = forward

        if forward:
            self.pair = self.wrapper.pair
        else:
            self.pair = [self.wrapper.pair[1], self.wrapper.pair[0]]

    def atTime(self, dim='S5', t=""):
        inx = self.wrapper.dataFor(dim)
        # pdb.set_trace()
        val = inx[t] if(inx.has_key(t)) else None
        if(val is None):
            return 1
        else:
            # pdb.set_trace()
            return val.ask.o if(self.forward)else (1/val.bid.o)




# an InstrumentPath is an ordered list of InstrumentSteps
class InstrumentPath(object):
    def __init__(self, path):
        self.path = path

    def __str__(self):
        vol =self.volume()
        m15,ln15 = self.coordinationFactor('M15')
        st1 =  "|".join(map(lambda st: st.wrapper.instrument.name + ("*" if not st.forward else ""),self.path))
        return st1 + " {" + self.ring() + "} [" + str(vol) + "] = " + str(m15) + "/" + str(ln15)


    def ring(self):
        return "_".join(map(lambda st: st.pair[0].lower(), self.path))

    def bestVolume(self,dim):
        z = map( lambda st: st.wrapper.betterVolume(dim), self.path)
        return reduce(lambda x,y: x+y, z)

    def volume(self):
        return self.bestVolume('S5') + self.bestVolume('M15')

    def coordinationFactor(self, dim='S5'):
        step1 = self.path[0].wrapper
        step1inx = step1.dataFor(dim)
        common = step1inx.keys()
        for n,s in enumerate(self.path):
            if(n>0):
                common = s.wrapper.commonTimes(dim,common)
        if(len(common)<15):
            return 0,0


        facts = map((lambda t: reduce(lambda red,s: red*s.atTime(dim,t), self.path, 1)), common)
        l = len(self.path)
        factor = (reduce(lambda red, f: red + (math.log(f)/l),facts,0))/len(facts)
        return math.exp(factor),len(facts)




class PathFinder(object):

    def __init__(self, wrappers):
        self.wrappers = wrappers


    # find exactly different alternatives for a next step
    def findNextStepAlternatives(self, visited, steps):
        if(len(steps)==0):
            raise ValueError("visited and steps cannot be both empty")
        if(len(visited)==0):
            for s in steps:
                visited[s.pair[0]]=True
                visited[s.pair[1]]=True

        lastStep = steps[len(steps)-1].pair[1]

        alternatives = []
        for w in self.wrappers:
            if(w.pair[0] == lastStep and not visited.has_key(w.pair[1])):
                alternatives.append(InstrumentStep(w, True))
            elif (w.pair[1] == lastStep and not visited.has_key(w.pair[0])):
                alternatives.append(InstrumentStep(w,False))

        return alternatives



    def find(self, seed=None):
        paths = []
        step1 = None
        if(seed is None):
            seed = self.wrappers[0].pair[0]
            step1 = InstrumentStep(self.wrappers[0],True)
        else:
            _i=0
            while step1 is None and _i<len(self.wrappers):
                if(self.wrappers[_i].passesThrough(seed)):
                    direction = (self.wrappers[_i].pair[0] == seed)
                    step1 = InstrumentStep(self.wrappers[_i],direction)
                _i=_i+1

        if step1 is None:
            raise ValueError("could not find first step for seed " + seed)

        exhausted = False
        steps = [step1]
        paths = [ steps ]

        while not exhausted:
            exhausted = True
            npaths = []
            for steps in paths:
                alternatives = self.findNextStepAlternatives({}, steps)
                if(len(alternatives)>0):
                    exhausted = False
                    for a in alternatives:
                        nsteps = list(steps)
                        nsteps.append(a)
                        npaths.append(nsteps)
            if(not exhausted): paths = npaths

        finalPaths = []
        for p in paths:
            p1 = p[0].pair[0]
            pn = p[len(p)-1].pair[1]
            ws = filter(lambda w: w.passesThrough(p1) and w.passesThrough(pn), self.wrappers)
            if(len(ws)>0):
                ns = InstrumentStep(ws[0], ws[0].pair[0] == pn)
                p.append(ns)
                finalPaths.append( InstrumentPath (p) )


        for p in finalPaths:
            print p.__str__()

        return finalPaths

class StrategicAdvice(object):

    def __init__(self, buySell, price, takeProfit, limitOrder, stopLoss):
        self.buy = buySell == 'buy'
        self.sell = not self.buy
        self.price = price
        self.takeProfit = takeProfit
        self.limitOrder = limitOrder
        self.stopLoss = stopLoss




class StrategicTest(object):
    def __init__(self,data):
        self.sampleSize      = 10 if(data.sampleSize is None) else data.sampleSize
        self.slice           = 'M1' if(data.slice is None) else data.slice
        # do we want to check on the spread ?
        self.spreadStatistic = 'median' if(data.spread is None) else data.spread
        self.spreadFactor    = 1 if(data.spreadFactor is None) else data.spreadFactor
        # do we want to choose based on recent up/down candles?
        self.ups = 0 if(data.ups is None) else self.ups
        self.downs = 0 if(data.downs is None) else self.downs
        # do we want to choose on


        if(not re.match('(median|mean|max|min|latest)', self.spread)):
            raise ValueError("spread statistics must either be median, latest, min, max or mean")

        if(not (isinstance(self.ups, (int,float)) and isinstance(self.downs, (int,float)))):
            raise ValueError("ups/downs must be numeric")

        if( (isinstance(self.ups,int) and not isinstance(self.downs, int)) or
            (isinstance(self.downs,int) and not isinstance(self.ups, int))):
            raise ValueError("ups/downs must be both ints or both floats")

        if(isintance(self.ups, float) and self.downs + self.ups != 1.0):
            raise ValueError("ups/downs, when float, must amount to 1.0 (100%)")


    #def summarizedSpread(self,iWrapper):


    #def advise(self, iWrapper, current):



class Opportunity(object):
    def __init__(self, first,second, pipFactor, trSize, iname):
        self.begin = first
        self.end   = second
        self.pf    = pipFactor
        self.trSize = trSize
        self.pair = iname.split("_");

#deltaS = ci.bid.o - lastExtreme.ask.o if(forBUY) else (lastExtreme.bid.o - ci.ask.o)

    def atBegin(self, forBUY):
        return self.begin.ask.o if(forBUY) else self.begin.bid.o

    def atEnd(self, forBUY):
        return self.end.bid.o if(forBUY) else self.end.ask.o


    def delta(self, forBUY):
        return self.atEnd(forBUY) - self.atBegin(forBUY)

    def deltaPips(self, forBUY):
        return self.pf * self.delta(forBUY)

    def profit(self, forBUY):
        d = self.delta(forBUY)
        if(not forBUY):
            d = -d

        return d

    def profitPips(self,forBUY):
        return self.profit(forBUY)*self.pf

    def profitAmount(self, forBUY):
        return self.profit(forBUY)*(100000*self.trSize) / self.end.bid.o

    def ok(self,forBUY):
        return self.profit(forBUY)>0
