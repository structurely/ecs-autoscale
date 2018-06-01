"""Interface to metric from third-party sources."""

from typing import List
import logging

import requests

from ecsautoscale.exceptions import ThirdPartyError


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _get_nested_field(data: dict, field: str):
    subdata = data
    levels = field.split(".")
    for level in levels:
        subdata = subdata[level]
    return subdata


def get_data(url: str = None,
             statistics: List[dict] = None,
             method: str = "GET",
             payload: dict = None) -> dict:
    """
    Retreive metrics from a URL with an HTTP POST or GET request.

    Parameters
    ----------
    url : str
        The URL of the resource.

    statistics : List[dict]
        A list of metric names to grab.

    method : str
        The HTTP method.

    payload : dict
        An arbitrary payload to include in the request.

    Returns
    -------
    dict
        The desired metrics.

    """
    # pylint: disable=not-callable
    assert method in ["GET", "POST"]

    statistics = statistics or []

    out = {x["alias"]: None for x in statistics}

    method_ = getattr(requests, method.lower())
    resp = method_(url, json=payload)
    if resp.status_code != 200:
        raise ThirdPartyError(resp.status_code, url)

    data = resp.json()
    log_messages = ["Retreived the following metrics:"]
    for stat in statistics:
        key = stat["alias"]
        val = _get_nested_field(data, stat["name"])
        out[key] = val
        log_messages.append(" => {}: {}".format(key, val))
    if out:
        logger.debug("\n".join(log_messages))

    return out
