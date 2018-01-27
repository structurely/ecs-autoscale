import logging

import requests


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _get_nested_field(data, field):
    d = data
    levels = field.split(".")
    for l in levels:
        d = d[l]
    return d


def get_data(url=None, statistics=[], method="GET", payload=None):
    assert method in ["GET", "POST"]
    out = {x["alias"]: None for x in statistics}
    method = getattr(requests, method.lower())
    r = method(url, json=payload)
    if r.status_code != 200:
        logger.error(
            "Error retreiving RabbitMQ statistics:\n"\
            " => Status code: {}\n"\
            " => URL: {}\n"\
            .format(r.status_code, url)
        )
    else:
        data = r.json()
        log_messages = ["Retreived the following statistics from RabbitMQ:"]
        for x in statistics:
            key = x["alias"]
            val = _get_nested_field(data, x["name"])
            out[key] = val
            log_messages.append(" => {}: {}".format(key, val))
        if out:
            logger.debug("\n".join(log_messages))
    return out
