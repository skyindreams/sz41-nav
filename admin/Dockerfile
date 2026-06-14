FROM python:3.11-slim

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure data dir exists with proper permissions
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser
EXPOSE 8901

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8901"]
