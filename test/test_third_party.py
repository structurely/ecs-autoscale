import inspect
import os
import sys

base_path = os.path.dirname(os.path.abspath(inspect.stack()[0][1]))
sys.path.append(os.path.join(base_path, "../python-lambda/"))

from autoscaling.metric_sources import third_party


def test_nested_get():
    data = {
        "foo": 2,
        "bar": {
            "baz": 3
        }
    }
    assert third_party._get_nested_field(data, "foo") == 2
    assert third_party._get_nested_field(data, "bar.baz") == 3
