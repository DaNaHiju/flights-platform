# flights-platform

FastAPI flights-search service. Application code only.
Terraform lives in the SEPARATE repo `flights-platform-infra`.
Deployment manifests live in the SEPARATE repo `flights-platform-manifests`.

## Context
Portfolio project doubling as a DevOps home assignment (EKS / ArgoCD / Istio / Helm / Terraform).
Every line must be explainable out loud in a review call. Prefer clarity over cleverness.

## Stack
- Python 3.12, FastAPI
- `fli` library (reverse-engineers Google Flights) — no official API key
- Docker multi-stage build, non-root runtime user
- Optional deps: PostgreSQL, Redis (conditional Helm subcharts, not always enabled)

## Repo boundary — IMPORTANT
This repo contains: app source, tests, Dockerfile, CI pipeline.
This repo NEVER contains: Helm charts, Kubernetes manifests, ArgoCD Applications,
Terraform. If a task needs those, say so — do not create them here.
Rationale: three-repo GitOps. Keeps CI from retriggering itself on image-tag bumps,
and keeps ArgoCD's desired-state repo as the single source of truth.

Layout:
- `flights-platform` (this repo) — application code only.
- `flights-platform-infra` — Terraform: EKS, VPC, IAM, ECR, remote-state backend.
  Not yet applied against AWS — the backend block in `versions.tf` has
  placeholders on purpose, filled in once `bootstrap/` is run. Today's active
  environment is k3s on pop-os, not EKS.
- `flights-platform-manifests` — Helm charts, ArgoCD Applications.

This rule (no Terraform/manifests in this repo) holds as of the
terraform/k8s/Jenkinsfile removal. Before that, this repo carried its own
`terraform/` and `k8s/` directories and a `Jenkinsfile`, which violated the
boundary above — the app history predates the three-repo split.

## Conventions
- Git: `git switch`, never `git checkout`
- Commits: short, English, imperative mood ("add health probe endpoint")
- Health endpoints: `/health` (liveness), `/ready` (readiness) — both must return 200
- Container must run as non-root with a read-only root filesystem

## Hard rules
- No secrets, tokens, or credentials in code or committed files. Ever.
- Secrets come from AWS Secrets Manager via External Secrets Operator at runtime.
- Do not add dependencies without saying why first.

