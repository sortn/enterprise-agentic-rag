FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
COPY requirements-lock.txt /app/requirements-lock.txt
RUN pip install --upgrade pip && pip install -r /app/requirements-lock.txt

COPY project /app/project
COPY evaluation /app/evaluation
RUN mkdir -p /app/data

WORKDIR /app/project
EXPOSE 8000

CMD ["python", "app.py"]
