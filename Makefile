.PHONY: help install lint test build run stop

PYTHON       := python3
PIP          := pip3
IMAGE_TAG    := latest
COMPOSE      := docker-compose
API_DIR      := services/api
WORKER_DIR   := services/worker
API_IMAGE    := flights-api
WORKER_IMAGE := flights-worker

help:
	@echo "Available targets:"
	@echo "  install       Install Python dependencies (api + worker)"
	@echo "  lint          Run black + pylint on api, worker and shared"
	@echo "  test          Run pytest with coverage for api and worker"
	@echo "  build         Build both Docker images"
	@echo "  run           Start api + worker + postgres + redis with docker-compose"
	@echo "  stop          Stop docker-compose services"

install:
	$(PIP) install -r $(API_DIR)/requirements.txt -r $(WORKER_DIR)/requirements.txt

lint:
	black --check --diff $(API_DIR)/app/ $(WORKER_DIR)/worker/ shared/
	pylint $(API_DIR)/app/ $(WORKER_DIR)/worker/ shared/ --fail-under=7.0

# One pytest run per service: both have a top-level `tests` package, so they
# cannot share a session. shared/ coverage is reported in both runs.
test:
	cd $(API_DIR) && $(PYTHON) -m pytest tests/ --cov=app --cov=shared --cov-report=term-missing -v
	cd $(WORKER_DIR) && $(PYTHON) -m pytest tests/ --cov=worker --cov=shared --cov-report=term-missing -v

# Context is the repo root so each Dockerfile can COPY shared/
build:
	docker build -f $(API_DIR)/Dockerfile -t $(API_IMAGE):$(IMAGE_TAG) .
	docker build -f $(WORKER_DIR)/Dockerfile -t $(WORKER_IMAGE):$(IMAGE_TAG) .

run:
	$(COMPOSE) up --build

stop:
	$(COMPOSE) down -v
