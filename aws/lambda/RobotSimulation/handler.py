# lambda handlers


import json, os, boto3, os.path
import v20config
from base64 import b64decode
import datetime, dateutil.parser
import extractor, candlecache, myt_support
import Alfred, Bibari, Student

# Lambda Instance Initialization:
if(not os.environ['S3_CACHE'].startswith('s3://')):
    raise RuntimeError("S3_CACHE must be a s3:// URI")
    
BUCKET = os.path.dirname(os.environ['S3_CACHE'])[ len('s3://'): ]
if(len(BUCKET)<10):
    raise RuntimeError("S3_CACHE bucket is unlikely...")
CACHEDIR =os.environ['S3_CACHE'][ (len(BUCKET)+len('s3://')+1) : ]

if('KMSVALS' in os.environ):
    kmsc = boto3.client('kms')

    for k in os.environ['KMSVALS'].split(','):
        if(k in os.environ):
            val = os.environ[k]
            try:
                os.environ[k] = kmsc.decrypt(CiphertextBlob=b64decode(val))['Plaintext'].decode('utf-8')
            except:
                raise

SECRET_TOKEN = os.environ['SECRET_TOKEN'] if('SECRET_TOKEN' in os.environ) else None


s3 = boto3.client("s3")

# The Handlers !
# --------------------===================================================------------------------------

def whathappens(event, context):
    print(event)

    return {
        'statusCode': 200,
        'body': json.dumps(event)
    }


def handle_cleanSimulations(event, context):
    pass


