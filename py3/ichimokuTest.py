
from oscillators import IchimokuCalculation
from myt_support import TradeLoop
import oandaconfig
import v20,math



cfg = oandaconfig.Config()
cfg.load("~/.v20.conf")
api = v20.Context( cfg.hostname, cfg.port, token = cfg.token)

looper = TradeLoop(api, cfg.active_account, 'EUR_USD', 200*1000.0)

def pad0(v):
    return str(v) if(v>9) else "0"+str(v)
def max(a,b):
    return a if(a>b) else b

def min(a,b):
    return a if(a<b) else b


def makeCandle(day,hr,mi, ex1,ex2, onBid=True, chgRatio=1):
    c = looper.mkCandlestickTemplate()
    cc = c.bid if(onBid) else c.ask

    hi = max(ex1,ex2)
    lo = min(ex1,ex2)
    delta = hi-lo
    mid = 0.5*(ex1+ex2)
    cc.h = hi
    cc.l = lo
    cc.o = mid-chgRatio*delta
    cc.c = mid+chgRatio*delta

    c.time = "201706{}T{}:{}:00.000000000Z".format(pad0(day),pad0(hr),pad0(mi))
    return c



def ZigZag():
    candles = []
    for hr in range(1,6):
        for mi in range(0,59):
            cr = 1 if(mi<30) else -1
            ex1=mi + 2
            ex2=mi
            if(mi<30):
                ex1,ex2=60-ex1,60-ex2
            ff = math.ceil(100+hr*math.log(mi+5))
            candles.append( makeCandle(10,hr,mi,ff+ex1,ff+ex2,True,cr) )
    XX = IchimokuCalculation(10,20)

    print("ctime,bidC,kijun,tenkan,chikou,sendkouA,senkouB")
    for c in candles:
        XX.add(c)
        #print("|{}: {}  {}|{}".format(c.time, c.bid.l, c.bid.h, 0.5*(c.bid.l+c.bid.h)))
        if(XX.full()):
            v = XX.lastVal
            print("{},{},{},{},{},{},{}".format(v.time, v.relevantClosePrice, v.kijun, v.tenkan, v.chikou, v.senkouA, v.senkouB))


ZigZag()
