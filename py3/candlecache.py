

import v20
import datetime


def makeTILL(till):
    if(till is None):
        from datetime import datetime
        now = datetime.utcnow()
        till = now.strftime("%Y-%m-%dT%H%M59.000000000Z")
    return till


def findInstrument(dir, select):
    import json
    with open(dir + "/instruments.json", 'r') as jsonf:
        these = json.load(jsonf)
        for i in these:
            if(i["name"] == select): return i

    return None

class AccountCache(object):
    def __init__(self):
        self.positions = []

class InstrumentCache(object):
    def __init__(self, dictObj):
        self.name = dictObj['name']
        self.pipLocation = dictObj['pipLocation']
        self.displayPrecision = dictObj['displayPrecision']
        self.minimumTrailingStopDistance = dictObj['minimumTrailingStopDistance']
        self.marginRate = dictObj['marginRate']


class FileCacheIterator(object):
    def __init__(self,dir, pair,zslice, since, till):
        self.dir = dir
        self.slice = zslice
        self.pair = pair
        self.since = since
        self.till  = makeTILL(till)
        self.files = []
        self.s3 = None

        sinceMonth = since[:7]
        tillMonth  = till[:7]
        suffix =  ".{}.{}.csv".format(pair, self.slice)
        if(type(dir) is str and dir.lower().startswith('s3://')):
            import boto3
            s3 = boto3.resource('s3')
            s3dir = dir[ len('s3://') :]
            s3path = s3dir.split('/')
            bucket= s3path[0]
            location = '/'.join(s3path[1:])
            sinceLocation = '{}/{}{}'.format(location, sinceMonth,suffix)
            tillLocation = '{}/{}{}'.format(location,tillMonth,suffix)
            buk = s3.Bucket(bucket)

            self.files = list( [ 's3://{}/{}'.format(bucket, obj.key) 
                  for obj in buk.objects.filter(Prefix='{}/'.format(location) )
                  if obj.key.endswith(suffix) and sinceLocation <= obj.key and obj.key <= tillLocation 
            ])
            self.s3 = s3
        else:
            import os
            self.files = [ dir + "/" + f 
                             for f in os.listdir(dir) 
                             if (f.endswith(suffix) and sinceMonth<f and f[:7]<= tillMonth) ]

        self.fileIter = iter(self.files)

    def __iter__(self):
        return self.fileIter

    def __next__(self):
        return next(self.fileIter)



class SliceRowIterator(object):

    def __init__(self,dir, pair, zslice, since, till, ctx=v20.Context("","",token="")):
        import csv
        self.dir = dir
        self.slice = zslice
        self.pair = pair
        self.since = since
        self.till  = makeTILL(till)

        self.fileIterator = FileCacheIterator(dir, pair, zslice,since, till)
        self.ctx = ctx

        self.rowIterator = None

    def acquireNextFile(self):
        zfile = next(self.fileIterator)
        allrows = []

        if(zfile.startswith('s3://')):
            s3 = self.fileIterator.s3
            s3c = s3.meta.client
            s3dir = zfile[ len('s3://') :]
            s3path = s3dir.split('/')
            bucket= s3path[0]
            location = '/'.join(s3path[1:])
            # print((zfile, s3path, bucket,location))
            resp = s3c.get_object(Bucket=bucket, Key=location)
            import io,csv
            with io.BytesIO(resp['Body'].read()) as linestream:
                csvr = csv.reader( (line.strip().decode('utf-8') for line  in linestream.readlines() ) )
        else:
            with open(zfile,'r') as zzf:
                import csv
                csvr = csv.reader(zzf)
       
        for row in csvr:
            if(self.since>row[0]):
                continue
            elif(row[0]<=self.till):
                allrows.append(row)
            else:
                break

        self.rowIterator = iter(allrows) #.__iter__()

    def __iter__(self):
        return self

    def __next__(self):
        if(self.rowIterator is None):
            self.acquireNextFile()

        nxt = None
        try:
            nxt = next(self.rowIterator)
        except StopIteration as e:
            self.acquireNextFile()
            nxt = next(self.rowIterator)

        (ctime, bido, asko,mido, bidl,askl,midl,bidh,askh,midh,bidc,askc,midc,vol) = nxt
        zz = {"time":ctime,"volume":vol}
        zz["bid"] = {"o":bido, "l":bidl, "h":bidh, "c": bidc}
        zz["ask"] = {"o":asko, "l": askl, "h": askh, "c": askc}
        zz["mid"] = {"o":mido, "l": midl, "h": midh, "c": midc}

        return v20.instrument.Candlestick.from_dict(zz, self.ctx)

