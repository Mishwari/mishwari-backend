FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY mishwari_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Django project
COPY mishwari_server/ .

# Collect static files
RUN python manage.py collectstatic --noinput || echo "Static files collection skipped"

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "mishwari_server.wsgi:application"]