test = test/
repo = epwalsh/ecs-autoscale

.PHONY : docker-build
docker-build :
	docker build -t $(repo) .

.PHONY : docker-run
docker-run :
	docker run --env-file=./access.txt --rm $(repo)

.PHONY : build
build :
	@cd lambda && zip -r ../deployment.zip *

.PHONY : push
push :
	aws lambda update-function-code \
			--function-name "ecs-autoscale" \
			--zip-file fileb://./deployment.zip

.PHONY : deploy
deploy : clean build push


.PHONY : typecheck
typecheck :
	-@mypy lambda --ignore-missing-imports

.PHONY : lint
lint :
	@echo "\nLint (pylint):\n"
	-@pylint --rcfile=./.pylintrc -f colorized lambda

.PHONY : unit-test
unit-test :
	@echo "Unit tests (pytest):\n"
	@export PYTHONPATH=./lambda && pytest --color=yes $(test)

.PHONY : test
test : clean typecheck lint unit-test

.PHONY : clean
clean :
	@echo "Removing compiled Python objects"
	@find . | grep -E "(__pycache__|\.pyc|\.pyo$$)" | xargs rm -rf
