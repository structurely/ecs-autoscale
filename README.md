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
make deploy
```

## Details

The file `./python-lambda/clusters.yml` determines which ECS clusters will be monitored.
This file is well documented with comments but if you have outstanding questions let me know.

> NOTE: We are using a similar syntax for expanding environment variables as used in `supervisor.conf` files, i.e.
something like `%(RABBITMQ_DEV)` will be expanding into the environment variable `RABBITMQ_DEV`.


### Scaling up the cluster

A cluster is triggered to scale up by one when the following two conditions are met:

- the desired capacity of the corresponding autoscaling group is less than the maximum capacity, and
- there is no EC2 instance in the autoscaling group with at least `cpu_buffer` CPU units and `mem_buffer` MB free.

### Scaling down the cluster

A cluster is triggered to scale down by one when the following two conditions are met:

- the desired capacity of the corresponding autoscaling group is greater than the minimum capacity, and
- all of the tasks on the EC2 instance in the cluster with either the smallest amount of reserved CPU units or memory could fit on another instance in the cluster with enough room left over for `cpu_buffer` CPU units and `mem_buffer` MB.

### Scaling individual services

Individual services can be scaled up or down according to arbitrary metrics. For example,
celery workers can be scaled according to the number of queued messages.


## TODO

- [ ] Get autoscaling group name automatically for a given cluster name.
  - Could do this by cross-referencing the EC2 instance ids in the autoscaling group with that in the cluster
