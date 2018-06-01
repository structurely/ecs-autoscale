"""
Handles scaling individual services within a cluster.
"""

import logging
from typing import List

import ecsautoscale.metric_sources.third_party
import ecsautoscale.metric_sources.cloudwatch
from . import ecs_client, LOG_LEVEL


logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)


class Service:
    """
    An object for scaling arbitrary services.

    Parameters
    ----------
    cluster_name : str
        Name of the cluster on ECS.

    service_name : str
        The name of the service on ECS.

    task_name : str
        The name of the task on ECS.

    task_count : int
        The current number of tasks running.

    events : List[dict]
        A list of trigger events.

    metric_sources : dict
        The details of where to pull metrics from.

    min_tasks : int
        The desired minimum number of tasks.

    max_tasks : int
        The desired maximum number of tasks.

    state : dict
        The current state of metrics.

    """

    def __init__(self, cluster_name: str,
                 service_name: str,
                 task_name: str,
                 task_count: int,
                 events: List[dict] = None,
                 metric_sources: dict = None,
                 min_tasks: int = 0,
                 max_tasks: int = 5,
                 state: dict = None) -> None:
        self.cluster_name = cluster_name
        self.service_name = service_name
        self.task_count = task_count
        self.task_name = task_name
        self.min_tasks = min_tasks
        self.max_tasks = max_tasks
        self.events = events or []
        self.metric_sources = metric_sources or {}

        if task_name:
            task_definition_data = \
                ecs_client.describe_task_definition(taskDefinition=task_name)
            self.task_cpu = 0
            self.task_mem = 0
            containers = \
                task_definition_data["taskDefinition"]["containerDefinitions"]
            for container in containers:
                self.task_cpu += container["cpu"]
                self.task_mem += container["memory"]
        else:
            self.task_cpu = 0
            self.task_mem = 0

        # Get metric data.
        self.state = state or {}
        for source_name in self.metric_sources:
            source = getattr(ecsautoscale.metric_sources, source_name)
            for item in self.metric_sources[source_name]:
                res = source.get_data(**item)
                if res:
                    self.state.update(res)

        self.desired_tasks = 0
        self.task_diff = 0

        if self.service_name is not None:
            logger.info(
                "[Cluster: {:s}, Service: {:s}] Current state:\n"
                " => Running count:    {:d}\n"
                " => Minimum capacity: {:d}\n"
                " => Maximum capacity: {:d}"
                .format(
                    self.cluster_name,
                    self.service_name,
                    self.task_count,
                    self.min_tasks,
                    self.max_tasks,
                )
            )

    def _get_metric(self, metric_str: str) -> float:
        for metric_name in self.state:
            metric_str = metric_str.replace(metric_name,
                                            str(self.state[metric_name]))
        return eval(metric_str)

    def pretend_scale(self) -> bool:
        """
        Check trigger events in order to determine what needs to scale.
        """
        if self.task_count < self.min_tasks:
            self.task_diff = self.min_tasks - self.task_count
            self.desired_tasks = self.min_tasks
            return True

        if self.task_count > self.max_tasks:
            self.task_diff = self.task_count - self.max_tasks
            self.desired_tasks = self.max_tasks
            return True

        for event in self.events:
            metric_name = event["metric"]
            metric = self._get_metric(metric_name)
            if metric is None:
                return False

            if event["max"] is not None and metric > event["max"]:
                continue

            if event["min"] is not None and metric < event["min"]:
                continue

            desired_tasks = self.task_count + event["action"]
            if desired_tasks < self.min_tasks:
                if self.task_count == self.min_tasks:
                    continue
                desired_tasks = self.min_tasks

            elif desired_tasks > self.max_tasks:
                if self.task_count == self.max_tasks:
                    continue
                desired_tasks = self.max_tasks

            self.desired_tasks = desired_tasks
            self.task_diff = self.desired_tasks - self.task_count
            logger.info(
                "[Cluster: %s, Service: %s] Event satisfied:\n"
                " => Metric name:   %s\n"
                " => Current: %s\n"
                " => Min:     %s\n"
                " => Max:     %s\n"
                " => Action:  %s",
                self.cluster_name,
                self.service_name,
                metric_name,
                metric,
                event["min"],
                event["max"],
                event["action"],
            )
            return True

        return False

    def scale(self, is_test_run: bool = False) -> None:
        """
        Scale service.
        """
        if self.desired_tasks is not None and \
                self.task_diff != 0 and \
                self.service_name is not None:
            logger.info(
                "[Cluster: {:s}, Service: {:s}] Setting desired count to {:d}"
                .format(
                    self.cluster_name,
                    self.service_name,
                    self.desired_tasks,
                )
            )
            if not is_test_run:
                ecs_client.update_service(
                    cluster=self.cluster_name,
                    service=self.service_name,
                    desiredCount=self.desired_tasks,
                )


def get_services(cluster_name: str, cluster_def: dict) -> dict:
    out: dict = {}
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


def gather_services(cluster_name: str, cluster_def: dict) -> List[Service]:
    logger.info(
        "[Cluster: {:s}] Gathering services"
        .format(cluster_name)
    )

    services_data = get_services(cluster_name, cluster_def)
    services = []
    for service_name in services_data:
        logger.info(
            "[Cluster: {:s}] Found service {:s}"
            .format(cluster_name, service_name)
        )
        if not cluster_def["services"][service_name]["enabled"]:
            logger.info(
                "[Cluster: {:s}] Skipping service {:s} since not enabled"
                .format(cluster_name, service_name)
            )
            continue
        service = cluster_def["services"][service_name]
        task_name = services_data[service_name]["task_name"]
        task_count = services_data[service_name]["task_count"]
        service = Service(
            cluster_name, service_name, task_name, task_count,
            events=service["events"],
            metric_sources=service["metric_sources"],
            min_tasks=service["min"],
            max_tasks=service["max"]
        )
        should_scale = service.pretend_scale()
        if should_scale:
            services.append(service)

    return services
