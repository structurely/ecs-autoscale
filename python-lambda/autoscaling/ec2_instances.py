"""
Handles scaling of EC2 instances within an ECS cluster.
"""

import datetime
import logging

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

from . import ecs_client, asg_client


def get_cluster_arn(cluster_name, cluster_list):
    for arn in cluster_list:
        name = arn.split("/")[1]
        if name == cluster_name:
            return arn
    else:
        logger.error(
            "Could not find cluster arn for cluster {}".format(cluster_name)
        )


def get_asg_group_data(asg_group_name, asg_data):
    for item in asg_data["AutoScalingGroups"]:
        if item["AutoScalingGroupName"] == asg_group_name:
            return item
    else:
        logger.error(
            "Could not find autoscaling group with name {}".format(asg_group_name)
        )


def empty_instances(clusterArn, activeContainerDescribed):
    """
    Returns a object of empty instances in cluster.
    """
    instances = []
    empty_instances = {}

    for inst in activeContainerDescribed['containerInstances']:
        if inst['runningTasksCount'] == 0 and inst['pendingTasksCount'] == 0:
            empty_instances.update(
                {inst['ec2InstanceId']: inst['containerInstanceArn']}
            )

    return empty_instances


def draining_instances(clusterArn, drainingContainerDescribed):
    """
    Returns an object of draining instances in cluster.
    """
    instances = []
    draining_instances = {}

    for inst in drainingContainerDescribed['containerInstances']:
        draining_instances.update(
            {inst['ec2InstanceId']: inst['containerInstanceArn']}
        )

    return draining_instances


def retrieve_cluster_data(cluster_arn, cluster_name):
    activeContainerInstances = ecs_client.list_container_instances(
        cluster=cluster_arn,
        status='ACTIVE'
    )

    if activeContainerInstances['containerInstanceArns']:
        activeContainerDescribed = ecs_client.describe_container_instances(
            cluster=cluster_arn,
            containerInstances=activeContainerInstances['containerInstanceArns']
        )
    else:
        logger.warning(
            "[Cluster: {}] No active instances in cluster"\
            .format(cluster_name)
        )
        activeContainerDescribed = {
            "containerInstances": []
        }

    drainingContainerInstances = ecs_client.list_container_instances(
        cluster=cluster_arn,
        status='DRAINING'
    )
    if drainingContainerInstances['containerInstanceArns']:
        drainingContainerDescribed = ecs_client.describe_container_instances(
            cluster=cluster_arn,
            containerInstances=drainingContainerInstances['containerInstanceArns']
        )
        drainingInstances = draining_instances(
            cluster_arn,
            drainingContainerDescribed
        )
    else:
        drainingInstances = {}
        drainingContainerDescribed = {
            "containerInstances": []
        }

    emptyInstances = empty_instances(cluster_arn, activeContainerDescribed)

    dataObj = {
        'clusterName': cluster_name,
        'activeContainerDescribed': activeContainerDescribed,
        'drainingInstances': drainingInstances,
        'emptyInstances': emptyInstances,
        'drainingContainerDescribed': drainingContainerDescribed
    }

    return dataObj


def drain_instance(container_instance_id, cluster_name):
    ecs_client.update_container_instances_state(
        cluster=cluster_name,
        containerInstances=[container_instance_id],
        status="DRAINING",
    )


def terminate_instance(ec2_instance_id):
    asg_client.terminate_instance_in_auto_scaling_group(
        InstanceId=ec2_instance_id,
        ShouldDecrementDesiredCapacity=True,
    )


def remove_instance(cluster_data, cluster_def, asg_group_data, instance):
    logger.info(
        "[Cluster: {}] Draining instance {}"\
        .format(cluster_data["clusterName"], instance["ec2InstanceId"])
    )
    drain_instance(
        instance["containerInstanceArn"].split("/")[1],
        cluster_data["clusterName"],
    )
    logger.info(
        "[Cluster: {}] Terminating instance {}"\
        .format(cluster_data["clusterName"], instance["ec2InstanceId"])
    )
    terminate_instance(
        instance["ec2InstanceId"],
    )
    asg_client.set_desired_capacity(
        AutoScalingGroupName=cluster_def["autoscale_group"],
        DesiredCapacity=asg_group_data["DesiredCapacity"] - 1,
    )


