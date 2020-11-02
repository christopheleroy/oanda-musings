#!/bin/bash

tmp=$(mktemp -d /tmp/building.XXXXXXXZ)

here=$(dirname $0)
there=$(pwd -P)

cp ${here}/handler.py ${here}/../v20config.py ${tmp}/

cd ${tmp}
zip -r ${there}/${here}/RobotSimulation.zip .

cd ${there}
rm -rf ${tmp}


