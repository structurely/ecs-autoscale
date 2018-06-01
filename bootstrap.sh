#!/bin/sh
# ==============================================================================
# This script bootstraps the setup process for the Lambda function:
#
#  1. Creates an IAM policy with the right permissions for the Lambda function.
#  2. Creates an IAM role for the Lambda function and attaches the policy.
#  3. Build a deployment package.
#  4. Create a Lambda function on AWS with the role attached and upload the
#     deployment package.
#
# ==============================================================================

echo "Creating IAM policy called ecs-autoscale-policy"

policy_arn=$(aws iam create-policy \
    --policy-name ecs-autoscale-policy \
    --policy-document file://policy.json | \
    grep "Arn" | \
    sed -E 's/.*Arn\": \"([^"]+)\".*/\1/')

echo "Created policy $policy_arn"

echo "Creating IAM role called ecs-autoscale-role"

role_arn=$(aws iam create-role \
    --role-name ecs-autoscale-role \
    --assume-role-policy-document file://role.json | \
    grep "Arn" | \
    sed -E 's/.*Arn\": \"([^"]+)\".*/\1/')

echo "Created role $role_arn"

echo "Attaching policy to role"

aws iam attach-role-policy \
    --role-name ecs-autoscale-role \
    --policy-arn $policy_arn

echo "Waiting for role to be registered"

sleep 5

echo "Creating deployment package"

cd lambda && zip -r ../deployment.zip * && cd -

echo "Creating Lambda function ecs-autoscale"

aws lambda create-function \
    --function-name ecs-autoscale \
    --zip-file fileb://deployment.zip \
    --role $role_arn \
    --handler "lambda_function.lambda_handler" \
    --runtime "python3.6" \
    --timeout 10 \
    --memory-size 128
