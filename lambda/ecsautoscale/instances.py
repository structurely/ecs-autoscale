"""Handles scaling of EC2 instances within an ECS cluster."""

import logging
from typing import List, Tuple

from . import ecs_client, asg_client
from .exceptions import ClusterARNError, ASGGroupError, MissingResourceValueError
from .services import Service


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_cluster_arn(cluster_name: str, cluster_list: List[str]) -> str:
    """Find the ARN corresponding to a cluster name."""
    for arn in cluster_list:
        name = arn.split("/")[1]
        if name == cluster_name:
            return arn
    raise ClusterARNError(cluster_name)


def get_asg_group_data(asg_group_name: str, asg_data: dict) -> dict:
    """Retrieve the autoscaling group data."""
    for item in asg_data["AutoScalingGroups"]:
        if item["AutoScalingGroupName"] == asg_group_name:
            return item
    raise ASGGroupError(asg_group_name)


def get_empty_instances(active_container_described: dict) -> dict:
    """Returns an object of empty instances in cluster."""
    empty_instances = {}

    for inst in active_container_described['containerInstances']:
        if inst['runningTasksCount'] == 0 and inst['pendingTasksCount'] == 0:
            empty_instances.update(
                {inst['ec2InstanceId']: inst['containerInstanceArn']}
            )

    return empty_instances


def get_draining_instances(draining_container_described: dict) -> dict:
    """Returns an object of draining instances in cluster."""
    draining_instances = {}

    for inst in draining_container_described['containerInstances']:
        draining_instances.update(
            {inst['ec2InstanceId']: inst['containerInstanceArn']}
        )

    return draining_instances


def retrieve_cluster_data(cluster_arn: str, cluster_name: str) -> dict:
    """Retrieve a dictionary of cluster data."""
    active_container_instances = ecs_client.list_container_instances(
        cluster=cluster_arn,
        status='ACTIVE'
    )

    if active_container_instances['containerInstanceArns']:
        arns = active_container_instances['containerInstanceArns']
        active_container_described = ecs_client.describe_container_instances(
            cluster=cluster_arn,
            containerInstances=arns,
        )
    else:
        logger.warning(
            f"[Cluster: {cluster_name}] No active instances in cluster")
        active_container_described = {"containerInstances": []}

    draining_container_instances = ecs_client.list_container_instances(
        cluster=cluster_arn,
        status='DRAINING'
    )

    if draining_container_instances['containerInstanceArns']:
        arns = draining_container_instances['containerInstanceArns']
        draining_container_described = ecs_client.describe_container_instances(
            cluster=cluster_arn,
            containerInstances=arns,
        )
        draining_instances = get_draining_instances(
            draining_container_described
        )
    else:
        draining_instances = {}
        draining_container_described = {
            "containerInstances": []
        }

    empty_instances = get_empty_instances(active_container_described)

    data = {
        'cluster_name': cluster_name,
        'active_container_described': active_container_described,
        'draining_instances': draining_instances,
        'empty_instances': empty_instances,
        'draining_container_described': draining_container_described
    }

    return data


def drain_instance(cluster_data: dict,
                   instance: dict,
                   is_test_run: bool = False) -> None:
    """Drain an instance."""
    logger.info(
        "[Cluster: {:s}] Draining instance {:s}"
        .format(cluster_data["cluster_name"], instance["ec2InstanceId"])
    )
    if not is_test_run:
        container_instance_id = instance["containerInstanceArn"].split("/")[1]
        ecs_client.update_container_instances_state(
            cluster=cluster_data["cluster_name"],
            containerInstances=[container_instance_id],
            status="DRAINING")


def terminate_instance(cluster_name: str,
                       asg_group_data: dict,
                       ec2_instance_id: str,
                       is_test_run: bool = False) -> None:
    """Completely terminate an instance."""
    logger.info(
        f"[Cluster: {cluster_name}] Terminating instance {ec2_instance_id}")
    if not is_test_run:
        asg_client.terminate_instance_in_auto_scaling_group(
            InstanceId=ec2_instance_id,
            ShouldDecrementDesiredCapacity=True,
        )
        asg_group_data["DesiredCapacity"] -= 1


def get_cpu_avail(instance: dict) -> int:
    for item in instance["remainingResources"]:
        if item["name"] == "CPU":
            return item["integerValue"]
    raise MissingResourceValueError("CPU available")


def get_mem_avail(instance: dict) -> int:
    for item in instance["remainingResources"]:
        if item["name"] == "MEMORY":
            return item["integerValue"]
    raise MissingResourceValueError("memory available")


def get_cpu_used(instance: dict) -> int:
    for item in instance["registeredResources"]:
        if item["name"] == "CPU":
            cpu_registered = item["integerValue"]
            break
    else:
        raise MissingResourceValueError("CPU used")
    return cpu_registered - get_cpu_avail(instance)


def get_mem_used(instance: dict) -> int:
    for item in instance["registeredResources"]:
        if item["name"] == "MEMORY":
            mem_registered = item["integerValue"]
            break
    else:
        raise MissingResourceValueError("memory used")
    return mem_registered - get_mem_avail(instance)


