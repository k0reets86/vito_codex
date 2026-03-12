FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PROJECT_ROOT=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt
RUN python -m patchright install chromium || python -m playwright install --with-deps chromium

COPY . /app

RUN mkdir -p /app/logs /app/runtime /app/output /app/memory

CMD ["python3", "-u", "main.py"]
