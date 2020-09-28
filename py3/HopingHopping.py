
# Hoping Hopping between robot parameters will increase performance !

from myt_support import frequency, addSeconds



class OriginalMapper(object):
    def __init__(self):
        self.ctime = lambda r: r[0]
        self.pair  = lambda r: r[22]
        self.slice = lambda r: r[23]
        self.param  = lambda r: r[24]
        self.added  = lambda r: float(r[26]) if(len(r[26])>0) else 0
        self.action = lambda r: r[14]
        self.closing = lambda r: r[14] == 'close'
        self.opening = lambda r: r[14] == 'take-position'


_originalMapper = OriginalMapper()

class TradeEvent(object):
    def __init__(self, row, mapper= _originalMapper):
        # if(mapper is None):
        #     self.ctime = row[0]
        #     self.pair = row[22]
        #     self.slice = row[23]
        #     self.param = row[24]
        #     self.added = float(row[26])
        self.ctime = mapper.ctime(row)
        self.pair  = mapper.pair(row)
        self.slice = mapper.slice(row)
        self.param = mapper.param(row)
        self.added = mapper.added(row)
        self.closing = mapper.closing(row)
        self.opening = mapper.opening(row)
        self.openSince = None
    
    def key(self):
        return '|$|'.join([self.pair, self.slice, self.param])

class TradeOption(object):
    def __init__(self, pair, slice, param):
        self.pair = pair
        self.slice = slice
        self.param = param
        self.added = 0.0
        self.firstTime = None
        self.lastTime = None
        self.count = 0

    def add(self, ev):
        if(self.firstTime is None or ev.ctime < self.firstTime ): self.firstTime = ev.ctime
        if(self.lastTime is None or ev.ctime < self.lastTime ): self.lastTime = ev.ctime
        self.added += ev.added
        self.count += 1
    
    def key(self):
        return '|$|'.join([self.pair, self.slice, self.param])
    


