FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

COPY ffsim/ /app/ffsim/
COPY api/ /app/api/
COPY data/players_half_ppr.csv /app/data/players_half_ppr.csv
COPY data/players_ppr.csv /app/data/players_ppr.csv

WORKDIR /app/api

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