def get_cpu_avail(instance):
    for item in instance["remainingResources"]:
        if item["name"] == "CPU":
            return item["integerValue"]
    return None


def get_mem_avail(instance):
    for item in instance["remainingResources"]:
        if item["name"] == "MEMORY":
            return item["integerValue"]
    return None


def get_cpu_used(instance):
    for item in instance["registeredResources"]:
        if item["name"] == "CPU":
            cpu_registered = item["integerValue"]
            break
    else:
        logger.error("No value for registered CPU found")
        return None
    return cpu_registered - get_cpu_avail(instance)


def get_mem_used(instance):
    for item in instance["registeredResources"]:
        if item["name"] == "MEMORY":
            mem_registered = item["integerValue"]
            break
    else:
        logger.error("No value for registered MEMORY found")
        return None
    return mem_registered - get_mem_avail(instance)


def scale_up(cluster_data, cluster_def, asg_group_data):
    """
    Check if cluster should scale up.

    We scale out when there is less than `cpu_buffer` or less than `mem_buffer`
    on all instances and when `desired_capacity` < `max_capacity`.
    """
    logger.info(
        "[Cluster: {}] Checking if we should scale up"\
        .format(cluster_data["clusterName"])
    )
    if asg_group_data["DesiredCapacity"] >= asg_group_data["MaxSize"]:
        logger.warning(
            "[Cluster: {}] Max capacity already reached, cannot scale up"\
            .format(cluster_data["clusterName"])
        )
        return False

    cpu_buffer = cluster_def["cpu_buffer"]
    mem_buffer = cluster_def["mem_buffer"]
    for instance in cluster_data["activeContainerDescribed"]["containerInstances"]:
        cpu_avail = get_cpu_avail(instance)
        mem_avail = get_mem_avail(instance)
        if cpu_avail >= cpu_buffer and mem_avail >= mem_buffer:
           logger.info(
               "[Cluster: {}] Cluster is sufficiently sized, not scaling up"\
               .format(cluster_data["clusterName"])
           )
           return False

    desired_capacity = asg_group_data["DesiredCapacity"] + 1
    logger.info(
        "[Cluster: {}] Scaling cluster up to {} instances"\
        .format(cluster_data["clusterName"], desired_capacity)
    )
    asg_client.set_desired_capacity(
        AutoScalingGroupName=cluster_def["autoscale_group"],
        DesiredCapacity=desired_capacity,
    )
    return True


def get_min_cpu_instance(instances):
    return min(instances, key=lambda x: get_cpu_used(x))


def get_min_mem_instance(instances):
    return min(instances, key=lambda x: get_mem_used(x))


def allocate_instances(desired_cpu, desired_mem, instance_tuples):
    for i, item in enumerate(instance_tuples):
        cpu, mem = item
        if desired_cpu < cpu and desired_mem < mem:
            instance_tuples[i] = (cpu - desired_cpu, mem - desired_mem)
            return instance_tuples, True
    return instance_tuples, False


def place_instance(instance, instances, cluster_def):
    other_instances = [(get_cpu_avail(x), get_mem_avail(x)) for x in instances
                       if x["ec2InstanceId"] != instance["ec2InstanceId"]]
    logger.debug(other_instances)
    if not other_instances:
        return False

    # Check if we can fit the memory and cpu reserved by this instance onto one
    # of the other instances with enough room left over for the CPU and mem buffers.
    cpu_needed = get_cpu_used(instance) + cluster_def["cpu_buffer"]
    mem_needed = get_mem_used(instance) + cluster_def["mem_buffer"]
    other_instances, allocated = allocate_instances(
        cpu_needed,
        mem_needed,
        other_instances,
    )
    logger.debug(other_instances)
    return allocated


