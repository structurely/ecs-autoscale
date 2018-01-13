.PHONY: build
build:
	@cd python-lambda && \
			zip -r ../deployment.zip *

.PHONY: push
push:
	aws lambda update-function-code \
			--function-name "ecs-autoscale" \
			--zip-file fileb://./deployment.zip

.PHONY: deploy
deploy: build push
