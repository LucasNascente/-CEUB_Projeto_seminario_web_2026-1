FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
ARG SERVICE
COPY ${SERVICE}/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY ${SERVICE}/app.py .
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "app:app"]
