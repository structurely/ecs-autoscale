"""Metrics from CloudWatch."""

from datetime import datetime, timedelta
import logging
from typing import List

from ecsautoscale import cdw_client
from ecsautoscale.exceptions import CloudWatchError


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _format_dimensions(dimensions: List[dict]) -> List[dict]:
    out = []
    for item in dimensions:
        out.append({
            "Name": item["name"],
            "Value": item["value"],
        })
    return out


def get_data(metric_name: str = "MemoryUtilization",
             dimensions: List[dict] = None,
             statistics: List[dict] = None,
             namespace: str = "AWS/ECS",
             period: int = 300,
             defaultValue: int = None) -> dict:
    """
    Retreive metrics from AWS CloudWatch.

    Parameters
    ----------
    metric_name : str
        The name of the metric.

    dimensions : List[dict]
        AWS metric dimension names.

    statistics : List[dict]
        AWS metric statistic names.

    namespace : str
        AWS metric namespace name.

    period : int
        AWS metric period.

    Returns
    -------
    dict
        The desired metrics.

    """
    statistics = statistics or []
    dimensions = dimensions or []

    out = {x["alias"]: None for x in statistics}

    dimensions_ = _format_dimensions(dimensions)
    statistics_ = [x["name"] for x in statistics]
    now = datetime.now()
    res = cdw_client.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=dimensions_,
        StartTime=now - timedelta(seconds=period),
        EndTime=now,
        Period=period,
        Statistics=statistics_,
    )
    datapoints = res["Datapoints"]
    if not datapoints:
        if defaultValue:
            datapoints.append({statistics_[0] : defaultValue})
        else:
            raise CloudWatchError(
                namespace, metric_name, dimensions_, period, statistics_)

    log_messages = ["Retreived the following statistics from CloudWatch:"]
    for stat in statistics:
        key = stat["alias"]
        val = datapoints[0].get(stat["name"])
        out[key] = val
        log_messages.append(" => {}: {}".format(key, val))

    if out:
        logger.debug("\n".join(log_messages))

    return out
