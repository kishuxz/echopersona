FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

# Bake API/WS URLs into the Vite bundle at build time.
# Override with --build-arg if deploying to a non-localhost host.
ARG VITE_API_BASE_URL=""
ARG VITE_WS_BASE_URL="ws://localhost"
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_BASE_URL=$VITE_WS_BASE_URL

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
