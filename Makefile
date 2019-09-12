test = test/
repo = epwalsh/ecs-autoscale
cmd = ls


.PHONY : docker-build
docker-build :
	docker build -t $(repo) .

.PHONY : docker-run
docker-run :
	docker run --env-file=./access.txt --rm $(repo) $(cmd)

.PHONY : build
build :
	@echo "Creating deployment package"
	@cd lambda && zip -r ../deployment.zip * &> /dev/null
	@ls -lh | grep *.zip

.PHONY : push
push :
	aws lambda update-function-code \
			--function-name "ecs-autoscale" \
			--zip-file fileb://./deployment.zip

.PHONY : deploy
deploy : build push

.PHONY : typecheck
typecheck :
	@mypy lambda --ignore-missing-imports

.PHONY : lint
lint :
	@echo "Lint (pylint):"
	@pylint --rcfile=./.pylintrc -f colorized lambda

.PHONY : unit-test
unit-test :
	@echo "Unit tests (pytest):"
	@export PYTHONPATH=./lambda && pytest --color=yes $(test)

.PHONY : test
test : typecheck lint unit-test

.PHONY : test-run
test-run :
	@cd lambda && python lambda_function.py --test

.PHONY : clean
clean :
	@echo "Removing compiled Python objects"
	@find . | grep -E "(__pycache__|\.pyc|\.pyo$$)" | xargs rm -rf
