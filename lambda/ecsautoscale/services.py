"""
Handles scaling individual services within a cluster.
"""

import logging

from . import ecs_client, LOG_LEVEL
import ecsautoscale.metric_sources.third_party
import ecsautoscale.metric_sources.cloudwatch


logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)


class Service:
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
            containers = \
                task_definition_data["taskDefinition"]["containerDefinitions"]
            for container in containers:
                self.task_cpu += container["cpu"]
                self.task_mem += container["memory"]
        else:
            self.task_cpu = 0
            self.task_mem = 0

        # Get metric data.
        self.state = state
        for source_name in self.metric_sources:
            source = getattr(ecsautoscale.metric_sources, source_name)
            for item in self.metric_sources[source_name]:
                res = source.get_data(**item)
                if res:
                    self.state.update(res)

        self.desired_tasks = None
        self.task_diff = None

        if self.service_name is not None:
            logger.info(
                "[Cluster: {}, Service: {}] Current state:\n"
                " => Running count:    {}\n"
                " => Minimum capacity: {}\n"
                " => Maximum capacity: {}"
                .format(
                    self.cluster_name,
                    self.service_name,
                    self.task_count,
                    self.min_tasks,
                    self.max_tasks,
                )
            )

    def _get_metric(self, metric_str):
        for metric_name in self.state:
            metric_str = metric_str.replace(metric_name,
                                            str(self.state[metric_name]))
        return eval(metric_str)

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
                "[Cluster: {}, Service: {}] Event satisfied:\n"
                " => Metric name:   {}\n"
                " => Current: {}\n"
                " => Min:     {}\n"
                " => Max:     {}\n"
                " => Action:  {}"
                .format(
                    self.cluster_name,
                    self.service_name,
                    metric_name,
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
                "[Cluster: {}, Service: {}] Setting desired count to {}"
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
        "[Cluster: {}] Gathering services"
        .format(cluster_name)
    )

    services_data = get_services(cluster_name, cluster_def)
    services = []
    for service_name in services_data:
        logger.info(
            "[Cluster: {}] Found service {}"
            .format(cluster_name, service_name)
        )
        if not cluster_def["services"][service_name]["enabled"]:
            logger.info(
                "[Cluster: {}] Skipping service {} since not enabled"
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
