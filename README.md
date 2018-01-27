<p align="center">
  <img src="https://github.com/structurely/ecs-autoscale/blob/master/.figures/logo.png"/>
</p>

# ecs-autoscale

This is a Lambda function that allows you to automatically
scale EC2 instances and services within an ECS cluster simultaneously based on 
arbitrary metrics from sources not limited to CloudWatch.

## Table of contents

- [Requirements](https://github.com/structurely/ecs-autoscale#requirements)
- [Quick start](https://github.com/structurely/ecs-autoscale#quick-start)
- [Scaling details](https://github.com/structurely/ecs-autoscale#scaling-details)
- [Metrics](https://github.com/structurely/ecs-autoscale#metrics)
  - [Sources](https://github.com/structurely/ecs-autoscale#sources)
  - [Metric arithmetic](https://github.com/structurely/ecs-autoscale#metric-arithmetic)
- [Logging](https://github.com/structurely/ecs-autoscale#logging)

## Requirements

Make sure you have Python 3.5 or 3.6 and have installed the requirements
listed in `requirements.txt` (`pip3 install -r requirements.txt`). 
Currently this has only been testing on OS X and Linux. Windows is not supported.

## Quick start

Suppose we want to set up autoscaling for a cluster on ECS called `my_cluster`
with two services running: `backend` and `worker`. Suppose `backend` is just a simple
web server and `worker` is a [celery](http://www.celeryproject.org) worker 
for handling long-running tasks for the web server with a RabbitMQ instance as the broker.

In this case we want to scale the web server based on CPU utilization and scale the
celery worker based on the number of waiting tasks (which is given by the number of `ready` 
messages on the RabbitMQ instance).

We can get the CPU utilization of the web server directly from CloudWatch,
but in order to get the number of queued messages in the RabbitMQ instance,
we will need to make an HTTP GET request to the api of the queue.

> To learn more about the RabbitMQ API, see [https://cdn.rawgit.com/rabbitmq/rabbitmq-management/v3.7.2/priv/www/api/index.html](https://cdn.rawgit.com/rabbitmq/rabbitmq-management/v3.7.2/priv/www/api/index.html).

**Step 1: Define the cluster scaling requirements**

We create a YAML file `./python-lambda/clusters/my_cluster.yml`.

> NOTE: The name of the YAML file sans extension must exactly match the name of the cluster on ECS.

Our cluster definition will look like this:

```yaml
# Exact name of the autoscaling group.
autoscale_group: EC2ContainerService-my_cluster-EcsInstanceAsg-AAAAA

# Set to false to ignore this cluster when autoscaling.
enabled: true

# Buffer room: you can think of this as an empty service / task.
cpu_buffer: 0  # Size of buffer in CPU units.
mem_buffer: 0  # Size of buffer in memory.

# Optionally specify the minimum and maximum number of instances for the cluster's
# autoscaling group from here.
min: 1
max: 4

# Defines scaling for individual services.
services:
  # This should be the exact name of the service as in the ECS cluster.
  worker:
    # Set to false to ignore service when autoscaling.
    enabled: true

    min: 1  # Min number of tasks.
    max: 3  # Max number of tasks.

    metric_sources:
      # Data sources needed for gathering metrics. Currently only `third_party` and 
      # `cloudwatch` are supported. Only one statistic from one source is needed.
      # For more information on the metrics available, see below under "Metrics".
      third_party:
        - url: https://username:password@my_rabbitmq_host.com/api/queues/celery
          method: GET  # Either GET or POST
          payload: null  # Optional JSON paylaod to include with the request
          statistics:
            - name: messages_ready
              alias: queue_length
          # In this case it is assumed that we will make a GET request to the url
          # given, and that request will return a JSON object that contains
          # the field `messages_ready`.

    # Autoscaling events which determine when to scale up or down.
    events:
      - metric: queue_length  # Name of metric to use.
        action: 1  # Scale up by one.
        # Conditions of the event:
        min: 5
        max: null
      - metric: queue_length
        action: -1  # Scale down by one.
        min: null
        max: 3

  backend:
    enabled: true
    min: 1
    max: 3
    metric_sources:
      cloudwatch:
        - namespace: AWS/ECS
          metric_name: CPUUtilization
          dimensions:
            - name: ClusterName
              value: my_cluster
            - name: ServiceName
              value: backend
          period: 300
          statistics:
            - name: Average
              alias: cpu_usage

    events:
      - metric: cpu_usage
        action: 1  # Scale up by 1
        min: 10
        max: null
      - metric: cpu_usage
        action: -1  # Scale down by 1
        min: null
        max: 1
```

> NOTE: You may not want to store sensitive information in your cluster definition,
such as the username and password in the RabbitMQ URL above. In this case you could store
those values in environment variables and pass them to the cluster definition
using our special syntax: `%(VARIABLE_NAME)`. So, for example, suppose
we have the environment variables `USERNAME` and `PASSWORD`. Then the line above
with the url for RabbitMQ would become `url: https://%(USERNAME):%(PASSWORD)@my_rabbitmq_host.com/api/queues/celery`.


**Step 2: Test the function locally**

To test the function locally,

```bash
cd ./python-lambda/ && python3 lambda_function.py --test
```

> NOTE: The `--test` switch ensures that no actual scaling events will occur,
it's just a simulation.


**Step 3: Setup and deployment**

Run the script `./bootstrap.sh`. This will

- Create a Python 3 virtualenv called `ecs-autoscale`.
- Install the requirements to that virtualenv.
- Create a symbolic link `python-lambda/packages` to the site-packages directory of that virtualenv.
- Create an IAM policy that gives access to the resources the lambda function will need.
- Create a role for the Lambda function to use, an attach the policy just created to that role.
- Build a deployment package.
- Create a Lambda function with the role attached and upload the deployment package.


**Step 4: Create a trigger to execute your function**

In this example we will create a simple CloudWatch that triggers our Lambda function to run
every 5 minutes.

To do this, first login to the AWS Console and the go to the CloudWatch service. On the left side menu,
click on "Rules". You should see a page that looks like this:

![step1](https://github.com/structurely/ecs-autoscale/blob/master/.figures/step1.png)

Then click "Create rule" by the top. You should now see a page that looks like this:

![step2](https://github.com/structurely/ecs-autoscale/blob/master/.figures/step2.png)

Make sure you check "Schedule" instead of "Event Pattern", and then set it to a fixed
rate of 5 minutes. Then on the right side click "Add target" and choose "ecs-autoscale"
from the drop down.

Next click "Configure details", give your rule a name, and then click "Create rule".

You're all set! After 5 minutes your function should run.


## Scaling details

### Scaling individual services

Individual services can be scaled up or down according to arbitrary metrics, as
long as those metrics can be gathered through a simple HTTP request. For example,
celery workers can be scaled according to the number of queued messages.

### Scaling up the cluster

A cluster is triggered to scale up by one instance when both of the following two conditions are met:

- the desired capacity of the corresponding autoscaling group is less than the maximum capacity, and
- the additional tasks for services that need to scale up cannot fit on the existing 
instances with room left over for the predefined CPU and memory buffers.

### Scaling down the cluster

A cluster is triggered to scale down by one instance when both of the following two conditions are met:

- the desired capacity of the corresponding autoscaling group is greater than the minimum capacity, and
- all of the tasks on the EC2 instance in the cluster with either the smallest amount of 
reserved CPU units or memory could fit entirely on another instance in the cluster, and 
so that the other instances could still support all additional tasks for services that need
to scale up with room left over for the predefined CPU and memory buffers.

## Metrics

### Sources

In order to use a metric, you need to define the source of the metric under
`metric_sources` in the YAML definition. In the example above, we defined a third party
metric like this:

```yaml
third_party:
  - url: https://username:password@my_rabbitmq_host.com/api/queues/celery
    method: GET
    payload: null
    statistics:
      - name: messages_ready
        alias: queue_length
```

This created a metric called `queue_length` based on `messages_ready`.
The alias `queue_length` was arbitrary, and is the name used to reference this
metric when defining events like in the above example:

```yaml
events:
  - metric: queue_length
    action: 1
    min: 5
    max: null
  - metric: queue_length
    action: -1
    min: null
    max: 3
```

In general, third party metrics are gathered by making an HTTP request to the
url given. It is then assumed that the request will return a JSON object with
a field name corresponding to the `name` of the metric. To retreive a nested field
in the JSON object, you can use dot notation.

Defining metrics from CloudWatch are pretty straight forward as well, like in our example:

```yaml
metric_sources:
  cloudwatch:
    - namespace: AWS/ECS
      metric_name: CPUUtilization
      dimensions:
        - name: ClusterName
          value: my_cluster
        - name: ServiceName
          value: backend
      period: 300
      statistics:
        - name: Average
          alias: cpu_usage
```

One thing to watch out for is how you define the `statistics` field above.
The `name` part has to match exactly with a statistic used by CloudWatch,
and the `alias` part is an arbitrary name you use to reference this metric when
defining events.


### Metric arithmetic

You can easily combine metrics with arbitrary arithmetic operations.
For example, suppose we create two metrics with aliases `cpu_usage` and `mem_usage`.
We could create an event based on the product of these two metrics like this:

```yaml
events:
  - metric: cpu_usage * mem_usage * 100
    action: 1
    min: 50
    max: 100
```

You could even go crazy for no reason:

```yaml
events:
  - metric: cpu_usage ** 2 - (mem_usage - 2000 + 1) * mem_usage + mem_usage * 0
    action: 1
    min: 50
    max: 100
```

In fact, metric arithmetic is interpreted directly as a Python statement, so you can even 
use functions like `min` and `max`:

```yaml
events:
  - metric: max([cpu_usage, mem_usage])
    action: 1
    min: 0.5
    max: 1.0
```

## Logging

Logs from the Lambda function will be sent to a CloudWatch logstream `/aws/lambda/ecs-autoscale`.
You can also set the log level easily by setting the environment variable `LOG_LEVEL`, which can
be set to

- `debug`
- `info`
- `warning`
- `error`

## Bugs

To report a bug, submit an issue at [https://github.com/structurely/ecs-autoscale/issues/new](https://github.com/structurely/ecs-autoscale/issues/new).


## Credit where credit is due

This project was inspired by the following articles and projects:

- [http://garbe.io/blog/2017/04/12/a-better-solution-to-ecs-autoscaling/](http://garbe.io/blog/2017/04/12/a-better-solution-to-ecs-autoscaling/)
- [https://medium.com/@omerxx/how-to-scale-in-ecs-hosts-2d0906d2ba](https://medium.com/@omerxx/how-to-scale-in-ecs-hosts-2d0906d2ba)
- [https://github.com/omerxx/ecscale/blob/master/ecscale.py](https://github.com/omerxx/ecscale/blob/master/ecscale.py)
