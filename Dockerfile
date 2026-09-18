FROM node:22-slim AS web

WORKDIR /web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

# numpy's BLAS sizes its thread pool from the CPU count it detects, which in a
# container is the host's, not this VM's one shared core. Left unset it spawns
# a thread per host core, and every small array operation then pays thread
# spawn and synchronization on a core that can only run one at a time.
# Measured before this: 21.3s per sim-strategy in production against 0.03s on
# a dev machine, a 710x gap.
ENV OMP_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV NUMEXPR_NUM_THREADS=1

COPY ffsim/ /app/ffsim/
COPY api/ /app/api/
COPY data/players_half_ppr.csv /app/data/players_half_ppr.csv
COPY data/players_ppr.csv /app/data/players_ppr.csv
COPY --from=web /web/dist /app/web/dist

WORKDIR /app/api

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
