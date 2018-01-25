#!/usr/bin/env bash

# Setup virtualenv.
echo "Creating virtualenv ecs-autoscale"
which python3 | mkvirtualenv ecs-autoscale -p
workon ecs-autoscale
cd python-lambda
pip install -r requirements.txt
 -s `python -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())"` packages
deactivate
cd -

# Create policy and get resulting policy arn.
echo "Creating IAM policy called ecs-autoscale-policy"
policy_arn=$(aws iam create-policy \
    --policy-name ecs-autoscale-policy \
    --policy-document file://policy.json | \
    grep "Arn" | \
    sed -E 's/.*Arn\": \"([^"]+)\".*/\1/')

echo "Created policy $policy_arn"

# Create execution role.
echo "Creating IAM role called ecs-autoscale-role"
role_arn=$(aws iam create-role \
    --role-name ecs-autoscale-role \
    --assume-role-policy-document file://role.json | \
    grep "Arn" | \
    sed -E 's/.*Arn\": \"([^"]+)\".*/\1/')

echo "Created role $role_arn"

# Attach policy to role.
aws iam attach-role-policy \
    --role-name ecs-autoscale-role \
    --policy-arn $policy_arn

# Build the deployment package.
echo "Building Lambda deployment package"
find . | grep -E "(__pycache__|\.pyc|\.pyo$$)" | xargs rm -rf
cd python-lambda
zip -r ../deployment.zip *
cd -

# Create lambda function.
echo "Creating Lambda function ecs-autoscale"
aws lambda create-function \
    --function-name ecs-autoscale \
    --zip-file fileb://deployment.zip \
    --role $role_arn \
    --runtime "python3.6" \
    --timeout 10 \
    --memory-size 128

echo "Success!"
