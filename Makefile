.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help
help: # See: https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

upload: ## Upload to the system
	rm -rf .pio/build
	platformio run -t upload -e cyd &
	platformio run -t upload -e left &

monitor-r:
	screen -m -port /dev/cu.usbserial-2110 115200

monitor-l:
	screen -m -port /dev/cu.usbserial-21430 115200

run: ## Run
	uv run python main.py