import boto3

# Initialize boto3 clients.
ecs_client = boto3.client('ecs')
cw_client = boto3.client('cloudwatch')
asg_client = boto3.client('autoscaling')
