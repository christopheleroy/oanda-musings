

import json, os, boto3, os.path
import v20config
from base64 import b64decode
import datetime
import extractor

# Lambda Instance Initialization:
if(not os.environ['S3_CACHE'].startswith('s3://')):
    raise RuntimeError("S3_CACHE must be a s3:// URI")
    
BUCKET = os.path.dirname(os.environ['S3_CACHE'])[ len('s3://'): ]
if(len(BUCKET)<10):
    raise RuntimeError("S3_CACHE bucket is unlikely...")
CACHEDIR =os.environ['S3_CACHE'][ (len(BUCKET)+len('s3://')+1) : ]

if('CLEAR_SECRET' in os.environ and os.environ['CLEAR_SECRET'].upper() == 'YES'):
    DECRYPTED = os.environ['SECRET_TOKEN']
else:
    ENCRYPTED = os.environ['SECRET_TOKEN']
    DECRYPTED = boto3.client('kms').decrypt(CiphertextBlob=b64decode(ENCRYPTED))['Plaintext'].decode('utf-8')

s3 = boto3.client("s3")

# The Handler !
# --------------------===================================================------------------------------

def whathappens(event, context):
    print(event)

    return {
        'statusCode': 200,
        'body': json.dumps(event)
    }


def lambda_handler(event, context):
    
    cfg = v20config.Config()

    params = event['queryStringParameters'] if 'queryStringParameters' in event else event

    print(json.dumps(params))
    print(DECRYPTED)

    cfg.load_from_v20event(event['v20'] if ('v20'in event) else None, DECRYPTED)

    api = cfg.create_context()
    
    zparam = lambda k: params[k] if(k in params) else os.environ[k]
    
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
    allCandles = extractor.collectForMonth(api, zparam('select'), year, month, '/tmp', zparam('slice'), False )
    # save file in /tmp but upload to S3:
    tempFile = extractor.fileLocation(zparam('select'), year, month, '/tmp', zparam('slice'))
    cacheFile = extractor.fileLocation(zparam('select'), year, month, CACHEDIR, zparam('slice'))
    extractor.writeCollectedCandles(zparam('select'), year, month, '/tmp', zparam('slice'), allCandles)
    
    print((tempFile, BUCKET, cacheFile))
    
    s3.upload_file(tempFile, BUCKET, cacheFile)
    os.unlink(tempFile)
    
    
    # TODO implement
    return {
        'statusCode': 200,
        'body': json.dumps({'updated': 's3://{}/{}'.format(BUCKET, cacheFile)})
    }
