# ecs-autoscale

Lambda function for autoscaling ECS clusters.

## Developing and deploying

For developing and deploying, make sure you have Python 3.5 or 3.6 and have installed the requirements
listed in `requirements.txt` (`pip3 install -r requirements.txt`). To test the function locally,

```bash
cd ./python-lambda/ && python3 lambda_function.py --test
```

> NOTE: The `--test` switch ensures that no actual scaling events will occur,
it's just a simulation.

In order to deploy, first run

```
make setup
```

This will

- Create a Python 3 virtualenv called `ecs-autoscale`.
- Install the requirements to that virtualenv.
- Create a symbolic link `python-lambda/packages` to the site-packages directory of that virtualenv.

Then you can deploy the with 

```
make deploy
```

## Details

The YAML files in `./python-lambda/clusters/` define which ECS clusters will be monitored.
A cluster definition will look like this:

```yaml
# Exact name of the autoscaling group.
autoscale_group: EC2ContainerService-development-EcsInstanceAsg-1F0M2UEJEY9OF

# Set to false to ignore this cluster when autoscaling.
enabled: true

# Buffer room: you can think of this as an empty service / task.
cpu_buffer: 0  # Size of buffer in CPU units.
mem_buffer: 0  # Size of buffer in memory.

# Defines scaling for individual services.
services:
  # This should be the exact name of the service as in the ECS cluster.
  worker:
    # Set to false to ignore service when autoscaling.
    enabled: true

    # Data sources needed for gathering metrics. Currently only `rabbitmq` and 
    # `cloudwatch` are supported.
    metric_sources:
      rabbitmq:
        url: %(RABBITMQ_DEV)/celery

    min: 1  # Min number of tasks.
    max: 3  # Max number of tasks.

    # Autoscaling events which determine when to scale up or down.
    events:
      - metric: messages_ready  # Name of metric to use.
        source: rabbitmq
        action: 1  # Scale up by one.
        # Conditions of the event:
        min: 5
        max: null
      - metric: messages_ready
        source: rabbitmq
        action: -1  # Scale down by one.
        min: null
        max: 3
```

> NOTE: We are using a similar syntax for expanding environment variables as used in `supervisor.conf` files, i.e.
something like `%(RABBITMQ_DEV)` will be expanding into the environment variable `RABBITMQ_DEV`.

### Scaling individual services

Individual services can be scaled up or down according to arbitrary metrics. For example,
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
