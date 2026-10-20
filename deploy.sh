#!/usr/bin/env bash
# Deploy bin-reminder to AWS Lambda with two daily EventBridge schedules.
set -euo pipefail

FUNCTION_NAME="bin-reminder"
ROLE_NAME="bin-reminder-lambda-role"
RULE_7PM="bin-reminder-schedule"
RULE_9PM="bin-reminder-schedule-9pm"
RUNTIME="python3.12"

# ---------------------------------------------------------------------------
# Region
# ---------------------------------------------------------------------------
REGION=$(aws configure get region 2>/dev/null || true)
if [[ -z "$REGION" ]]; then
  read -rp "AWS region (e.g. eu-west-2): " REGION
fi
echo "Region: $REGION"

# ---------------------------------------------------------------------------
# Secrets / config
# ---------------------------------------------------------------------------
echo ""
echo "Enter your configuration:"
read -rsp "  VM_TOKEN       (Voice Monkey API key)      : " VM_TOKEN; echo
read -rp  "  VM_DEVICE      (Voice Monkey device ID)    : " VM_DEVICE
read -rp  "  VM_PROXY_URL   (Cloudflare Worker URL)     : " VM_PROXY_URL
DEFAULT_IMAGE_URL="https://bin-reminder-images-106573904151.s3.eu-west-2.amazonaws.com"
read -rp  "  IMAGE_BASE_URL (Enter for S3 default)      : " IMAGE_BASE_URL
IMAGE_BASE_URL="${IMAGE_BASE_URL:-$DEFAULT_IMAGE_URL}"

# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo ""
echo "Account: $ACCOUNT_ID"

# ---------------------------------------------------------------------------
# 1. IAM execution role
# ---------------------------------------------------------------------------
echo ""
echo "==> IAM role"
TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

if aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
  echo "    Already exists, skipping."
else
  aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document "$TRUST" \
    >/dev/null
  aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "    Created. Waiting 10 s for IAM to propagate..."
  sleep 10
fi

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo "    $ROLE_ARN"

# ---------------------------------------------------------------------------
# 2. Package
# ---------------------------------------------------------------------------
echo ""
echo "==> Packaging"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
if [[ ! -f bins.csv ]]; then
  echo "    ERROR: bins.csv not found. Run: KIRKLEES_UPRN=<uprn> python3 fetch_dates.py"
  exit 1
fi
zip -q bin_reminder.zip bin_reminder.py bins.csv
echo "    bin_reminder.zip created (bin_reminder.py + bins.csv)"

# ---------------------------------------------------------------------------
# 3. Lambda function (create or update)
# ---------------------------------------------------------------------------
echo ""
echo "==> Lambda function"
ENV_VARS="Variables={VM_TOKEN=${VM_TOKEN},VM_DEVICE=${VM_DEVICE},VM_PROXY_URL=${VM_PROXY_URL},IMAGE_BASE_URL=${IMAGE_BASE_URL}}"

if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" &>/dev/null; then
  echo "    Updating existing function..."
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file fileb://bin_reminder.zip \
    --region "$REGION" >/dev/null
  aws lambda wait function-updated \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION"
  aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --environment "$ENV_VARS" \
    --region "$REGION" >/dev/null
else
  echo "    Creating new function..."
  aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime "$RUNTIME" \
    --role "$ROLE_ARN" \
    --handler "bin_reminder.lambda_handler" \
    --zip-file fileb://bin_reminder.zip \
    --environment "$ENV_VARS" \
    --timeout 60 \
    --region "$REGION" >/dev/null
fi

LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}"
echo "    $LAMBDA_ARN"

# ---------------------------------------------------------------------------
# 4. EventBridge rules — 7 PM and 9 PM UK time (19:00 + 21:00 UTC / GMT)
# ---------------------------------------------------------------------------
add_rule() {
  local rule_name="$1"
  local cron="$2"
  local sid="$3"
  echo ""
  echo "==> EventBridge rule: $rule_name ($cron UTC)"
  local rule_arn
  rule_arn=$(aws events put-rule \
    --name "$rule_name" \
    --schedule-expression "cron($cron)" \
    --state ENABLED \
    --region "$REGION" \
    --query RuleArn --output text)
  echo "    $rule_arn"
  aws lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id "$sid" \
    --action "lambda:InvokeFunction" \
    --principal "events.amazonaws.com" \
    --source-arn "$rule_arn" \
    --region "$REGION" >/dev/null 2>&1 \
    || echo "    Permission already set."
  aws events put-targets \
    --rule "$rule_name" \
    --targets "Id=1,Arn=$LAMBDA_ARN" \
    --region "$REGION" >/dev/null
}

add_rule "$RULE_7PM" "0 19 * * ? *" "EventBridgeInvoke7pm"
add_rule "$RULE_9PM" "0 21 * * ? *" "EventBridgeInvoke9pm"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "All done. Lambda runs every evening at 19:00 UTC (7 PM GMT) and 21:00 UTC (9 PM GMT)."
echo ""
echo "To test it now (grey bin day):"
echo "  aws lambda invoke --function-name $FUNCTION_NAME --region $REGION \\"
echo "    --cli-binary-format raw-in-base64-out \\"
echo "    /tmp/out.json && cat /tmp/out.json"
