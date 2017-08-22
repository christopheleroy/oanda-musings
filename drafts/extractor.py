

import argparse, re, pdb, time
import oandaconfig
import v20, csv

from myt_support import TradeLoop, trailSpecsFromStringParam, getSortedCandles, getBacktrackingCandles, PositionFactory

parser = argparse.ArgumentParser()

parser.add_argument('--select', nargs='?',
                    help="valid currency-pair")
parser.add_argument('--dir', nargs='?', help='target directory')
parser.add_argument('--slice', nargs='?', default="M1")
parser.add_argument('--quick', action='store_true', help='to quickly extend a cache for what is missing in the month')
parser.add_argument('--year', nargs='?', type=int, default = None)
parser.add_argument('--month', nargs='?', type=int, default = None)
parser.add_argument('--instruments', action='store_true')

args = parser.parse_args()


cfg = oandaconfig.Config()
cfg.load("~/.v20.conf")
api = v20.Context( cfg.hostname, cfg.port, token = cfg.token)

import datetime
today = datetime.date.today()
if(args.year is None): args.year = today.year
if(args.month is None): args.month = today.month

def collectInstruments(dir):
    import json
    instResp    = api.account.instruments(cfg.active_account)
    instruments = instResp.get('instruments','200')
    stuff = map(lambda i: {"name": i.name, "pipLocation": i.pipLocation,
                           "displayPrecision": i.displayPrecision,
                           "minimumTrailingStopDistance": i.minimumTrailingStopDistance}, instruments)

    with open((dir + "/instruments.json"), 'wb') as jsonf:
        json.dump(stuff, jsonf)


def collectForMonth(pair, year, month, dir, granularity="S5", refresh=True):
    kwargs = {"granularity":granularity, "price":"MBA"}

    batches = ( ("00:00:00", "03:59:59"), ("04:00:00", "07:59:59"),
                ("08:00:00", "11:59:59"), ("12:00:00", "15:59:59"),
                ("16:00:00", "19:59:59"), ("20:00:00", "23:59:59"))

    precache = []

    daysOfMonth = (00,31,28,31,30,31,30,31,31,30,31,30,31)
    days = daysOfMonth[month]
    month = str(month)
    if(len(month)==1): month = "0" + month
    if(month=="02"):
        if(year % 4 == 0 and (not day % 100 ==0 or day % 400 ==0)):
            days+=1

    if(not refresh):
        from candlecache import SliceRowIterator
        _since = "{}-{}-{}T00:00:00.000000000Z".format(year, month, "01")
        _till  = "{}-{}-{}T23:59:59:999999999Z".format(year, month, days)
        precache = list( SliceRowIterator(dir,pair,granularity, _since, _till, api) )

    allCandles = []
    timeToBreak = False

    if(len(precache)>0 and not refresh):
        for c in precache:
            row = [c.time, c.bid.o, c.ask.o, c.mid.o, c.bid.l, c.ask.l, c.mid.l, c.bid.h, c.ask.h, c.mid.h, c.bid.c, c.ask.c, c.mid.c, c.volume ]
            allCandles.append(row)

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
            if(not refresh):
                if(len(allCandles)>0 and cmp(toTs, allCandles[-1][0])<0):
                    # no need to refresh what is way in the past...
                    continue

            print kwargs
            resp = api.instrument.candles(pair, **kwargs)
            # import pdb; pdb.set_trace()
            if(str(resp.status) != '200'):

                if(resp.body.has_key("errorMessage") and resp.body["errorMessage"] == "Invalid value specified for 'to'. Time is in the future"):
                    del kwargs['toTime']
                    print ('future is not accepted', kwargs)
                    resp = api.instrument.candles(pair, **kwargs)
                    timeToBreak = True
                else:
                    print resp.body

            candles = resp.get('candles',200)
            candles.sort(lambda a,b: cmp(a.time, b.time))
            for c in candles:
                if(len(allCandles)>0 and cmp(c.time, allCandles[-1][0])<0): continue
                row = [c.time, c.bid.o, c.ask.o, c.mid.o, c.bid.l, c.ask.l, c.mid.l, c.bid.h, c.ask.h, c.mid.h, c.bid.c, c.ask.c, c.mid.c, c.volume ]
                allCandles.append(row)
            if(timeToBreak): break
        if(timeToBreak): break


    with open( "{}/{}-{}.{}.{}.csv".format(dir, year, month, pair, granularity), "wb") as outf:
        csvwriter = csv.writer(outf)
        for r in allCandles:
            csvwriter.writerow(r)


if(not args.instruments):
    collectForMonth(args.select, args.year, args.month, args.dir, args.slice, not args.quick)
else:
    collectInstruments(args.dir)
