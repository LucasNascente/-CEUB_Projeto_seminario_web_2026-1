FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
ARG SERVICE=chamados-service
COPY ${SERVICE}/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY ${SERVICE}/app.py .
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "flask --app app init-db && exec gunicorn --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --threads 4 --timeout ${GUNICORN_TIMEOUT:-100} app:app"]
