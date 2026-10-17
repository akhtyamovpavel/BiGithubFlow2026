FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_HEALTH_URL=/health/ready
ARG VITE_SCHEDULE_PATH=/lessons/
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_HEALTH_URL=$VITE_HEALTH_URL
ENV VITE_SCHEDULE_PATH=$VITE_SCHEDULE_PATH
RUN npm run build

FROM nginx:1.28-alpine AS runtime
ENV BACKEND_URL=http://app:8000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
