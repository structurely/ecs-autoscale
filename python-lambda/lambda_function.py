#!/usr/bin/env python

"""
Lambda function to autoscale ECS clusters.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import datetime
import logging
import os
import yaml

import boto3


def clusters(ecs_client, avoid=[]):
    """
    Returns an iterable list of cluster names.
    """
    response = ecs_client.list_clusters()
    if not response['clusterArns']:
        print('No ECS cluster found')
        return []
    return [cluster for cluster in response['clusterArns']
            if not any([x in cluster for x in avoid])] 


def get_cluster_arn(cluster_name, cluster_list):
    for arn in cluster_list:
        name = arn.split("/")[1]
        if name == cluster_name:
            return arn
    else:
        logging.error(
            "Could not find cluster arn for cluster {}".format(cluster_name)
        )


def get_asg_group_data(asg_group_name, asg_data):
    for item in asg_data["AutoScalingGroups"]:
        if item["AutoScalingGroupName"] == asg_group_name:
            return item
    else:
        logging.error(
            "Could not find autoscaling group with name {}".format(asg_group_name)
        )


def cluster_memory_reservation(cw_client, cluster_name):
    """
    Return cluster mem reservation average per minute cloudwatch metric.
    """
    try:
        response = cw_client.get_metric_statistics( 
            Namespace='AWS/ECS',
            MetricName='MemoryReservation',
            Dimensions=[
                {
                    'Name': 'ClusterName',
                    'Value': cluster_name
                },
            ],
            StartTime=datetime.datetime.utcnow() - datetime.timedelta(seconds=120),
            EndTime=datetime.datetime.utcnow(),
            Period=60,
            Statistics=['Average']
        )
        return response['Datapoints'][0]['Average']

    except Exception:
        logging.error(
            "ClusterMemoryError: Could not retrieve mem reservation for {}"\
            .format(cluster_name)
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


def retrieve_cluster_data(ecs_client, cw_client, asg_client, cluster_arn, cluster_name):
    logging.info("Retreiving data for {} cluster".format(cluster_name))
    activeContainerInstances = ecs_client.list_container_instances(
        cluster=cluster_arn, 
        status='ACTIVE'
    )
    clusterMemReservation = cluster_memory_reservation(cw_client, cluster_name)
    
    if activeContainerInstances['containerInstanceArns']:
        activeContainerDescribed = ecs_client.describe_container_instances(
            cluster=cluster_arn, 
            containerInstances=activeContainerInstances['containerInstanceArns']
        )
    else: 
        logging.warning("No active instances in cluster")
        return None

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
        drainingContainerDescribed = [] 

    emptyInstances = empty_instances(cluster_arn, activeContainerDescribed)

    dataObj = { 
        'clusterName': cluster_name,
        'clusterMemReservation': clusterMemReservation,
        'activeContainerDescribed': activeContainerDescribed,
        'drainingInstances': drainingInstances,
        'emptyInstances': emptyInstances,
        'drainingContainerDescribed': drainingContainerDescribed        
    }

    return dataObj


def drain_instance(ecs_client, container_instance_id, cluster_name):
    ecs_client.update_container_instances_state(
        cluster=cluster_name,
        containerInstances=[container_instance_id],
        status="DRAINING",
    )


def terminate_instance(asg_client, ec2_instance_id):
    asg_client.terminate_instance_in_auto_scaling_group(
        InstanceId=ec2_instance_id,
        ShouldDecrementDesiredCapacity=True,
    )


def scale_up(cluster_data, cluster_def, asg_group_data):
    """
    Check if cluster should scale up.

    We scale out when there is less than `cpu_buffer` or less than `mem_buffer` 
    on all instances and when `desired_capacity` < `max_capacity`.
    """
    if asg_group_data["DesiredCapacity"] >= asg_group_data["MaxSize"]:
        return False
    should_scale = True
    for instance in cluster_data["activeContainerDescribed"]:
        # TODO
        # if cpu_avail >= cpu_buffer and mem_avil >= mem_buffer:
        #     should_scale = False
        #     break
        pass
    if should_scale:
        desired_capacity = asg_group_data["DesiredCapacity"] + 1
        asg_client.set_desired_capacity(
            AutoScalingGroupName=cluster_def["autoscale_group"],
            DesiredCapacity=desired_capacity,
        )
        return True
    return False


def scale_down(cluster_data, cluster_def, asg_group_data):
    """
    Check if cluster should scale down.

    We scale down when the current reserved memory and reserved CPU on the 
    instance with either the smallest amount of reserved mem or reserved CPU 
    can fit on another instance and when `desired_capacity` > `min_capacity`.
    """
    if asg_group_data["DesiredCapacity"] <= asg_group_data["MinSize"]:
        return False
    # TODO:
    return False


def scale_cluster(cluster_data, cluster_def, asg_group_data):
    """
    Scale a cluster up or down if requirements are met, otherwise do nothing.
    """
    if not cluster_def["enabled"]: 
        return False

    # Check if we should scale up.
    scaled = scale_up(cluster_data, cluster_def, asg_group_data)
    if scaled: return True

    # If we didn't scale up, check if we should scale down.
    scaled = scale_down(cluster_data, cluster_def, asg_group_data)
    return scaled



# Set up
ecs_client = boto3.client('ecs')
cw_client = boto3.client('cloudwatch')
asg_client = boto3.client('autoscaling')
asg_data = asg_client.describe_auto_scaling_groups()

cluster_defs = yaml.load(open("clusters.yml", "r"))
cluster_list = clusters(ecs_client)

# Flow
cluster_name = "development"
asg_group_name = cluster_defs["clusters"][cluster_name]["autoscale_group"]
cluster_arn = get_cluster_arn(cluster_name, cluster_list)
cluster_data = retrieve_cluster_data(ecs_client, cw_client, asg_client, cluster_arn, cluster_name)
asg_group_data = get_asg_group_data(asg_group_name, asg_data)
