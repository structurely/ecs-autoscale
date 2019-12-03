# pylint: disable=wrong-import-position
"""Lambda function for autoscaling ECS clusters and services."""

import inspect
import logging
import os
import re
import sys
from typing import List

BASE_PATH = os.path.dirname(os.path.abspath(inspect.stack()[0][1]))
sys.path.append(os.path.join(BASE_PATH, "./packages/"))

import yaml

from ecsautoscale import asg_client, ecs_client, LOG_LEVEL
from ecsautoscale.instances import scale_ec2_instances
from ecsautoscale.services import gather_services, Service


logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)


def load_yaml(path: str) -> dict:
    """Load a YAML file into a dict object."""
    with open(path, "r") as yamlfile:
        raw = yamlfile.read()
        # Replace env variables in the yaml defs.
        for match, env_var in re.findall(r"(%\(([A-Za-z_]+)\))", raw):
            raw = raw.replace(match, os.environ[env_var])
    data = yaml.load(raw)
    return data


def load_cluster_defs() -> dict:
    """Load YAML cluster definitions."""
    cluster_defs = {}
    clusters_defs_path = os.path.join(BASE_PATH, "clusters/")
    for fname in os.listdir(clusters_defs_path):
        if not fname.endswith(".yml"):
            continue
        path = os.path.join(clusters_defs_path, fname)
        cluster_name = os.path.splitext(fname)[0]
        data = load_yaml(path)
        cluster_defs[cluster_name] = data
    return cluster_defs


def clusters() -> List[str]:
    """Return an iterable list of cluster names."""
    response = ecs_client.list_clusters()
    if not response['clusterArns']:
        logger.warning('No ECS cluster found')
        return []
    return response["clusterArns"]


def lambda_handler(event, context):
    """
    Pull metrics and check to see which clusters and services should scale.

    This is the function called by AWS Lambda. The 'event' and 'context' are
    given by AWS, but we currently don't do anything with them.
    """
    # pylint: disable=unused-argument,broad-except
    logger.info(event)

    is_test_run = event == "TEST_RUN"
    if is_test_run:
        logger.warning(
            "Going through test run, will not actually scale anything"
        )

    # Initialize data.
    cluster_defs = load_cluster_defs()
    cluster_list = clusters()
    asg_data = asg_client.describe_auto_scaling_groups()
    if 'NextToken' in asg_data:
        asg_data['AutoScalingGroups'] += asg_client.describe_auto_scaling_groups(
            NextToken=asg_data['NextToken']
        )['AutoScalingGroups']

    for cluster_name in cluster_defs:
        try:
            cluster_def = cluster_defs[cluster_name]

            # Skip cluster if not enabled.
            if not cluster_def["enabled"]:
                logger.warning(
                    "[Cluster: {:s}] Skipping since not enabled"
                    .format(cluster_name)
                )
                continue

            # (1 / 4) Collect individual services in the cluster that will need
            # to be scaled.
            services = gather_services(cluster_name, cluster_def)
            n_services = len(services)
            logger.info(
                "[Cluster: {:s}] Found {:d} services that need to scale"
                .format(cluster_name, n_services)
            )

            # (2 / 4) Add a fake task to account for CPU buffer and mem buffer.
            if cluster_def["cpu_buffer"] > 0 or cluster_def["mem_buffer"] > 0:
                logger.info(
                    "[Cluster: {:s}] Buffer size requested:\n"
                    " => CPU buffer:    {:d}\n"
                    " => Memory buffer: {:d} MB"
                    .format(cluster_name, cluster_def["cpu_buffer"],
                            cluster_def["mem_buffer"])
                )
                buffer_service = Service(cluster_name, None, None, 1,
                                         min_tasks=1,
                                         max_tasks=2)
                buffer_service.task_cpu = cluster_def["cpu_buffer"]
                buffer_service.task_mem = cluster_def["mem_buffer"]
                buffer_service.task_diff = 1
                services.append(buffer_service)

            # (3 / 4) Scale EC2 instances according to the tasks that need to
            # be scaled. We first check if we can place all new needed tasks on
            # the existing instances. If not, we scale out.
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
                        "[Cluster: {:s}] Cannot scale services since max"
                        "capacity is 0"
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


def run_test():
    """Run a test event locally."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    opts = parser.parse_args()
    if opts.test:
        test_event = "TEST_RUN"
    else:
        test_event = 1
    lambda_handler(test_event, 2)


if __name__ == "__main__":
    run_test()
