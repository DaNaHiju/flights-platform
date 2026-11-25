# syntax=docker/dockerfile:1
# Build context is the REPO ROOT, same as the Python services:
#   docker build -f services/web/Dockerfile .
# ── Stage 1: build the static site ───────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /web

# Dependencies first: this layer is reused while package*.json do not change.
COPY services/web/package.json services/web/package-lock.json ./
RUN npm ci

COPY services/web/index.html services/web/tsconfig.json services/web/vite.config.ts ./
COPY services/web/src/ ./src/
RUN npm run build

# ── Stage 2: serve it ────────────────────────────────────────────────────────
# nginx-unprivileged already runs as uid 101 and listens on 8080, so no root
# is needed to bind a port. Only the static files and one config are copied in.
FROM nginxinc/nginx-unprivileged:stable-alpine

# The base image can lag behind security fixes that are already published, and
# Trivy fails the build on those (CRITICAL/HIGH with a fix available). Two kinds:
#   1. Alpine packages: `apk upgrade` against the image's own Alpine repos.
#   2. nginx itself: it comes from nginx.org's apk repo, which the base image
#      removes after installing, and /etc/apk/world pins the exact version. So
#      plain `apk upgrade` never moves it. Re-adding every installed nginx*
#      package by name (no version) from nginx.org's repo lifts the pin and
#      installs the latest stable build. The packages are signature-checked with
#      the nginx.org key the base image left in /etc/apk/keys.
# Root only for this one RUN.
USER root
RUN apk upgrade --no-cache && \
    NGINX_REPO="https://nginx.org/packages/alpine/v$(cut -d. -f1,2 /etc/alpine-release)/main" && \
    apk add --no-cache --upgrade --repository "$NGINX_REPO" $(apk info | grep '^nginx') && \
    nginx -v
USER 101

COPY services/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist/ /usr/share/nginx/html/

EXPOSE 8080
