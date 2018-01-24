#!/usr/bin/env python

"""
Lambda function to autoscale ECS clusters.
"""

from copy import deepcopy
import datetime
import inspect
import logging
import os
import re
import sys

base_path = os.path.dirname(os.path.abspath(inspect.stack()[0][1]))
sys.path.append(os.path.join(base_path, "./packages/"))

import yaml
import boto3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

from autoscaling import asg_client, ecs_client
from autoscaling.ec2_instances import scale_ec2_instances
from autoscaling.services import gather_services, Service


# Load cluster autoscaling definitions.
clusters_defs_path = os.path.join(
    base_path,
    "clusters/"
)

base_cluster_defs = {}
for fname in os.listdir(clusters_defs_path):
    if not fname.endswith(".yml"):
        continue
    path = os.path.join(clusters_defs_path, fname)
    cluster_name = os.path.splitext(fname)[0]
    with open(path, "r") as f:
        raw = f.read()
        # Replace env variables in the yaml defs.
        for match, env_var in re.findall(r"(%\(([A-Za-z_]+)\))", raw):
            raw = raw.replace(match, os.environ[env_var])
    base_cluster_defs[cluster_name] = yaml.load(raw)


def clusters():
    """
    Returns an iterable list of cluster names.
    """
    response = ecs_client.list_clusters()
    if not response['clusterArns']:
        logger.warning('No ECS cluster found')
        return []
    return response["clusterArns"]


def lambda_handler(event, context):
    """
    Main function which is invoked by AWS Lambda.
    """
    logger.info("Got event {}".format(event))

    is_test_run = event == "TEST_RUN"
    if is_test_run:
        logger.warning("Going through test run, will not actually scale anything")

    # Initialize data.
    cluster_defs = deepcopy(base_cluster_defs)
    cluster_list = clusters()
    asg_data = asg_client.describe_auto_scaling_groups()

    for cluster_name in cluster_defs:
        try:
            cluster_def = cluster_defs[cluster_name]

            # Skip cluster if not enabled.
            if not cluster_def["enabled"]:
                logger.warning(
                    "[Cluster: {}] Skipping since not enabled"\
                    .format(cluster_name)
                )
                continue

            # (1 / 4) Collect individual services in the cluster that will need 
            # to be scaled.
            services = gather_services(cluster_name, cluster_def)
            n_services = len(services)
            logger.info(
                "[Cluster: {}] Found {:d} services that need to scale"\
                .format(cluster_name, n_services)
            )

            # (2 / 4) Add a fake task to account for CPU buffer and mem buffer.
            if cluster_def["cpu_buffer"] > 0 or cluster_def["mem_buffer"] > 0:
                logger.info(
                    "[Cluster: {}] Buffer size requested:\n"\
                    " => CPU buffer:    {}\n"\
                    " => Memory buffer: {} MB"\
                    .format(cluster_name, cluster_def["cpu_buffer"], 
                            cluster_def["mem_buffer"])
                )
                buffer_service = Service(cluster_name, None, None, 1,
                                         service_type="buffer",
                                         min_tasks=1,
                                         max_tasks=2)
                buffer_service.task_cpu = cluster_def["cpu_buffer"]
                buffer_service.task_mem = cluster_def["mem_buffer"]
                buffer_service.task_diff = 1
                services.append(buffer_service)

            # (3 / 4) Scale EC2 instances according to the tasks that need to be
            # scaled. We first check if we can place all new needed tasks on the
            # existing instances. If not, we scale out.
            #
            # If we do not need to scale out, we check if we can place all of
            # tasks from the instance with the smallest amount of reserved
            # memory or CPU onto another instance in the cluster. And then
            # still have room for all services that need to scale out.
            res = scale_ec2_instances(
                cluster_name, cluster_def, asg_data, cluster_list, services,
                is_test_run=is_test_run,
            )
            if res == -1:
                if n_services > 0:
                    logger.warning(
                        "[Cluster: {}] Cannot scale services since max capacity is 0"\
                        .format(cluster_name)
                    )
                # No instances in the cluster or something else went wrong.
                continue

            # (4 / 4) Scale services. First do all services that are scaling 
            # down, then the ones that are scaling up.
            for service in sorted(services, key=lambda x: x.task_diff):
                service.scale(is_test_run=is_test_run)

        except Exception as ex:
            logger.exception(ex)


if __name__ == "__main__":
    lambda_handler("TEST_RUN", 2)
