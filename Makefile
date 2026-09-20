.PHONY: help install lint test build run stop

PYTHON      := python3
PIP         := pip3
IMAGE_NAME  := flights-api
IMAGE_TAG   := latest
COMPOSE     := docker-compose
APP_DIR     := services/api

help:
	@echo "Available targets:"
	@echo "  install       Install Python dependencies"
	@echo "  lint          Run black + pylint"
	@echo "  test          Run pytest with coverage"
	@echo "  build         Build Docker image"
	@echo "  run           Start app + postgres with docker-compose"
	@echo "  stop          Stop docker-compose services"

install:
	$(PIP) install -r $(APP_DIR)/requirements.txt

lint:
	black --check --diff $(APP_DIR)/app/ shared/
	pylint $(APP_DIR)/app/ shared/ --fail-under=7.0

test:
	cd $(APP_DIR) && pytest tests/ --cov=app --cov=shared --cov-report=term-missing -v

# Context is the repo root so the Dockerfile can COPY shared/
build:
	docker build -f $(APP_DIR)/Dockerfile -t $(IMAGE_NAME):$(IMAGE_TAG) .

run:
	$(COMPOSE) up --build

stop:
	$(COMPOSE) down -v
