# El Frontend - Dockerfile
# =========================
# Multi-stage build for Vue 3 application
#
# Stages:
#   development - Dev server with hot reload (used by docker-compose, security-scan)
#   build       - Production build step
#   production  - Nginx serving static files
#
# Build:
#   docker build -t el-frontend .                           # Production (default)
#   docker build -t el-frontend:dev --target development .  # Development
# Run:
#   docker run -p 5173:5173 el-frontend:dev   # Dev server
#   docker run -p 80:80 el-frontend           # Production

# ============================================
# Stage 1: Development
# ============================================
FROM node:20-alpine AS development

# Fix CVE-2026-22184 (zlib buffer overflow) — update alpine packages
RUN apk update && apk upgrade --no-cache

WORKDIR /app

# Install dependencies first (for better caching)
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./

# Install dependencies based on available lockfile
RUN if [ -f pnpm-lock.yaml ]; then \
        npm install -g pnpm && pnpm install --frozen-lockfile; \
    elif [ -f yarn.lock ]; then \
        yarn install --frozen-lockfile; \
    else \
        npm ci; \
    fi

# Copy application code
COPY . .

# Create non-root user
RUN addgroup -g 1001 -S appgroup && \
    adduser -S appuser -u 1001 -G appgroup && \
    chown -R appuser:appgroup /app

USER appuser

# Environment
ENV NODE_ENV=development
ENV HOST=0.0.0.0

# Expose Vite dev server port
EXPOSE 5173

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -q --spider http://localhost:5173 || exit 1

# Run Vite dev server with host binding
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ============================================
# Stage 2: Build
# ============================================
FROM development AS build

# Switch to root for build (need write access)
USER root

# Build production bundle
RUN npm run build

# ============================================
# Stage 3: Production
# ============================================
FROM nginx:alpine AS production

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Create non-root user
RUN addgroup -g 1001 -S appgroup && \
    adduser -S appuser -u 1001 -G appgroup

# Expose HTTP port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:80 || exit 1

CMD ["nginx", "-g", "daemon off;"]
