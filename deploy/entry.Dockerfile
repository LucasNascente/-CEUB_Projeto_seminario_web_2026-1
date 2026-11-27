FROM node:22-alpine AS swagger
WORKDIR /swagger
COPY frontend/api-docs/package.json frontend/api-docs/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

FROM node:22-alpine AS assets
WORKDIR /build
COPY frontend/index.html frontend/app.js frontend/tailwind.config.cjs frontend/tailwind.input.css ./
RUN npm install --no-audit --no-fund tailwindcss@3.4.17 materialize-css@1.0.0 && npx tailwindcss -c tailwind.config.cjs -i tailwind.input.css -o tailwind.css --minify

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install --no-install-recommends -y nginx && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY gateway/app.py .
COPY frontend/nginx.conf /app/frontend.conf
COPY frontend/index.html frontend/app.js frontend/style.css /usr/share/nginx/html/
COPY --from=assets /build/tailwind.css /usr/share/nginx/html/
COPY --from=assets /build/node_modules/materialize-css/dist/css/materialize.min.css /usr/share/nginx/html/
COPY frontend/api-docs/index.html frontend/api-docs/openapi.json frontend/api-docs/swagger.js /usr/share/nginx/html/api-docs/
COPY --from=swagger /swagger/node_modules/swagger-ui-dist/swagger-ui-bundle.js /swagger/node_modules/swagger-ui-dist/swagger-ui.css /usr/share/nginx/html/api-docs/vendor/
COPY deploy/entry.sh .
CMD ["sh", "/app/entry.sh"]
