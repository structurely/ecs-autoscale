# ecs-autoscale

Lambda function for autoscaling ECS clusters.

In order to deploy, first create a Python 3 virtualenv called `ecs-autoscale` and then run
`make setup`. This will install the requirements to that virtualenv and create a symbolic link
`python-lambda/packages` to the site-packages directory.
Then you can deploy the with `make ecs-deploy`.