class HistoryIndex(object):

    def __init__(self):
        self.pairs = set()
        self.slices = set()
        self.paramNames = set()
        self.history = {}
        
    def load(self,csvstream, mapper = _originalMapper):
        lastTime = {}

        for r in csvstream:
            action = mapper.action(r)
            if(action == 'close' or action == 'take-position'):
                # import pdb;pdb.set_trace()
                ev = TradeEvent(r)
                if( ev.ctime not in self.history):
                    self.history[ev.ctime] = []
                self.history[ev.ctime].append(ev)
                self.pairs.add(ev.pair)
                self.paramNames.add(ev.param)
                self.slices.add(ev.slice)
                if(ev.key() in lastTime and action == 'close'):
                    ev.openSince = lastTime[ev.key()]
                elif(action=='take-position'):
                    lastTime[ev.key()] = ev.ctime
                # elif(action=='close'):
                #     import pdb;pdb.set_trace()

        
            
    
    def weightedFrequencies(self, fibseed=[10,15]): 
        frequencies = sorted(list(set( map(lambda s: (frequency(s), s), self.slices) )), key=lambda f: -f[0])
        # use some Fibonacci technic to help beef-up the amount of time we scan the past
        fib = list(filter(lambda f: f>=10, fibseed))

        if(len(fib)<1): fib.append(10)
        if(len(fib)<2): fib.append(int(1.5*fib[-1]))
        while(len(fib)<len(frequencies)):
            fib.append( fib[-2]+fib[-1] )

        return list([ (frequencies[i][0], frequencies[i][1], fib[i]) for i in range(len(fib)) ])
        


    def timeSet(self, until, back_seconds =None, fibseed=[10,15]):
        from functools import reduce


        if(back_seconds is None):
            wFreqs = self.weightedFrequencies(fibseed)
            maxr = lambda mx,v: v if(mx is None or mx[0]*mx[2]<v[0]*v[2]) else mx

            maxF = reduce(max, wFreqs, None)
            maxS = maxF[0]*maxF[2]
        else:
            maxS = back_seconds

        since = addSeconds(until, -maxS)

        return sorted(list([ t  for t in self.history.keys() if t <= until and t>= since ]))

    def scoreOptions(self, timeSet, asTuples = True):
        M = {}
        

        for t in timeSet:
            if(t not in self.history): continue
            for ev in self.history[t]:
                k = ev.key()
                if(k not in M): M[k] = TradeOption(ev.pair, ev.slice, ev.param)
                if(ev.closing): M[k].add(ev)
        if(asTuples):
            return list( [ (x.pair, x.slice, x.param, x.added, x.firstTime, x.lastTime) for x in M.values() ])

        return M.values()

    def resimulation(self, money = 5000, freq= 3600, fibseed=[10,15], start = None):
        from functools import reduce
        if(start is None):
            start = sorted(self.history.keys())[0]

        back_seconds = reduce(lambda mx, v: v[0]*v[2] if(mx is None or mx < v[0]*v[2]) else mx, self.weightedFrequencies(fibseed), None)
        # back_seconds = 5 * freq
        print('Back-seconds: {}'.format(back_seconds))

        actualStart = addSeconds(start, back_seconds)
        nextCheck = actualStart
        
        timeline = sorted( self.history.keys() )

        strategy = None
        strategySince = None

        simulation = []
        hasOpenTrade = False
        for t in timeline:
            if(t >= actualStart):
                if(t >= nextCheck and not hasOpenTrade):
                    # we have to revaluate the strategy
                    #import pdb; pdb.set_trace()
                    nbs = back_seconds
                    bestOption = None
                    earliestTime = None
                    timeRange = sorted(self.timeSet(t, nbs))
                    earliestTime = timeRange[0]
                    # find the very best option, perhaps a loop is required ...
                    while(bestOption is None):    
                        options = self.scoreOptions(timeRange, False)
                        greatOption = reduce(lambda best, opt: opt if(best is None or \
                             best.added<opt.added or \
                                 (best.added == opt.added and opt.added>best.added)) else best, options)
                        bestOptions = list( [ opt for opt in options if (opt.added == greatOption.added) ] )
                        if(len(bestOptions)==1): 
                            # one single winner
                            bestOption = bestOptions[0]
                        else:
                            # too many winners, let's see back further in time ...
                            nbs = nbs + freq
                            timeRange = sorted(self.timeSet(t, nbs))
                            if(timeRange[0] == earliestTime):
                                # the time range is no longer worth expanding, we break...
                                bestOption = bestOptions[0]
                                break
                            else:
                                # loop again...
                                earliestTime = timeRange[0]

                    if(strategy is None or bestOption.key() != strategy.key()):
                        strategy = bestOption
                        strategySince = t
                        simulation.append( (t, 'pick-strategy', strategy.pair, strategy.slice, strategy.param, money, 0, nbs) )
                    nextCheck = addSeconds(t, freq)
                if(strategy is not None and strategySince < t):
                    skey = strategy.key()
                    for ev in self.history[t]:
                        if(skey == ev.key()) :
                            if(ev.closing and ev.openSince is not None and strategySince<ev.openSince):
                                simulation.append( (t, 'close',ev.pair, ev.slice, ev.param, money + ev.added, ev.added) )
                                money = money + ev.added
                                hasOpenTrade = False
                            elif(ev.closing and ev.openSince is None):
                                print('bug')
                                hasOpenTrade = False
                            elif(ev.opening):
                                simulation.append( (t, 'take-position', strategy.pair, strategy.slice, strategy.param, money, 0) )
                                hasOpenTrade = True

        return simulation


                

if(__name__ == '__main__'):
      import argparse, csv

      parser = argparse.ArgumentParser()
      parser.add_argument('files', nargs='+')
      parser.add_argument('--money', type=float, default = 5000.0)
      parser.add_argument('--freq', type=int, default=7200)
      
      args = parser.parse_args()

      HI = HistoryIndex()
      for f in args.files:
          with open(f,'r') as FIN:
              csvr = csv.reader(FIN)
              HI.load(csvr)
    
      for r in HI.resimulation(args.money, args.freq):
          print(r)



        





    




