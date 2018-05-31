"""Test the ecsautoscale.services.Service class."""

from typing import List

import pytest

from ecsautoscale.services import Service


def test_metric_arithmetic1(service):
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
    assert service._get_metric("min([foo, bar])") == 2
    assert service._get_metric("max([foo, bar])") == 3


cases = [
    (
        [{
            "metric": "foo",
            "action": 1,
            "min": 1,
            "max": None,
        }],
        None, 2, 1
    ),
    (
        [{
            "metric": "foo",
            "action": 2,
            "min": 1,
            "max": None,
        }],
        None, 3, 2
    ),
    (
        [{
            "metric": "foo",
            "action": 3,
            "min": 1,
            "max": None,
        }],
        3, 3, 2
    )
]


@pytest.mark.parametrize(
    "events, max_tasks, desired_tasks_check, task_diff_check", cases)
def test_pretend_scale(service: Service,
                       events: List[dict],
                       max_tasks: int,
                       desired_tasks_check: int,
                       task_diff_check: int) -> None:
    if max_tasks is not None:
        service.max_tasks = max_tasks
    service.events = events
    service.pretend_scale()
    assert service.desired_tasks == desired_tasks_check
    assert service.task_diff == task_diff_check