def cleanSimulations(ordinalStart, startingSum=5000):
    import re, os.path
    from functools import reduce

    s3r = boto3.resource('s3')
    bbok = s3r.Bucket(BUCKET)

    oldish = re.compile("{}{}{}{}".format(str(ordinalStart), r'-\.', str(startingSum), r'\.csv'))
    
    deletecandidates = [ obj.key for obj in bbok.objects.filter(Prefix="simulations/out") if oldish.search(obj.key) is not None ]

    def organize(mapped, key):
        x = tease(key)
        kkey = "None"
        if(x is not None):
             kkey = ".".join([x[0], x[1], x[2], x[3], x[5] )
        if(kkey not in mapped): mapped[kkey]=[]
        mapped[kkey].append( (key, x[4]) )
        return mapped

    mapped = reduce(organize, deletecandidates, {})
    
    for kkey in mapped.keys():
        best = reduce(lambda kmax, k: k if(kmax is None or kmax[1]<k[1]) else kmax, mapped[kkey], None)
        deletes = [ k[0] in mapped[kkey] if(k[0] != best[0]) ]
        print('not deleting s3://{}/{}'.format(BUCKET, best[0]))
        for k in deletes:
            print('deleting s3://{}/{} ...'.format(BUCKET, k))
            s3.delete_object(Bucket=BUCKET, Key=k)


def build_aggregate(bucket, start, end, select, sims, fmin,fmax, selected, compress=True):
    import csv,io, dateutil.parser

    dtStart = dateutil.parser.parse(start)
    dtEnd   = dateutil.parser.parse(end)

    oStart = dtStart.toordinal()
    oEnd   = dtEnd.toordinal()

    filename = '{}.{}-{}.{}.{}.{}.csv'.format(select,fmin,fmax,start,end, ('Z' if compress else 'a'))
    tempFile = '/tmp/{}'.format(filename)

    with open('/tmp/{}'.format(filename), 'w') as FOUT:
        csvw = csv.writer(FOUT)
        header = ['ctime', 
                  'bido', 'asko', 'mido', 
                  'bidl', 'askl', 'midl', 
                  'bidh', 'askh', 'midh',
                  'bidc', 'askc','midc', 'vol',
                  'action', 'posN', 
                  'avgBasePrice', 'avgTargetPrice', 'avgSaveLossPrice',
                  'money', 'lenDecisions', 'rsMax', 
                  'pair', 'slice', 'config', 'freq', 'added' ]
        csvw.writerow(header)

        for ks in selected:
            key, slice, config, so, eo, mo, freq = ks
            print('get s3://{}/{}'.format(bucket, key))
            resp = s3.get_object(Bucket=bucket, Key=key)
            with io.BytesIO(resp['Body'].read()) as linestream:
                csvstream = (line.strip().decode('utf-8') for line  in linestream.readlines())
                csvr = csv.reader(csvstream)
                waitCount = 0
                holdCount = 0
                rows = 0
                wrows = 0
                lastMoney = 0
                for r in csvr:
                    dt = dateutil.parser.parse(r[0])
                    if( (dt - dtStart).total_seconds() >=0 and (dt - dtEnd).total_seconds() <=0):
                        rows += 1

                        action = r[14]
                        if(action == 'hold'): 
                            holdCount += 1
                            waitCount = 0
                            if(compress and holdCount>2): continue
                        elif(action == 'wait'):
                            waitCount += 1
                            holdCount = 0
                            if(compress and waitCount>2): continue
                        
                        r.append(select)
                        r.append(slice)
                        r.append(config)
                        r.append(freq)
                        rmoney = float(r[19])
                        dmoney = None if(action != 'close' and action != 'flip-position') else (rmoney - lastMoney)
                        lastMoney = rmoney
                        r.append(dmoney)
                        wrows +=1
                        csvw.writerow(r)
            print('reading s3://{}/{} : wrote {} rows among {} qualified rows'.format(bucket, key, wrows, rows))
    aggFile = '{}/agg/{}'.format(sims,filename)
    s3.upload_file(tempFile, bucket, aggFile)
    os.unlink(tempFile)

    return {'saved': 's3://{}/{}'.format(bucket,aggFile)}



def tease(s3Key): 
    """ break the s3Key to find details of the simulation"""
    import os.path
    from myt_support import frequency
    teased = os.path.basename(s3Key).split('.')
    if (len(teased) != 6 or teased[5].upper() != 'CSV' or not "-" in teased[3]):
        return None

    select = teased[0]
    slice = teased[1]
    config = teased[2]
    ordRange = teased[3]
    ors= ordRange.split("-")
    so = int(ors[0])
    eo = int(ors[1])
    mo = int(teased[4])
    freq = frequency(slice)

    return (select, slice, config, so,eo, mo, freq)





def lambda_aggregate(event, context):
    import os

    params = event['queryStringParameters'] if 'queryStringParameters' in event else event
    paramd = lambda k,ddef: params[k] if(k in params) else (os.environ[k] if k in os.environ else ddef)

    sdef, edef = "2019-01-01T00:00:00Z", "2019-07-30T22:00:10Z"

    select = paramd('select', 'EUR_USD')
    tFrom = paramd('from', sdef)
    eFrom = paramd('till', edef)
    sims  = paramd('sims', 'simulations')
    fmin  = int(paramd('fmin', '60')) # by default, do not consider frequencies below 60 seconds (don't aggregate over S30 or S5 for example)
    fmax  = int(paramd('fmax',  '43200'))  # by default, do no consider frequencies above half-day (don't aggregate below H12 or D or W)

    
    startPAD = "XXXX-01-01T00:00:00Z"
    endPAD   = "XXXX-12-31T23:59:59Z"

    # Pad the start/end specs for a complete spec
    START = '{}{}'.format(tFrom, startPAD[ len(tFrom): ])
    END   = '{}{}'.format(eFrom,   endPAD[ len(eFrom): ])

    dtStart = dateutil.parser.parse(START)
    dtEnd   = dateutil.parser.parse(END)

    oStart = dtStart.toordinal()
    oEnd   = dtEnd.toordinal()

    s3r = boto3.resource('s3')
    bbk = s3r.Bucket(BUCKET)

    # import os.path, re
    # from myt_support import frequency
    # tease = re.compile('{}{}'.format(select, r'\.([MSH])(\d*)\.([^\.]+)\.(\d+)-(\d+)\.(\d+)\.csv'))
    selectThem = [ obj.key for obj in bbk.objects.filter(Prefix='{}/out/{}.'.format(sims, select)) ]
    selected = []
    for s in selectThem:
        # ss = os.path.basename(s)
        m = tease(s)
        if(m is not None):
            # mg = m.groups()
            # slice = '{}{}'.format(mg[0], mg[1])
            # config = mg[2]
            # so = int(mg[3])
            # eo = int(mg[4])
            # mo = int(mg[5])
            # freq = frequency(slice)
            select, slice, config, so, eo, mo, freq = m
            # frequency  ok?
            if(freq > fmax or freq < fmin): continue
            # time stretch meaningful ?
            if((oEnd < so) or (oStart > eo)): continue
            selected.append( (s, slice, config, so, eo, mo, freq) )
            print(selected[-1])

    return {
        'statusCode': 200,
        'body': json.dumps(build_aggregate(BUCKET, START,END, select, sims, fmin, fmax, selected, True))
    }






def lambda_update_candle_handler(event, context):
    
    cfg = v20config.Config()

    params = event['queryStringParameters'] if 'queryStringParameters' in event else event

    print(json.dumps(params))

    cfg.load_from_v20event(event['v20'] if ('v20'in event) else None, SECRET_TOKEN)

    api = cfg.create_context()
    
    param = lambda k: params[k] if(k in params) else os.environ[k]
    
    today = datetime.date.today()
    year = today.year
    month = today.month
    if('year' in params):
        try:
            year = int(params['year'])
        except:
            print (params['year'])
    if('month' in params):
        try:
            month = int(params['month'])
        except:
            print(params['month'])
    
    # extract candles for this month
    allCandles = extractor.collectForMonth(api, param('select'), year, month, '/tmp', param('slice'), False )
    # save file in /tmp but upload to S3:
    tempFile = extractor.fileLocation(param('select'), year, month, '/tmp', param('slice'))
    cacheFile = extractor.fileLocation(param('select'), year, month, CACHEDIR, param('slice'))
    extractor.writeCollectedCandles(param('select'), year, month, '/tmp', param('slice'), allCandles)
    
    print((tempFile, BUCKET, cacheFile))
    
    s3.upload_file(tempFile, BUCKET, cacheFile)
    os.unlink(tempFile)
    
    
    # TODO implement
    return {
        'statusCode': 200,
        'body': json.dumps({'updated': 's3://{}/{}'.format(BUCKET, cacheFile)})
    }



def getSimulationParams(sims, key):
    """read the simulation params from the 'params' file point by key """

    resp = s3.get_object(Bucket=BUCKET, Key= '{}/params/{}.json'.format(sims,key))
    import io, json

    # with io.TextIOWrapper(resp['Body'], encoding='utf-8') as jstream:
    #     params = json.load(jstream)
    text = resp['Body'].read().decode()
    params = json.loads(text)

    money = 5000
    trigger = params['trigger']
    bf=params['profit']
    drp=params['risk']
    dropList = list([ (x[0],x[1]) for x in params['dropList'] ])
    tenkanSize = params['tenkanSize']
    kijunSize = params['kijunSize']
    xoverSize = params['xoverSize']
    insurance = params['insurance']
    tradeSIZE = 10000
    msm  = params['msm']

    return (money, tradeSIZE, trigger, bf, drp, dropList, insurance, msm, tenkanSize, kijunSize, xoverSize)


def lambda_robot_simulation(event, context):

    cfg = v20config.Config()

    params = event['queryStringParameters'] if 'queryStringParameters' in event else event

    print(json.dumps(params))

    cfg.load_from_v20event(event['v20'] if ('v20'in event) else None, SECRET_TOKEN)

    api = cfg.create_context()
    
    param = lambda k: params[k] if(k in params) else os.environ[k]
    paramd = lambda k,default: params[k] if(k in params) else default


    sdef, edef, kdef = "2019-01-01T00:00:00Z", "2019-07-30T22:00:10Z", "basic1323-2f"

    SELECT = param('select')
    SLICE  = paramd('slice', 'M15')
    START  = paramd('start', sdef)
    END    = paramd('end',   edef)
    KEY    = paramd('key', kdef)
    CACHE  = os.environ['S3_CACHE']
    SIMS   = paramd('sims', 'simulations')

    startPAD = "XXXX-01-01T00:00:00Z"
    endPAD   = "XXXX-12-31T23:59:59Z"

    # Pad the start/end specs for a complete spec
    START = '{}{}'.format(START, startPAD[ len(START): ])
    END   = '{}{}'.format(END,   endPAD[ len(END): ])

    dt0 = dateutil.parser.parse(START)
    dt1 = dateutil.parser.parse(END)
    delta = '{}-{}'.format(dt0.toordinal(), dt1.toordinal())

    looper = myt_support.TradeLoop(api, cfg.active_account, SELECT)
    ITER3 = candlecache.SliceRowIterator(CACHE, SELECT,SLICE,START,END)

    money, tradeSIZE, trigger, bf, drp, dropList, insurance, msm, tenkanSize, kijunSize, xoverSize = getSimulationParams(SIMS, KEY)

    bibari = Bibari.TradeStrategy(trigger, bf, drp, SELECT, tradeSIZE, tenkanSize, kijunSize, xoverSize, 'W', SLICE, dropList)
    bibari.turnSingle()

    bibari.riskManagement = Alfred.RiskManagementStrategy.parse(insurance, bibari, {'ichiMaker':True})
    bibari.maxEngagedSize = tradeSIZE * msm

    posMaker = myt_support.PositionFactory(50,50)
    looper.initialize(posMaker)

    stuff3 = []

    Student.study(ITER3, bibari, posMaker, looper, dropList, money,stuff3)

    t0 = stuff3[0][0].time
    t1  = stuff3[-1][0].time
    


    Metadata = {}
    Metadata['slice'] = SLICE
    Metadata['select'] = SELECT
    Metadata['from'] = t0
    Metadata['till'] = t1
    Metadata['mode'] = 'single'
    Metadata['strategy'] = 'Bibari'
    Metadata['request_id'] = context.aws_request_id


    filename = '{}.{}.{}.{}.{}.csv'.format(SELECT, SLICE, KEY, delta, money) 
    tempFile = '/tmp/{}'.format(filename)
    s3FileKey = '{}/out/{}'.format(SIMS, filename)

    with open(tempFile, 'w') as FOUT:
        import csv
        csvw = csv.writer(FOUT)
        Student.csvwriterows(csvw,stuff3)
    
    s3.upload_file(tempFile, BUCKET, s3FileKey, ExtraArgs={'Metadata':Metadata})
    os.unlink(tempFile)


    return {
        'statusCode': 200,
        'body': json.dumps({'saved': 's3://{}/{}'.format(BUCKET, s3FileKey)})
    }

