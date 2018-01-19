"""
Handles scaling individual services within a cluster.
"""

import logging

import requests

from . import ecs_client


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


HANDLED_SERVICE_TYPES = ["celery"]


def get_celery_data(url):
    r = requests.get(url)
    return r.json()


class Service(object):
    """
    An object for scaling arbitrary services.
    """

    def __init__(self, cluster_name, service_name, task_name, task_count,
                 events=[],
                 data={},
                 min_tasks=0,
                 max_tasks=5,
                 service_type="celery"):
        assert service_type in HANDLED_SERVICE_TYPES

        self.cluster_name = cluster_name
        self.service_name = service_name
        self.task_count = task_count
        self.task_name = task_name
        self.min_tasks = min_tasks
        self.max_tasks = max_tasks
        self.service_type = service_type
        self.events = events
        self.data = data

        task_definition_data = \
            ecs_client.describe_task_definition(taskDefinition=task_name)
        self.task_cpu = 0
        self.task_mem = 0
        for container in task_definition_data["taskDefinition"]["containerDefinitions"]:
            self.task_cpu += container["cpu"]
            self.task_mem += container["memory"]

        if self.service_type == "celery":
            self.state = get_celery_data(self.data["url"])

        self.desired_tasks = None
        self.cpu_increase = None
        self.mem_increase = None

    def pretend_scale(self):
        if self.task_count < self.min_tasks:
            diff = self.min_tasks - self.task_count
            self.desired_tasks = self.min_tasks
            self.cpu_increase = self.task_cpu * diff
            self.mem_increase = self.task_mem * diff
            return True
        if self.task_count > self.max_tasks:
            diff = self.task_count - self.max_tasks
            self.desired_tasks = self.max_tasks
            self.cpu_increase = self.task_cpu * diff
            self.mem_increase = self.task_mem * diff
            return True
        for event in self.events:
            metric = self.state[event["metric"]]
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
                self.cpu_increase = self.task_cpu * event["action"]
                self.mem_increase = self.task_mem * event["action"]
                return True
        return False

    def scale(self):
        if self.desired_tasks is not None and \
                self.desired_tasks != self.task_count:
            logger.info(
                "[Cluster: {}] Setting desired count to {} for {} service"\
                .format(self.cluster_name, self.desired_tasks, self.service_name)
            )
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
                          data=cluster_def["services"][service_name]["data"],
                          service_type=cluster_def["services"][service_name]["type"],
                          min_tasks=cluster_def["services"][service_name]["min"],
                          max_tasks=cluster_def["services"][service_name]["max"])
        should_scale = service.pretend_scale()
        if should_scale:
            services.append(service)
    return services
