import pdb
from collections import deque
from functools import reduce

## Teeth is a small module helping to navigate an instrument whose value goes up and down...

# keep a queue (FIFO) of size 'size'
# to help compute moving-max or moving-min (or moving whatever, with reduce)
class MovingQueue(object):


    def __init__(self, size):
        self.size = size
        self.elems = deque([])
        self.subscribers=[]
        self.skipper = None # a possible Lambda that we use to avoid adding elements to the queue - this lambda takes 2 possible elements of the queue x,y and returns True when y ought to be understood as equivalent of x


    def subscribes(self,fun):
        self.subscribers.append(fun)

    def skip(self, val):
        """ return True when the queue has a skipper set and this skipper say we should skip ... """
        if(self.skipper is not None):
            return self.elems>0 and self.skipper(self.elems[-1],val)
        else:
            return False


    def add(self,val):
        gone = None
        if(self.skipper is not None):
            if(len(self.elems)>0):
                if(self.skipper(self.elems[-1], val)):
                    return False


        if(len(self.elems)>=self.size):
            gone = self.elems.popleft()

        self.elems.append(val)
        # call all subscribers
        for fun in self.subscribers:
            fun(gone,val)
            
        return True

    def flush(self):
        self.elems = deque([])

    def full(self):
        return (len(self.elems)>=self.size)

    def empty(self):
        return len(self.elems)<1

    def currentSize(self):
        return len(self.elems)

    def size(self):
        return self.size

    def max(self):
        return max(self.elems)

    def min(self):
        return min(self.elems)

    def first(self):
        return self.elems[0]

    def last(self):
        return self.elems[-1]

    def lastTwo(self):
        return (self.elems[-2], self.elems[-1])

    def lastN(self,n):
        n = len(self.elems) if(n>len(self.elems)) else n
        return [ self.elems[i] for i in range(-n,0) ]
        


    def fill(self, V, n):
        if(self.full()):
            self.add(V[n+self.size])
        else:
            maxnk = len(V)
            for k in range(1,self.size+1):
                if(n+k<maxnk): self.add(V[n+k])

    def reduced(self, lam, init=0):
        return reduce(lam, self.elems,init)

    def __iter__(self):
        return self.elems.__iter__()

# order a distribution by a dimension (e.g time) and remove duplicated dimension times
def orderAndFilterBy(distribution, filterBy_fn):
    fcmp = lambda x,y: cmp(filterBy_fn(x),filterBy_fn(y))

    distribution = sorted(distribution, fcmp)
    nodups = []

    def redfilter(X,item):
        t = filterBy_fn(item)
        if(t > X['lt']):
            X['lt'] = t
            X['arr'].append(item)
        return X

    item0 = distribution[0]
    nodups = reduce(redfilter,distribution, {"lt": filterBy_fn(item0), "arr": [ item0]})
    # pdb.set_trace()
    return nodups['arr']



# for a distribution expected to be pre-sorted by time, with no dups per time
def findExtremes(distribution, valuation, time, nlevel,dt):
    T = list(map(time, distribution))
    V = list(map(valuation, distribution))
    S = len(distribution)


    movingMax = [False for i in range(S)]
    movingMin = list(movingMax)

    steps = list(range(1, nlevel+1))
    stepsDT = [dt * x for x in range(0,nlevel+1)]


    def checkN(n,bw=True,fw=True):
        if((bw and n<nlevel) or (fw and n+1>S-nlevel)):
            return False

        Tn = T[n]
        for i in steps:
            if(bw and T[n-i] != (Tn-stepsDT[i])): return False
            if(fw and T[n+i] != (Tn+stepsDT[i])): return False

        return True

    forwardOK = list(map((lambda n: checkN(n,False,True)), list(range(S))))
    backwardOK = list(map((lambda n: checkN(n,True, False)), list(range(S))))


    queueBefore = MovingQueue(nlevel)
    queueAfter = MovingQueue(nlevel)
    mbfull = False
    mafull = False
    for n in range(S):
        # if(V[n] == 9): pdb.set_trace()
        if(forwardOK[n]):
            queueAfter.fill(V,n)
        else:
            queueAfter.flush()

        if(backwardOK[n]):
            queueBefore.fill(V,n-nlevel-1)
        else:
            queueBefore.flush()


        if(forwardOK[n] and backwardOK[n]):
            movingMax[n] = (V[n]>queueBefore.max() and V[n] >= queueAfter.max())
            movingMin[n] = (V[n]<queueBefore.min() and V[n] <= queueAfter.min())

    return movingMin, movingMax
