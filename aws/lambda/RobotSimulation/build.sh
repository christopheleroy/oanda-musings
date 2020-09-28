#!/bin/bash
s3repo=s3://oanda-musings-data-cache/lambdas
#listing=handler.py ../v20config.py ../../../py3/extractor.py ../../../py3/candlecache.py
basis=~/RobotSimulation-basis.zip
############################################################################################

me=$0
here=$(dirname $0)

if [ -z "$here" ]; then 
    here=$(pwd)
fi

cd "$here"
here=$(pwd)

target=$(basename $here)
targetzip=$target.zip

targetdir=/tmp/$target.$(date -Is).$$.dir
targetbasis=/tmp/$target.$(date -Is).$$.basis.zip



mkdir ${targetdir}
cd ${targetdir}
if [ "$basis" == "yes" ]; then
    aws s3 cp $s3repo/${target}-basis.zip $targetbasis
    unzip "$targetbasis" >/dev/null 2>&1
    rm $targetbasis
elif [ -f "$basis" ]; then   
    unzip "$basis" >/dev/null
fi

for f in handler.py ../v20config.py ../../../py3/extractor.py \
         ../../../py3/{Alfred,Bibari,candlecache,forwardInstrument,livecandlehierarchy,myt_support,oscillators,robologger,Student,teeth,superargs,timespecs}.py
do
    cp ${here}/$f  ${targetdir}
done

cd ${targetdir}
rm ../$targetzip
zip -r9 -q ../$targetzip .
rm -rf ${targetdir}

echo aws s3 cp /tmp/$targetzip s3://oanda-musings-data-cache/lambdas/$targetzip

