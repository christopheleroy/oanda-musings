
# A Student package: able to study a robot's behaviour
from functools import reduce

cCANDLE=0
cTODO = 1
cPOSN = 2
cBP=3 # base price
cTP=4 # target price
cSL=5 # save loss
cCASH=6 #money
cDECN=7 # number of decisions
cSCORE=8 # score recorded on event

class BAF(object):
    def __init__(self, topic, cnt, lam, obj):
        self.cnt = cnt
        self.topic = topic
        self.lam = lam
        self.obj = obj
        self.before = lam(obj)
        
    def baf(self, nobj = None, echo=True):
        self.after = self.lam( nobj if(nobj is not None) else self.obj)
        aaa = (self.topic, self.cnt, self.before, self.after)
        if(echo):
            print(aaa)
        else:
            return aaa
        
def nrnd(a, ndigits=7):
    return round(a,ndigits) if(a is not None) else None


def weightedAverage(pairList):
    if(len(pairList)==0): return None
    a,b = reduce(lambda P,p: (P[0]+p[0]*p[1], P[1]+p[1]) if(p[0] is not None) else P, pairList, (0,0))
    return a/b if(b!=0) else None

def onPositions(looper, lFN):
    return list(map(lFN, looper.positions))



def study(singleCandleIterator, strategy, posMaker, looper, trailSpecs, money, stuff):
    cnt = 0
    strategy.initialize()
    for t in singleCandleIterator:
        if(cnt % 1000==0): print(t.time)
        cnt+=1
        strategy.digestLowCandle(t)
        decisions = strategy.decision(looper, posMaker)
        rsMax =0.0
        for dec in decisions:
            event,todo,benef,benefRatio,rs1,pos1 = dec
            if(rs1 is not None and (type(rs1) is float) and rs1>rsMax): rsMax = rs1
            if(todo == 'take-position'):
                pos1.calibrateTrailingStopLossDesireForSteppedSpecs(t,trailSpecs, strategy.mspread, looper.instrument.minimumTrailingStopDistance)
                looper.positions.append(pos1)
                moneyOnClose, margin, profit,equity1, freeMargin1, marginLevel1 = posMaker.positionFootprint(looper,pos1,t,money)
                print(('position', cnt, pos1.relevantPrice(t), margin, freeMargin1, marginLevel1))
            elif(todo == 'close'):
                moneyOnClose, margin, profit,equity1, freeMargin1, marginLevel1 = posMaker.positionFootprint(looper,pos1,t,money)
                money  = moneyOnClose
                pos1Time,beforeCount = pos1.entryQuote.time, len(looper.positions)
                looper.positions = list([p for p in looper.positions if p.entryQuote.time != pos1Time])
                print(('close',cnt, event, profit, margin, freeMargin1, marginLevel1))
            elif(todo == 'flip-position'):
                # when flip-position, the pos1 item is actual a pair of positions. (newer position, closing position)
                closePos = pos1[1]
                pos1 = pos1[0]
                # with the oanda API, to flip from 1lot BUY to a 2lot SELL, we push a  3lot SELL through the API
                # in simulation, the robot will send a 3lot SELL, so let's account for it correctly here.
                newPosArray = list([p for p in looper.positions if p.entryQuote.time != closePos.entryQuote.time])
                if(len(newPosArray) != len(looper.positions)-1):
                    raise RuntimeError("bug - unable to remove closing postion (in simulation)")
                pos1.size -= closePos.size
                if(pos1.size<0):
                    raise RuntimeError("bug - position size rendered negative...")
                elif(pos1.size>0):
                     newPosArray.append(pos1)

                moneyOnClose, margin, profit,equity1, freeMargin1, marginLevel1 = posMaker.positionFootprint(looper,closePos,t,money)
                money = moneyOnClose

                print(('fp', cnt, event, profit, margin, freeMargin1, marginLevel1))
                looper.positions = newPosArray
            elif(todo == 'trailing-stop'):
                pos1.setTrailingStop(t)
                print(('ts >> ', cnt, nrnd(pos1.trailingStopValue)))
                
            elif(todo == 'trailing-progress'):
                baf = BAF('tp', cnt, lambda p: nrnd(p.trailingStopValue), pos1)
                pos1.updateTrailingStopValue(t)
                baf.baf()
                
            elif(todo == 'trailing-update'):
                bafD = BAF('tu', cnt, lambda p: nrnd(p.trailingStopDistance), pos1)
                pos1.trailingStopDistance = pos1.trailingStopDesiredDistance
                bafD.baf()
                bafV = BAF('tu/tp', cnt, lambda p: nrnd(p.trailingStopValue), pos1)
                pos1.updateTrailingStopValue(t)
                pos1.trailingStopNeedsReplacement = False
                bafV.baf()
                
            elif(todo == 'hold' or todo == 'wait'):
                if(pos1 is not None):
                    pos1.calibrateTrailingStopLossDesireForSteppedSpecs(t, trailSpecs, strategy.mspread, looper.instrument.minimumTrailingStopDistance)
        # all decisions are processed,
        # we want to draw:
        # - the price, aka candle
        # - number of positions pending/held
        # - average base price of positions held
        # - average target price of positions held
        # - average safety/stop-close for positions
        # - remaining money
        posN = len(looper.positions)
        avgBasePrice = weightedAverage(onPositions(looper,lambda p: (p.entryPrice(), p.size)))
        avgTargetPrice = weightedAverage(onPositions(looper,lambda p: (p.takeProfit, p.size)))
        avgSaveLossPrice = weightedAverage(onPositions(looper, \
                    lambda p: (p.saveLoss if(p.trailingStopValue is None) else p.trailingStopValue, 1)))
        stuff.append( (t, todo,posN, avgBasePrice, avgTargetPrice, avgSaveLossPrice, money, len(decisions), rsMax) )
    return stuff



def narrowRanges(stuff3, leeway=20):
    global cPOSN
    WWW3 = len(stuff3)
    www3 = [ (True if(stuff3[i][2]>0) else \
            (True if(i+leeway<WWW3 and stuff3[i+leeway][cPOSN]>0) else \
            (True if(i-leeway>=0 and stuff3[i-leeway][cPOSN]>0) else False))) for i in range(WWW3) ]

    fn0_reducer = lambda X,v: X if(X!=0) else v

    def firstScore(stuff3, n,p):
        """first non zero score in the range [n,p) """
        for t in range(n,p):
            if(stuff3[t][cSCORE]>0): return round(stuff3[t][cSCORE],4)
        return 0.0

    def money(stuff3, n):
        return round(stuff3[n][cCASH],3)


    boundaries = [ i for i in range(WWW3-1) if(www3[i] != www3[i+1]) ]
    ranges = [ (boundaries[i], boundaries[i+1], \
                firstScore(stuff3, boundaries[i], boundaries[i+1]), \
                money(stuff3, boundaries[i]), round(money(stuff3, boundaries[i+1])-money(stuff3, boundaries[i]),4) ) for i in range(len(boundaries)-1) if i%2 == 0 ]
    return list(ranges)
