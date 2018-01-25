"""
Handles scaling individual services within a cluster.
"""

import logging

import requests

from . import ecs_client, LOG_LEVEL
import autoscaling.metric_sources.rabbitmq
import autoscaling.metric_sources.cloudwatch


logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)


class Service(object):
    """
    An object for scaling arbitrary services.
    """

    def __init__(self, cluster_name, service_name, task_name, task_count,
                 events=[],
                 metric_sources={},
                 min_tasks=0,
                 max_tasks=5,
                 state={}):
        self.cluster_name = cluster_name
        self.service_name = service_name
        self.task_count = task_count
        self.task_name = task_name
        self.min_tasks = min_tasks
        self.max_tasks = max_tasks
        self.events = events
        self.metric_sources = metric_sources

        if task_name:
            task_definition_data = \
                ecs_client.describe_task_definition(taskDefinition=task_name)
            self.task_cpu = 0
            self.task_mem = 0
            for container in task_definition_data["taskDefinition"]["containerDefinitions"]:
                self.task_cpu += container["cpu"]
                self.task_mem += container["memory"]
        else:
            self.task_cpu = 0
            self.task_mem = 0

        # Get metric data.
        self.state = state
        for source_name in self.metric_sources:
            source = getattr(autoscaling.metric_sources, source_name)
            for item in self.metric_sources[source_name]:
                res = source.get_data(**item)
                if res:
                    self.state.update(res)

        self.desired_tasks = None
        self.task_diff = None

        if self.service_name is not None:
            logger.info(
                "[Cluster: {}, Service: {}] Current state:\n"\
                " => Running count:    {}\n"\
                " => Minimum capacity: {}\n"\
                " => Maximum capacity: {}"\
                .format(
                    self.cluster_name,
                    self.service_name,
                    self.task_count,
                    self.min_tasks,
                    self.max_tasks,
                )
            )

    def pretend_scale(self):
        if self.task_count < self.min_tasks:
            self.task_diff = self.min_tasks - self.task_count
            self.desired_tasks = self.min_tasks
            return True

        if self.task_count > self.max_tasks:
            self.task_diff = self.task_count - self.max_tasks
            self.desired_tasks = self.max_tasks
            return True

        for event in self.events:
            metric = self.state[event["metric"]]
            if metric is None:
                return False

            if event["max"] is not None and metric > event["max"]:
                continue

            if event["min"] is not None and metric < event["min"]:
                continue

            desired_tasks = self.task_count + event["action"]
            if desired_tasks < self.min_tasks:
                pass
            elif desired_tasks > self.max_tasks:
                pass
            else:
                self.desired_tasks = desired_tasks
                self.task_diff = self.desired_tasks - self.task_count
                logger.info(
                    "[Cluster: {}, Service: {}] Event satisfied:\n"\
                    " => Metric name:   {}\n"\
                    " => Current: {}\n"\
                    " => Min:     {}\n"\
                    " => Max:     {}\n"\
                    " => Action:  {}"\
                    .format(
                        self.cluster_name,
                        self.service_name,
                        event["metric"],
                        metric,
                        event["min"],
                        event["max"],
                        event["action"],
                    )
                )
                return True

        return False

    def scale(self, is_test_run=False):
        if self.desired_tasks is not None and \
                self.task_diff != 0 and \
                self.service_name is not None:
            logger.info(
                "[Cluster: {}, Service: {}] Setting desired count to {}"\
                .format(
                    self.cluster_name,
                    self.service_name,
                    self.desired_tasks,
                )
            )
            if not is_test_run:
                response = ecs_client.update_service(
                    cluster=self.cluster_name,
                    service=self.service_name,
                    desiredCount=self.desired_tasks,
                )


def get_services(cluster_name, cluster_def):
    out = {}
    service_names = cluster_def["services"].keys()
    if not service_names:
        return out
    res = ecs_client.describe_services(
        cluster=cluster_name,
        services=list(cluster_def["services"].keys())
    )
    for item in res["services"]:
        name = item["serviceName"]
        out[name] = {
            "task_count": item["runningCount"],
            "task_name": item["taskDefinition"],
        }
    return out


def gather_services(cluster_name, cluster_def):
    logger.info(
        "[Cluster: {}] Gathering services"\
        .format(cluster_name)
    )

    services_data = get_services(cluster_name, cluster_def)
    services = []
    for service_name in services_data:
        logger.info(
            "[Cluster: {}] Found service {}"\
            .format(cluster_name, service_name)
        )
        if not cluster_def["services"][service_name]["enabled"]:
            logger.info(
                "[Cluster: {}] Skipping service {} since not enabled"\
                .format(cluster_name, service_name)
            )
            continue
        task_name = services_data[service_name]["task_name"]
        task_count = services_data[service_name]["task_count"]
        service = Service(cluster_name, service_name, task_name, task_count,
                          events=cluster_def["services"][service_name]["events"],
                          metric_sources=cluster_def["services"][service_name]["metric_sources"],
                          min_tasks=cluster_def["services"][service_name]["min"],
                          max_tasks=cluster_def["services"][service_name]["max"])
        should_scale = service.pretend_scale()
        if should_scale:
            services.append(service)

    return services
