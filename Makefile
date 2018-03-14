test=test/

.PHONY: clean
clean:
	@echo "Removing compiled Python objects"
	@find . | grep -E "(__pycache__|\.pyc|\.pyo$$)" | xargs rm -rf

.PHONY: build
build:
	@cd lambda && zip -r ../deployment.zip *

.PHONY: push
push:
	aws lambda update-function-code \
			--function-name "ecs-autoscale" \
			--zip-file fileb://./deployment.zip

.PHONY: deploy
deploy: clean build push

.PHONY: flake
flake:
	@echo "Running flake8"
	@flake8 ./lambda/lambda_function.py ./lambda/autoscaling/

.PHONY: run-test
run-test:
	@echo "Running pytest on $(test)"
	@export PYTHONPATH=./lambda && pytest $(test)

.PHONY: test
test: clean flake run-test