def place_task(instance_tuples: List[Tuple[int, int]],
               cpu: int,
               mem: int) -> Tuple[List[Tuple[int, int]], bool]:
    for i, tup in enumerate(instance_tuples):
        if tup[0] > cpu and tup[1] > mem:
            instance_tuples[i] = (tup[0] - cpu, tup[1] - mem)
            return instance_tuples, True
    return instance_tuples, False


def scale_up(cluster_data: dict,
             cluster_def: dict,
             asg_group_data: dict,
             services: List[Service],
             is_test_run: bool = False) -> bool:
    """
    Check if cluster should scale up.

    We scale out when the services that need to scale cannot fit on the
    existing instances.
    """
    logger.info(
        "[Cluster: {:s}] Checking if we should scale up"
        .format(cluster_data["cluster_name"])
    )
    if asg_group_data["DesiredCapacity"] >= asg_group_data["MaxSize"]:
        logger.warning(
            "[Cluster: {:s}] Max capacity already reached, cannot scale up"
            .format(cluster_data["cluster_name"])
        )
        return False

    instances = [
        (get_cpu_avail(x), get_mem_avail(x)) for x in
        cluster_data["active_container_described"]["containerInstances"]
    ]
    for service in services:
        if service.task_diff <= 0:
            continue
        for _ in range(service.task_diff):
            # Try and place task.
            instances, placeable = place_task(instances, service.task_cpu,
                                              service.task_mem)
            if placeable:
                continue

            # If we can't place the task, need to scale up.
            desired_capacity = asg_group_data["DesiredCapacity"] + 1
            logger.info(
                "[Cluster: {:s}] Scaling cluster up to {} instances"
                .format(cluster_data["cluster_name"], desired_capacity)
            )
            if not is_test_run:
                asg_client.set_desired_capacity(
                    AutoScalingGroupName=cluster_def["autoscale_group"],
                    DesiredCapacity=desired_capacity,
                )
            return True

    logger.info(
        "[Cluster: {:s}] Cluster is sufficiently sized, not scaling up"
        .format(cluster_data["cluster_name"])
    )
    return False


def get_min_cpu_instance(instances: List[dict]) -> dict:
    return min(instances, key=get_cpu_used)


def get_min_mem_instance(instances: List[dict]) -> dict:
    return min(instances, key=get_mem_used)


def allocate_instances(desired_cpu: int,
                       desired_mem: int,
                       instance_tuples: List[Tuple[int, int]]) -> Tuple[List[Tuple[int, int]], bool]:
    for i, item in enumerate(instance_tuples):
        cpu, mem = item
        if desired_cpu < cpu and desired_mem < mem:
            instance_tuples[i] = (cpu - desired_cpu, mem - desired_mem)
            return instance_tuples, True
    return instance_tuples, False


def place_instance(instance: dict,
                   instances: List[dict],
                   services: List[Service]) -> bool:
    """
    Check if we can fit the memory and cpu reserved by this instance onto one
    of the other instances with enough room left over for any services that
    need to scale out.
    """
    other_instances = [(get_cpu_avail(x), get_mem_avail(x)) for x in instances
                       if x["ec2InstanceId"] != instance["ec2InstanceId"]]
    if not other_instances:
        return False

    # First check if we can place the tasks on this instance onto another
    # instance.
    cpu_needed = get_cpu_used(instance)
    mem_needed = get_mem_used(instance)
    other_instances, allocated = allocate_instances(
        cpu_needed,
        mem_needed,
        other_instances)
    if not allocated:
        return False

    # Now check if we still have room left for all of the services that need
    # to scale up.
    for service in services:
        # Ignore services that are scaling down.
        if service.task_diff <= 0:
            continue

        # Try and place task.
        for _ in range(service.task_diff):
            other_instances, placeable = place_task(
                other_instances, service.task_cpu, service.task_mem
            )
            if not placeable:
                return False

    # If we have gotten this far, all new tasks are placeable onto one of the
    # other instances.
    return True


def scale_down(cluster_data: dict,
               asg_group_data: dict,
               services: List[Service],
               is_test_run: bool = False) -> bool:
    """
    Check if cluster should scale down.

    We scale down when the current reserved memory and reserved CPU on the
    instance with either the smallest amount of reserved mem or reserved CPU
    can fit on another instance and when `desired_capacity` > `min_capacity`.
    """
    logger.info(
        "[Cluster: {:s}] Checking if we can scale down"
        .format(cluster_data["cluster_name"])
    )
    if asg_group_data["DesiredCapacity"] <= asg_group_data["MinSize"]:
        logger.warning(
            "[Cluster: {:s}] Min capacity already reached, cannot scale down"
            .format(cluster_data["cluster_name"])
        )
        return False

    instances = \
        cluster_data["active_container_described"]["containerInstances"]

    # First see if we can move all of the tasks from the instance with the
    # smallest amount of reserved memory to another instance.
    min_mem_instance = get_min_mem_instance(instances)
    if place_instance(min_mem_instance, instances, services):
        # Scale down this instance.
        drain_instance(cluster_data, min_mem_instance, is_test_run=is_test_run)
        return True

    # Otherwise see if we can move all of the tasks from the instance with the
    # smallest amount of reserved CPU units to another instance.
    min_cpu_instance = get_min_cpu_instance(instances)
    if place_instance(min_cpu_instance, instances, services):
        # Scale down this instance.
        drain_instance(cluster_data, min_cpu_instance, is_test_run=is_test_run)
        return True

    logger.info(
        "[Cluster: {:s}] Scale down conditions not met, doing nothing"
        .format(cluster_data["cluster_name"])
    )
    return False


