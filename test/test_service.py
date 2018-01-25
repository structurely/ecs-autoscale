import inspect
import os
import sys

base_path = os.path.dirname(os.path.abspath(inspect.stack()[0][1]))
sys.path.append(os.path.join(base_path, "../python-lambda/"))

from autoscaling.services import Service


def init_service():
    return Service("test_cluster", None, None, 1)


def test_metric_arithmetic1():
    service = init_service()
    service.state = {
        "foo": 2,
        "bar": 3,
        "baz": 4,
    }
    assert service._get_metric("foo * bar * baz") == 24
    assert service._get_metric("foo") == 2
    assert service._get_metric(" foo") == 2
    assert service._get_metric("foo ") == 2
    assert service._get_metric("foo * bar / baz") == 1.5
    assert service._get_metric("foo * bar/baz") == 1.5
    assert service._get_metric("foo*bar/baz") == 1.5
    assert service._get_metric("foo*bar/ baz") == 1.5
    assert service._get_metric("foo *bar/ baz") == 1.5
    assert service._get_metric("foo * 100") == 200
    assert service._get_metric("foo - 1 + 2") == 3
    assert service._get_metric("(foo - 1) * 10") == 10
    assert service._get_metric("foo * foo") == 4
    assert service._get_metric("foo ** 2") == 4
