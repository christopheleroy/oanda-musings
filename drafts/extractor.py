

import argparse, re, pdb, time
import oandaconfig
import v20, csv

import Alfred
from myt_support import TradeLoop, trailSpecsFromStringParam, getSortedCandles, getBacktrackingCandles, PositionFactory

parser = argparse.ArgumentParser()

parser.add_argument('--select', nargs='?',
                    help="valid currency-pair")
parser.add_argument('--dir', nargs='?', help='target directory')
parser.add_argument('--slice', nargs='?', default="M1")

parser.add_argument('--year', nargs='?', type=int, default = None)
parser.add_argument('--month', nargs='?', type=int, default = None)
args = parser.parse_args()


cfg = oandaconfig.Config()
cfg.load("~/.v20.conf")
api = v20.Context( cfg.hostname, cfg.port, token = cfg.token)

import datetime
today = datetime.date.today()
if(args.year is None): args.year = today.year
if(args.month is None): args.month = today.month

def collectForMonth(pair, year, month, dir, granularity="S5"):
    kwargs = {"granularity":granularity, "price":"MBA"}

    batches = ( ("00:00:00", "03:59:59"), ("04:00:00", "07:59:59"),
                ("08:00:00", "11:59:59"), ("12:00:00", "15:59:59"),
                ("16:00:00", "19:59:59"), ("20:00:00", "23:59:59"))

    daysOfMonth = (00,31,28,31,30,31,30,31,31,30,31,30,31)
    days = daysOfMonth[month]
    month = str(month)
    if(len(month)==1): month = "0" + month
    if(month=="02"):
        if(year % 4 == 0 and (not day % 100 ==0 or day % 400 ==0)):
            days+=1

    allCandles = []
    timeToBreak = False
    header = ["time", "bid-o", "ask-o", "mid-o", "bid-l", "ask-l", "mid-l", "bid-h", "ask-h", "mid-h", "bid-c", "ask-c", "mid-c", "volume"]
    for day in range(days):
        d = str(day+1)
        if(len(d)==1): d = "0" + d

        dstamp = "{}-{}-{}".format(year,month,d)
        for b in batches:
            fromTs = "{}T{}.000000000Z".format(dstamp, b[0])
            toTs   = "{}T{}.000000000Z".format(dstamp, b[1])
            kwargs["fromTime"]=fromTs
            kwargs["toTime"]=toTs
            print kwargs
            resp = api.instrument.candles(pair, **kwargs)
            # import pdb; pdb.set_trace()
            if(str(resp.status) != '200'):

                if(resp.body.has_key("errorMessage") and resp.body["errorMessage"] == "Invalid value specified for 'to'. Time is in the future"):
                    del kwargs['toTime']
                    print kwargs
                    resp = api.instrument.candles(pair, **kwargs)
                    timeToBreak = True
                else:
                    print resp.body

            candles = resp.get('candles',200)
            candles.sort(lambda a,b: cmp(a.time, b.time))
            for c in candles:
                if(len(allCandles)>1 and cmp(c.time, allCandles[-1][0])<0): continue
                row = [c.time, c.bid.o, c.ask.o, c.mid.o, c.bid.l, c.ask.l, c.mid.l, c.bid.h, c.ask.h, c.mid.h, c.bid.c, c.ask.c, c.mid.c, c.volume ]
                allCandles.append(row)
            if(timeToBreak): break
        if(timeToBreak): break


    with open( "{}/{}-{}.{}.{}.csv".format(dir, year, month, pair, granularity), "wb") as outf:
        csvwriter = csv.writer(outf)
        for r in allCandles:
            csvwriter.writerow(r)


collectForMonth(args.select, args.year, args.month, args.dir, args.slice)