def log_instances(cluster_name: str,
                  instances: List[dict],
                  status: str = "active") -> None:
    for instance in instances:
        logger.info(
            "[Cluster: {:s}] Instance {:s} ({:s}):\n"
            " => Reserved CPU units:  {:d}\n"
            " => Available CPU units: {:d}\n"
            " => Reserved memory:     {:d} MB\n"
            " => Available memory:    {:d} MB\n"
            " => Running task count:  {:d}"
            .format(
                cluster_name,
                instance["ec2InstanceId"],
                status,
                get_cpu_used(instance),
                get_cpu_avail(instance),
                get_mem_used(instance),
                get_mem_avail(instance),
                instance["runningTasksCount"],
            )
        )


def _scale_ec2_instances(cluster_data: dict,
                         cluster_def: dict,
                         asg_group_data: dict,
                         services: List[Service],
                         is_test_run: bool = False) -> bool:
    active_instances = \
        cluster_data["active_container_described"]["containerInstances"]
    draining_instances = \
        cluster_data["draining_container_described"]["containerInstances"]
    logger.info(
        "[Cluster: {:s}] Current state:\n"
        " => Active instances:   {:d}\n"
        " => Draining instances: {:d}\n"
        " => Desired capacity:   {:d}\n"
        " => Minimum capacity:   {:d}\n"
        " => Maximum capacity:   {:d}"
        .format(
            cluster_data["cluster_name"],
            len(active_instances),
            len(draining_instances),
            asg_group_data["DesiredCapacity"],
            asg_group_data["MinSize"],
            asg_group_data["MaxSize"],
        )
    )
    log_instances(cluster_data["cluster_name"], active_instances)
    log_instances(cluster_data["cluster_name"], draining_instances,
                  status="draining")

    # Terminate any empty draining instances.
    for instance in draining_instances:
        running_tasks = instance["runningTasksCount"]
        if running_tasks:
            continue
        terminate_instance(
            cluster_data["cluster_name"],
            asg_group_data,
            instance["ec2InstanceId"],
            is_test_run=is_test_run,
        )

    # Check if we should scale up.
    scaled = scale_up(
        cluster_data,
        cluster_def,
        asg_group_data,
        services,
        is_test_run=is_test_run,
    )
    if scaled:
        return True

    # If we didn't scale up, check if we should scale down.
    scaled = scale_down(
        cluster_data,
        asg_group_data,
        services,
        is_test_run=is_test_run,
    )
    return scaled


def scale_ec2_instances(cluster_name: str,
                        cluster_def: dict,
                        asg_data: dict,
                        cluster_list: List[str],
                        services: List[Service],
                        is_test_run: bool = False) -> int:
    """
    Scale EC2 instances in a cluster. Returns -1 if the maximum capacity of the
    cluster is 0, otherwise returns 1 if a scaling event occured, and 0 if not.
    """
    # Gather data needed.
    asg_group_name = cluster_def["autoscale_group"]
    asg_group_data = get_asg_group_data(asg_group_name, asg_data)
    cluster_arn = get_cluster_arn(cluster_name, cluster_list)
    cluster_data = retrieve_cluster_data(
        cluster_arn,
        cluster_name,
    )

    # Adjust min and max requirements if cluster def does not match
    # asg_group_data. We treat the values in the cluster def as the truth.
    min_instances = cluster_def.get("min")
    max_instances = cluster_def.get("max")
    if min_instances is not None and max_instances is not None:
        if min_instances != asg_group_data["MinSize"] or \
                max_instances != asg_group_data["MaxSize"]:
            logger.warning(
                "[Cluster: {:s}] Mismatched min or max size of cluster with "
                "autoscaling group data. Using settings from cluster"
                "definition:\n"
                " => Minimum: {:d}\n"
                " => Maximum: {:d}"
                .format(cluster_name, min_instances, max_instances)
            )
            if not is_test_run:
                asg_client.update_auto_scaling_group(
                    AutoScalingGroupName=cluster_def["autoscale_group"],
                    MinSize=min_instances,
                    MaxSize=max_instances,
                )
            asg_group_data["MinSize"] = min_instances
            asg_group_data["MaxSize"] = max_instances

    # Attempt scaling.
    res = _scale_ec2_instances(
        cluster_data,
        cluster_def,
        asg_group_data,
        services,
        is_test_run=is_test_run,
    )

    if asg_group_data["MaxSize"] == 0:
        return -1
    return int(res)
