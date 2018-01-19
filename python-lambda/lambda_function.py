#!/usr/bin/env python

"""
Lambda function to autoscale ECS clusters.
"""

import datetime
import inspect
import logging
import os
import sys

base_path = os.path.dirname(os.path.abspath(inspect.stack()[0][1]))
sys.path.append(os.path.join(base_path, "./packages/"))

import yaml
import boto3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

from autoscaling.ec2_instances import scale_ec2_instances


# Load cluster autoscaling definitions.
clusters_defs_path = os.path.join(
    base_path,
    "./clusters.yml"
)
cluster_defs = yaml.load(open(clusters_defs_path, "r"))


def lambda_handler(event, context):
    """
    Main function which is invoked by AWS Lambda.
    """
    logger.info("Got event {}".format(event))
    for cluster_name in cluster_defs["clusters"]:
        try:
            cluster_def = cluster_defs["clusters"][cluster_name]
            if not cluster_def["enabled"]:
                logger.warning(
                    "[Cluster: {}] Skipping since not enabled"\
                    .format(cluster_name)
                )
                continue

            # Scale up EC2 instances.
            scale_ec2_instances(cluster_name, cluster_def)
        except Exception as ex:
            logger.exception(ex)


if __name__ == "__main__":
    lambda_handler(1, 2)
