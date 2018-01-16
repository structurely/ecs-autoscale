# ecs-autoscale

Lambda function for autoscaling ECS clusters.

## Developing and deploying

For developing and deploying, make sure you have Python 3.5 or 3.6 and have installed the requirements
listed in `requirements.txt` (`pip3 install -r requirements.txt`). To test the function locally,

```bash
cd ./python-lambda/ && python3 lambda_function.py
```

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
make ecs-deploy
```

## Details

The file `./python-lambda/clusters.yml` determines which ECS clusters will be monitored.
That file will look something like this:

```yaml
clusters:
  # Cluster name.
  development:
    # Autoscaling group name.
    autoscale_group: EC2ContainerService-development-EcsInstanceAsg-1F0M2UEJEY9OF
    cpu_buffer: 256  # Minimum amount of free CPU required for this cluster.
    mem_buffer: 256  # Minimum amount of free memory required for this cluster.
    enabled: false   # Easy toggle monitoring.
    # NOTE: `cpu_buffer` and `mem_buffer` should be set to at least the maximum
    # reserved CPU and maximum reserved memory, respectively, out of all tasks
    # running on the cluster, so that any service will be able scale up when
    # `cpu_buffer` CPU units and `mem_buffer` MB are available.
  staging:
    autoscale_group: EC2ContainerService-staging-EcsInstanceAsg-FKQIRK1S4ZDU
    cpu_buffer: 512
    mem_buffer: 512
    enabled: true
  production:
    autoscale_group: EC2ContainerService-production-EcsInstanceAsg-1M41VS657IN2A
    cpu_buffer: 512
    mem_buffer: 512
    enabled: true
```

### Scaling up

A cluster is triggered to scale up by one when the following two conditions are met:

- the desired capacity of the corresponding autoscaling group is less than the maximum capacity, and
- there is no EC2 instance in the autoscaling group with at least `cpu_buffer` CPU units and `mem_buffer` MB free.

### Scaling down

A cluster is triggered to scale down by one when the following two conditions are met:

- the desired capacity of the corresponding autoscaling group is greater than the minimum capacity, and
- all of the tasks on the EC2 instance in the cluster with either the smallest amount of reserved CPU units or memory could fit on another instance in the cluster with enough room left over for `cpu_buffer` CPU units and `mem_buffer` MB.

## TODO

- [ ] Get autoscaling group name automatically for a given cluster name.
  - Could do this by cross-referencing the EC2 instance ids in the autoscaling group with that in the cluster
