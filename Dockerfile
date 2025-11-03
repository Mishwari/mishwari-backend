FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY mishwari_server/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY mishwari_server/ /app/

CMD ["gunicorn", "mishwari_server.wsgi:application", "--bind", "0.0.0.0:8000"]