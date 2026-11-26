FROM node:22-alpine AS assets
WORKDIR /build
COPY index.html app.js tailwind.config.cjs tailwind.input.css ./
RUN npm install --no-audit --no-fund tailwindcss@3.4.17 materialize-css@1.0.0 && npx tailwindcss -c tailwind.config.cjs -i tailwind.input.css -o tailwind.css --minify
FROM nginx:1.28-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html app.js style.css /usr/share/nginx/html/
COPY --from=assets /build/tailwind.css /usr/share/nginx/html/
COPY --from=assets /build/node_modules/materialize-css/dist/css/materialize.min.css /usr/share/nginx/html/
