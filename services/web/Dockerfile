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

# The base image can lag behind Alpine's security fixes (Trivy flags them with a
# fix available), so pull the patched packages. Root only for this one RUN.
USER root
RUN apk upgrade --no-cache
USER 101

COPY services/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist/ /usr/share/nginx/html/

EXPOSE 8080
