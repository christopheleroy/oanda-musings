#!/bin/bash

me=/tmp/$(date -Is).me.$$.dir

BATCHTYPE=${BATCHTYPE-py3}

mkdir -p "$me/s3zip"
mkdir -p $me/run

if [ -z "$BATCH_S3ZIP" ];
    aws cp "$BATCH_S3ZIP" "$me/s3zip/thezip.zip" || echo Failed retrieving prescribed zip $BATCH_S3ZIP && exit 100
    cd "$me/s3zip"
    unzip thezip.zip  || echo Failed extracting zip archive && exit 99


    cd $me/run
    cat >batch-script.py <<EofScript
import handler
import os

event = os.environ

handler.$BATCHFUNCTION(event,None)

EofScript
    export PYTHONPATH=$me/s3zip
    python3 batch-script.py
    exit $?

else
    echo variable BATCH_S3ZIP is required
    exit 80
fi







