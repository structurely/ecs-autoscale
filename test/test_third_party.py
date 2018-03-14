from ecsautoscale.metric_sources import third_party


def test_nested_get():
    data = {
        "foo": 2,
        "bar": {
            "baz": 3
        }
    }
    assert third_party._get_nested_field(data, "foo") == 2
    assert third_party._get_nested_field(data, "bar.baz") == 3
