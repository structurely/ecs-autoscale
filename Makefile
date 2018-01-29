.PHONY: build
build:
	find . | grep -E "(__pycache__|\.pyc|\.pyo$$)" | xargs rm -rf
	@cd python-lambda && \
			zip -r ../deployment.zip *

.PHONY: push
push:
	aws lambda update-function-code \
			--function-name "ecs-autoscale" \
			--zip-file fileb://./deployment.zip

.PHONY: deploy
deploy: build push

.PHONY: test
test:
	flake8 \
			./python-lambda/lambda_function.py \
			./python-lambda/autoscaling/cluster_definitions.py \
			./python-lambda/autoscaling/ec2_instances.py \
			./python-lambda/autoscaling/services.py \
			./python-lambda/autoscaling/metric_sources/cloudwatch.py \
			./python-lambda/autoscaling/metric_sources/third_party.py
	pytest
