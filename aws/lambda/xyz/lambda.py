
import handler, boto3

event = {
  "select": "EUR_USD",
  "fmin": "60",
  "key3": "value3"
}

handler.lambda_aggregate(event, None)