def scale_down(cluster_data, cluster_def, asg_group_data):
    """
    Check if cluster should scale down.

    We scale down when the current reserved memory and reserved CPU on the
    instance with either the smallest amount of reserved mem or reserved CPU
    can fit on another instance and when `desired_capacity` > `min_capacity`.
    """
    logger.info(
        "[Cluster: {}] Checking if we can scale down"\
        .format(cluster_data["clusterName"])
    )
    if asg_group_data["DesiredCapacity"] <= asg_group_data["MinSize"]:
        logger.warning(
            "[Cluster: {}] Min capacity already reached, cannot scale down"\
            .format(cluster_data["clusterName"])
        )
        return False

    instances = cluster_data["activeContainerDescribed"]["containerInstances"]

    # First see if we can move all of the tasks from the instance with the smallest 
    # amount of reserved memory to another instance.
    min_mem_instance = get_min_mem_instance(instances)
    if place_instance(min_mem_instance, instances, cluster_def):
        # Scale down this instance.
        remove_instance(
            cluster_data, cluster_def, asg_group_data, min_mem_instance
        )
        return True

    # Otherwise see if we can move all of the tasks from the instance with the 
    # smallest amount of reserved CPU units to another instance.
    min_cpu_instance = get_min_cpu_instance(instances)
    if place_instance(min_cpu_instance, instances, cluster_def):
        # Scale down this instance.
        remove_instance(
            cluster_data, cluster_def, asg_group_data, min_cpu_instance
        )
        return True

    logger.info(
        "[Cluster: {}] Scale down conditions not met, doing nothing"\
        .format(cluster_data["clusterName"])
    )
    return False


def log_instances(cluster_name, instances, status="active"):
    for instance in instances:
        logger.info(
            "[Cluster: {}] Instance {} ({}):\n"\
            " => Reserved CPU units:  {}\n"\
            " => Available CPU units: {}\n"\
            " => Reserved memory:     {} MB\n"\
            " => Available memory:    {} MB"\
            .format(
                cluster_name,
                status,
                instance["ec2InstanceId"],
                get_cpu_used(instance),
                get_cpu_avail(instance),
                get_mem_used(instance),
                get_mem_avail(instance),
            )
        )


def _scale_ec2_instances(cluster_data, cluster_def, asg_group_data):
    """
    Scale a cluster up or down if requirements are met, otherwise do nothing.
    """
    logger.info(
        "[Cluster: {}] Current state:\n"\
        " => Minimum capacity: {}\n"\
        " => Maximum capacity: {}\n"\
        " => Desired capacity: {}\n"\
        " => CPU buffer:       {}\n"\
        " => Memory buffer:    {} MB"
        .format(
            cluster_data["clusterName"],
            asg_group_data["MinSize"],
            asg_group_data["MaxSize"],
            asg_group_data["DesiredCapacity"],
            cluster_def["cpu_buffer"],
            cluster_def["mem_buffer"],
        )
    )

    active_instances = cluster_data["activeContainerDescribed"]["containerInstances"]
    log_instances(cluster_data["clusterName"], active_instances)

    draining_instances = cluster_data["drainingContainerDescribed"]["containerInstances"]
    log_instances(cluster_data["clusterName"], draining_instances, status="draining")

    # Check if we should scale up.
    scaled = scale_up(
        cluster_data,
        cluster_def,
        asg_group_data,
    )
    if scaled: return True

    # If we didn't scale up, check if we should scale down.
    scaled = scale_down(
        cluster_data,
        cluster_def,
        asg_group_data,
    )
    return scaled


def scale_ec2_instances(cluster_name, cluster_def, asg_data, cluster_list):
    """
    Scale EC2 instances in a cluster. Returns -1 if the maximum capacity of the
    cluser is 0, otherwise returns 1 if a scaling event occured, and 0 if not.
    """
    # Gather data needed.
    asg_group_name = cluster_def["autoscale_group"]
    asg_group_data = get_asg_group_data(asg_group_name, asg_data)
    cluster_arn = get_cluster_arn(cluster_name, cluster_list)
    cluster_data = retrieve_cluster_data(
        cluster_arn,
        cluster_name,
    )

    # Attempt scaling.
    res = _scale_ec2_instances(
        cluster_data,
        cluster_def,
        asg_group_data,
    )

    if asg_group_data["MaxSize"] == 0:
        return -1
    return int(res)
