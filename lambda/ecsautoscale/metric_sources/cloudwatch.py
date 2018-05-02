from datetime import datetime, timedelta
import logging

from ecsautoscale import cdw_client


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _format_dimensions(dimensions):
    out = []
    for item in dimensions:
        out.append({
            "Name": item["name"],
            "Value": item["value"],
        })
    return out


def get_data(metric_name="MemoryUtilization", dimensions=None,
             statistics=None, namespace="AWS/ECS", period=300):
    """
    Retreive metrics from AWS CloudWatch.

    Args:
        metric_name (str): the name of the metric.
        dimensions (list of str): AWS metric dimension names.
        statistics (list of str): AWS metric statistic names.
        namespace (str): AWS metric namespace name.
        period (int): AWS metric period.

    Returns:
        dict: the desired metrics.
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
        logger.error(
            "Error retreiving CloudWatch statistics, no datapoints found:\n"
            " => Namespace:  {}\n"
            " => MetricName: {}\n"
            " => Dimensions: {}\n"
            " => Period:     {}\n"
            " => Statistics: {}"
            .format(
                namespace, metric_name, dimensions_, period, statistics_,
            )
        )
    else:
        log_messages = ["Retreived the following statistics from CloudWatch:"]
        for x in statistics:
            key = x["alias"]
            val = datapoints[0].get(x["name"])
            out[key] = val
            log_messages.append(" => {}: {}".format(key, val))
        if out:
            logger.debug("\n".join(log_messages))

    return out
