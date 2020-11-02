
updateAPIKEY=${MUSINGSAPIKEY}
simulationAPIKEY=${MUSINGSAPIKEY}

APIGW=https://rdvb28k5z0.execute-api.us-east-1.amazonaws.com/default

#instruments=(EUR_USD AUD_USD)
instruments=(EUR_USD AUD_USD NZD_USD USD_CAD USD_CHF USD_JPY GBP_USD)
months=(1 2 3 4 5 6 7 8)
#sims=(basic1323-2f basic1723-2f basic1733-2f basic1333-2f)
sims=(basic1323-2f basic1723-2f basic1733-2f basic1333-2f basic1323-2f-xos6 basic1323-2f-xos4 basic1323-2f-xos3 basic1323-2f-xos7)
slices=(M1 M5 M15 M30)

declare -A xmap=(
[--year]=year
[--m2m]=m2m
[--sim]=sim
[--slice]=slice
[--start]=start
[--end]=end
)

while [ ! -z "$1" ]; 
do
	case "$1" in 
		--year|--m2m|--slice|--start|--end|--sim)
			eval "${xmap[$1]}=$2"
			shift;shift;
			;;
		*)
			echo param $1 not understood
			exit 9
			;;
	esac
done

# present anumeric with a 0 padded if  less than 10
function n2() {
	if [ "$1" -lt 10 ]; then
		echo "0"$(expr $1 + 1 - 1)
	else
		echo "$1"
	fi
}

if [ -z "$slice" ]; then
	echo will run through all slices ${slices[@]}
else
	slices=($slice)
fi

if [ -z "$sim" ]; then
	echo will run though all simulations ${sims[@]}
else
	sims=($sim)
fi

if [ -z "$start" -a -z "$end" ]; then
	if [ -z "$year" -o -z "$m2m" ]; then
		echo both --year and --m2m are required
		exit 9
	else
		y0=${year}
		m0=$(echo $m2m | awk -F- '{print $1}')
		y1=${year}
		m1=$(echo $m2m | awk -F- '{print $2}')
		if [ -z "$m1" ]; then
			m1=$(expr $m0 + 1)
		fi
		while [ "$m1" -gt 12 ]; do
			y1=$(expr $y1 + 1)
			m1=$(expr $m1 - 12)
		done
		m0=$(n2 $m0)
		m1=$(n2 $m1)
		start=${y0}-${m0}
	        end=${y1}-${m1}
	fi
elif [ -z "$start" -o -z "$end" ]; then
	echo --start and --end must be both passed
	exit 9
fi





function simulation() {
	sel=$1
	slice=$2
	key=$3
	_start=$4
	_end=$5

	curl -H 'x-api-key: '$simulationAPIKEY  $APIGW/'RobotSimulation?select='$sel'&slice='$slice'&key='$key'&start='$_start'&end='$_end >/dev/null 2>&1 &
}

for i in ${instruments[@]}; do
  for x in ${slices[@]}; do
	for s in ${sims[@]}; do
		echo 	simulation $i $x $s $start $end
		simulation $i $x $s $start $end
	done
  done
done

n=$(jobs -p | wc -l)
while [ $n -gt 1 ]; do
	echo $n jobs pending $(date)
	sleep 1
	n=$(jobs -p | wc -l)
	if [ $n -eq 1 ]; then
		jobs -p
	fi
done

	

