.PHONY: setup
setup:
	which python3 | mkvirtualenv ecs-autoscale -p
	workon ecs-autoscale && \
			cd python-lambda && \
			pip install -r requirements.txt && \
			ln -s `python -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())"` packages

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
