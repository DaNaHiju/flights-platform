.PHONY: help install lint test build run destroy budget-alarm

PYTHON      := python3
PIP         := pip3
IMAGE_NAME  := myapp
IMAGE_TAG   := latest
COMPOSE     := docker-compose
TF_DIR      := terraform
ALERT_EMAIL ?= your-email@example.com

help:
	@echo "Available targets:"
	@echo "  install       Install Python dependencies"
	@echo "  lint          Run black + pylint"
	@echo "  test          Run pytest with coverage"
	@echo "  build         Build Docker image"
	@echo "  run           Start app + postgres with docker-compose"
	@echo "  destroy       Terraform destroy (ALWAYS run after EKS session)"
	@echo "  budget-alarm  Create AWS Budget alarm at \$10 / 80% threshold"

install:
	$(PIP) install -r requirements.txt

lint:
	black --check --diff app/
	pylint app/ --fail-under=7.0

test:
	pytest tests/ --cov=app --cov-report=term-missing -v

build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

run:
	$(COMPOSE) up --build

stop:
	$(COMPOSE) down -v

# ── kind (local Kubernetes) ───────────────────────────────────────────────────
kind-up:
	kind create cluster --name jenkins-argocd
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/postgres-local.yaml

kind-down:
	kind delete cluster --name jenkins-argocd

# ── Terraform (AWS) ───────────────────────────────────────────────────────────
tf-init:
	cd $(TF_DIR) && terraform init

tf-plan:
	cd $(TF_DIR) && terraform plan

tf-apply:
	cd $(TF_DIR) && terraform apply -auto-approve

destroy:
	@echo ">>> Destroying all AWS resources to avoid billing <<<"
	cd $(TF_DIR) && terraform destroy -auto-approve

# ── AWS Budget alarm ($10 / 80%) — use on Free Plan accounts ─────────────────
budget-alarm:
	@echo "Creating AWS Budget: \$$10/month alert at 80% for $(ALERT_EMAIL)"
	aws budgets create-budget \
	  --account-id $$(aws sts get-caller-identity --query Account --output text) \
	  --budget '{ \
	    "BudgetName": "ecommerce-api-monthly-budget", \
	    "BudgetLimit": {"Amount": "10", "Unit": "USD"}, \
	    "TimeUnit": "MONTHLY", \
	    "BudgetType": "COST" \
	  }' \
	  --notifications-with-subscribers '[{ \
	    "Notification": { \
	      "NotificationType": "ACTUAL", \
	      "ComparisonOperator": "GREATER_THAN", \
	      "Threshold": 80, \
	      "ThresholdType": "PERCENTAGE" \
	    }, \
	    "Subscribers": [{ \
	      "SubscriptionType": "EMAIL", \
	      "Address": "$(ALERT_EMAIL)" \
	    }] \
	  }]'
	@echo "Budget alarm created. Check AWS Billing console."
