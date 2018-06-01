"""Defines custom errors."""


class Error(Exception):
    """Base error."""
    pass


class ClusterARNError(Error):
    """Error raised when we could not match a cluster name with an ARN."""

    def __init__(self, cluster_name):
        self.cluster_name = cluster_name
        message = f"Could not find cluster ARN for cluster {cluster_name}"
        super(ClusterARNError, self).__init__(message)


class ASGGroupError(Error):
    """Error raised when we could not match a cluster name with an ARN."""

    def __init__(self, asg_group_name):
        self.asg_group_name = asg_group_name
        message = f"Could not find autoscaling group {asg_group_name}"
        super(ASGGroupError, self).__init__(message)


class MissingResourceValueError(Error):
    """Error raised when CPU or memory for an instance cannot be found."""

    def __init__(self, resource):
        self.resource = resource
        message = f"Could not find {resource}"
        super(MissingResourceValueError, self).__init__(message)


class CloudWatchError(Error):
    """Error raised when retreiving CloudWatch statistics fails."""

    def __init__(self, namespace, metric_name, dimensions, period, statistics):
        self.namespace = namespace
        self.metric_name = metric_name
        self.dimensions = dimensions
        self.period = period
        self.statistics = statistics
        message = \
            "Error retreiving CloudWatch statistics, no datapoints found:\n"\
            " => Namespace:  {:s}\n"\
            " => MetricName: {:s}\n"\
            " => Dimensions: {}\n"\
            " => Period:     {}\n"\
            " => Statistics: {}"\
            .format(namespace, metric_name, dimensions, period, statistics)
        super(CloudWatchError, self).__init__(message)


class ThirdPartyError(Error):
    """Error raised when retreiving third party statistics."""

    def __init__(self, status_code, url):
        self.status_code = status_code
        self.url = url
        message = \
            "Error retreiving metrics:\n"\
            " => Status code: {:d}\n"\
            " => URL: {:s}\n"\
            .format(status_code, url)
        super(ThirdPartyError, self).__init__(message)
