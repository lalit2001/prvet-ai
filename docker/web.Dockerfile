# syntax=docker/dockerfile:1.7
# --- builder ---
FROM node:20-alpine AS builder
WORKDIR /build
COPY apps/web/package.json apps/web/pnpm-lock.yaml* ./
RUN npm install -g pnpm@9 && pnpm install --frozen-lockfile || pnpm install
COPY apps/web/ ./
RUN pnpm build

# --- runtime ---
FROM nginx:alpine AS runtime
COPY docker/web-entrypoint.sh /docker-entrypoint.d/50-config-js.sh
RUN chmod +x /docker-entrypoint.d/50-config-js.sh
COPY --from=builder /build/out /usr/share/nginx/html
EXPOSE 80
