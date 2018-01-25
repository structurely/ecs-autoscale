import logging
import os

import boto3


LOG_LEVEL_STR = os.environ.get("LOG_LEVEL", "info")
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR.upper())

logging.basicConfig(level=LOG_LEVEL)

# Initialize boto3 clients.
ecs_client = boto3.client('ecs')
asg_client = boto3.client('autoscaling')
cdw_client = boto3.client('cloudwatch')