class SliceIterator(object):
    def __init__(self,zslice, since, till):
        self.slice = zslice
        self.since = since
        self.till  = makeTILL(till)

        self.level = zslice[0]
        self.freq  = int(zslice[1:]) if(len(zslice)>1) else 1

        # yyyy-mm-ddTHH:MM:SS.000000000Z
        #    4  7  10
        #            12,15,18
        kk = "....-..-DDtHH:MM:SS"
        self.basisPosition = kk.find(self.level)
        if(self.basisPosition<0):
            raise ValueError("slice {} is not supported".format(zslice))

        freqMax = 60 if(self.level in ('M','S'))else (24 if(self.level == 'H') else 1)

        if(self.freq>freqMax):
            raise ValueError("slice {} exceed range limit {}".format(zslice, freqMax))

        self.vmx = freqMax
        self.wtag = ({"S":"minutes", "M":"hours", "H":"days"})[self.level]


        paddingH = {"M": (":00", ":59", "00:00"), "S":("","", "00"),
                    "H": (":00:00", ":59:59", "00:00:00"),
                    "D": ("T00:00:00", "T23:59:59", "00:00:00") }
        self.padding = paddingH[ self.level ]

        from datetime import timedelta
        self.add4till= timedelta(seconds = self.freq, microseconds=-1) if(self.level=='S') else (timedelta(minutes=self.freq, microseconds=-1) if(self.level == 'M') else timedelta(hours=self.freq, microseconds=-1))

        self.current= None

    def findNext(self, ts, dbg=False):
        lvl = self.level

        verystable = ts[ :(self.basisPosition-3)]
        stable = ts[(self.basisPosition-3): (self.basisPosition-1) ]
        attach = ts[ (self.basisPosition-1) ]
        variable = ts[ self.basisPosition: (self.basisPosition+2) ]
        postvar = ts[ (self.basisPosition+3):(self.basisPosition+5)]

        if(dbg):
            import pdb; pdb.set_trace()

        vv = int(variable)
        vvb = vv if (vv % self.freq == 0 and postvar == '00') else (self.freq * (1+ (vv/self.freq) ))
        ww = int(stable)
        if(vvb >= self.vmx):
            ww = ww+1
            if( (self.level == 'M' and ww>23) or (self.level == 'S' and ww>59) or (self.level == 'H')):
                from datetime import timedelta, date, datetime, time
                nts = verystable+stable+attach+ (self.padding[2])
                nts_d = datetime.strptime(nts, "%Y-%m-%dT%H:%M:%S")
                add_me = timedelta(minutes=1) if(self.level=='S') else (timedelta(hours=1) if(self.level=='M') else timedelta(days=1))
                bts = nts_d + add_me
                cts = bts + self.add4till
                return (bts.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), cts.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
            else:
                vvb = 0

        vvc = str(vvb + self.freq-1 )
        vvb = str(vvb)
        ww  = str(ww)
        if(len(vvb)==1): vvb = "0" + vvb
        if(len(vvc)==1): vvc = "0" + vvc
        if(len(ww)==1): ww = "0"+ww
        bts = verystable + ww + attach + vvb + self.padding[0] + ".000000000Z"
        cts = verystable + ww + attach + vvc + self.padding[1] + ".999999999Z"
        return (bts,cts)


    def __next__():
        if(self.current is None):
            self.current = self.findNext(self.since)
        else:
            self.current = self.findNext(self.current[1])

        if(not self.current[0]<self.till):
            raise StopIteration

        if(not self.current[1] < self.till):
            self.current[1] = self.till

        return (self.current[0], self.current[1])



# class SliceRowIterator(object):
#     def __init__(self, dir, pair, zslice, since, till):
#         self.pair = pair
#         self.slice = zslice
#         self.dir = dir
#         self.since = since
#         self.till = makeTILL(till)
#
#         self.s5RowIterator = s5RowIterator(self.dir,self.pair,self.slice, self.since,self.till)
#         self.intervalIterator = SliceIterator(self.slice,self.since, self.till)
#
#         self.currentInterval = None
#         self.lastestS5 = None
#
#     def __next__():
#         if(self.currentInterval is None):
#             self.currentInterval = self.intervalIterator.__next__()
#
#
#         for s5 in self.s5RowIterator:
#             if(cmp(s5[0], self.currentInterval[0])==-1):
#                 continue
#             else:
