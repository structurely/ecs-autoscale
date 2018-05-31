"""Defines custom errors."""


class Error(Exception):
    """Base error."""
    pass


class ClusterARNError(Error):
    """Error raised when we could not match a cluster name with an ARN."""

    def __init__(self, cluster_name):
        message = f"Could not find cluster ARN for cluster {cluster_name}"
        super(ClusterARNError, self).__init__(message)


class ASGGroupError(Error):
    """Error raised when we could not match a cluster name with an ARN."""

    def __init__(self, asg_group_name):
        message = f"Could not find autoscaling group {asg_group_name}"
        super(ASGGroupError, self).__init__(message)


class MissingResourceValueError(Error):
    """Error raised when CPU or memory for an instance cannot be found."""

    def __init__(self, resource):
        message = f"Could not find {resource}"
        super(MissingResourceValueError, self).__init__(message)
