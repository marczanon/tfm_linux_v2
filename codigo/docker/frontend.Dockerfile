# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-build

WORKDIR /app

COPY codigo/frontend/package.json codigo/frontend/package-lock.json ./
RUN npm ci

COPY codigo/frontend/ ./

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginx:1.27-alpine AS frontend

ENV TFM_FRONTEND_PORT=5173 \
    TFM_BACKEND_URL=http://backend:8010

COPY codigo/docker/frontend.nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=frontend-build /app/dist /usr/share/nginx/html

EXPOSE 5173

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- "http://127.0.0.1:${TFM_FRONTEND_PORT}/healthz" >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
