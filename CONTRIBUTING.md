This project is in its very early stages and we encourage developer contributions.

Before submitting a PR, please do this checklist first:

- Run `make test` and fix any errors. You can also run all of the tests through the Docker container with:

 ```
 docker run --env-file=./access.txt --rm epwalsh/ecs-autoscale make test
 ```

- When adding new functionality, also add tests for this functionality.
- Include a detailed description of the changes you made and the rational behind
them in your PR.
