site-packages=`python -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())"`

.PHONY: setup
setup:
	workon ecs-autoscale
	cd python-lambda && \
			pip install -r requirements.txt && \
			ln -s $(site-packages) packages


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
