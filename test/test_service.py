from ecsautoscale.services import Service


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
    assert service._get_metric("min([foo, bar])") == 2
    assert service._get_metric("max([foo, bar])") == 3


def test_pretend_scale1():
    service = init_service()
    service.state = {
        "foo": 2,
        "bar": 3,
        "baz": 4,
    }
    service.events = [
        {
            "metric": "foo",
            "action": 1,
            "min": 1,
            "max": None,
        }
    ]
    service.pretend_scale()
    assert service.desired_tasks == 2
    assert service.task_diff == 1


def test_pretend_scale2():
    service = init_service()
    service.state = {
        "foo": 2,
        "bar": 3,
        "baz": 4,
    }
    service.events = [
        {
            "metric": "foo",
            "action": 2,
            "min": 1,
            "max": None,
        }
    ]
    service.pretend_scale()
    assert service.desired_tasks == 3
    assert service.task_diff == 2


def test_pretend_scale3():
    service = init_service()
    service.state = {
        "foo": 2,
        "bar": 3,
        "baz": 4,
    }
    service.max_tasks = 3
    service.events = [
        {
            "metric": "foo",
            "action": 3,
            "min": 1,
            "max": None,
        }
    ]
    service.pretend_scale()
    assert service.desired_tasks == 3
    assert service.task_diff == 2
