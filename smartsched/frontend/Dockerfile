# syntax=docker/dockerfile:1.7
# SmartSched frontend: Next.js 16 standalone build (multi-stage, non-root).
# Build context: smartsched/frontend. `output: "standalone"` is set in next.config.ts.
#
# NEXT_PUBLIC_* values are inlined by `next build` into both the client and the server bundles
# (they cannot be changed at run time), so they are build args; compose passes them from .env.
# Reproducibility: pinned base image + `npm ci` against package-lock.json.

ARG NODE_IMAGE=node:22.23.3-alpine3.24

FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM ${NODE_IMAGE} AS build
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=http://backend:8000
ARG NEXT_PUBLIC_API_MOCK=0
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_API_MOCK=$NEXT_PUBLIC_API_MOCK \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM ${NODE_IMAGE} AS runtime
LABEL org.opencontainers.image.title="smartsched-frontend" \
      org.opencontainers.image.description="SmartSched web UI (Next.js standalone)"
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
# The standalone output contains a minimal node_modules + server.js; static assets and
# /public are not included and must be copied next to it.
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD wget -q -O /dev/null --spider http://127.0.0.1:3000/login || exit 1
CMD ["node", "server.js"]
