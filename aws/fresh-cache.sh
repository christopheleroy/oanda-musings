
updateAPIKEY=${MUSINGSAPIKY}
simulationAPIKEY=${MUSINGSAPIKEY}

APIGW=https://rdvb28k5z0.execute-api.us-east-1.amazonaws.com/default

#instruments=(EUR_USD AUD_USD)
slices=(M1 M5 M15 M30)

month=$1
year=$2

if [ -z "$month" -a -z "$year" ]; then
	month=$(date +%m)
	year=$(date +%Y)
elif [ -z "year" -a "$month" -gt 2017 ]; then
	year=$month
	month=$(date +%m)
fi

if [ "$month" -ge 1 -a "$month" -le 12 ]; then
	echo For month: $month
else
	echo Bad month: $month
	exit 7
fi

if [ "$year" -gt 2017 -a "$year" -le $(date +%Y) ]; then
	echo and for year: $year

else
	echo Bad Year: $year
	exit 9
fi



function updatecandle() {
	sel=$1
	slice=$2
	year=$3
	month=$4
	curl -H 'x-api-key: '$updateAPIKEY  -X POST $APIGW/'updatecandlecache?select='$sel'&slice='$slice'&year='$year'&month='$month >/dev/null 2>&1 &

}

for i in $(aws --profile tof s3 cp s3://oanda-musings-data-cache/candles/instruments.json - | jq -r '.[]|.name')
do
	for s in ${slices[@]}; do
		echo updatecandle $i $s $year $month
		updatecandle $i $s $year $month
	done
	sleep 0.25
	jc=$(jobs | wc -l)
	test "$jc" -gt 10 && echo "Jobs still running: $jc"
done


	

