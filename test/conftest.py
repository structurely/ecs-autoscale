"""Defines test fixtures."""

import pytest

from ecsautoscale.services import Service


@pytest.fixture(scope="function")
def service():
    service = Service("test_cluster", None, None, 1)
    service.state = {
        "foo": 2,
        "bar": 3,
        "baz": 4,
    }
    return service
