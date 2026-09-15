# Frontend_App (Next.js/React) container — S3-01a Application Shell Scaffold.
#
# Node base image (design §Compose_Stack: "web/Dockerfile — Node base
# (e.g. node:20-slim): install deps, build the Next.js app, run it on port 3000").
#
# Multi-stage build:
#   1. deps    — install node_modules from the lockfile/manifest
#   2. builder — build the Next.js app (`next build`)
#   3. runner  — run the built app (`next start`) on port 3000
#
# No host address or Service_URL literal appears here. The browser-facing
# backend URL is injected at build/runtime via NEXT_PUBLIC_API_BASE_URL
# (see app/docker-compose.yml and app/web/.env.example), never hard-coded.

# ---- Stage 1: install dependencies ------------------------------------------
FROM node:20-slim AS deps
WORKDIR /app

# Copy only the manifest(s) first so dependency install is cached independently
# of source changes. The lockfile is optional at scaffold time.
COPY package.json package-lock.json* ./
RUN npm install

# ---- Stage 2: build the Next.js app -----------------------------------------
FROM node:20-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* values are inlined at build time; the value is supplied by the
# build environment (Compose / CI), never baked into this file.
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

RUN npm run build

# ---- Stage 3: run the built app ---------------------------------------------
FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production

# Bring across the runtime artefacts produced by the builder.
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.js ./next.config.js
COPY --from=builder /app/.next ./.next
# Note: a Next.js `public/` directory is optional. If task 6.1 adds one, copy it
# here as well (`COPY --from=builder /app/public ./public`); it is omitted so the
# build does not depend on a directory the design's app/web/ layout does not list.

# Next.js serves on port 3000 by default; bind to all interfaces so the
# published host port can reach it.
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
EXPOSE 3000

# `npm run start` -> `next start`, serving the built app on port 3000.
CMD ["npm", "run", "start"]
