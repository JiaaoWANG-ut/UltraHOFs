# UltraHOFs production image: built web UI + FastAPI backend + Zeo++ + MACE (CPU/GPU via torch wheels).
# Build from the repository root:  docker build -f deploy/Dockerfile -t ultrahofs:0.1.0 .

FROM node:22-bookworm-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM mambaorg/micromamba:1.5-bookworm-slim AS app
USER root
WORKDIR /app
COPY environment.yml /tmp/environment.yml
RUN micromamba install -y -n base -f /tmp/environment.yml && micromamba clean -a -y
ARG MAMBA_DOCKERFILE_ACTIVATE=1
COPY backend/ /app/backend/
RUN pip install --no-cache-dir "/app/backend[relax]" psycopg[binary]
COPY --from=web /src/frontend/dist /app/frontend/dist
COPY scripts/ /app/scripts/
ENV ULTRAHOFS_VAR_DIR=/data/var \
    ULTRAHOFS_DATA_DIR=/data/data \
    OMP_NUM_THREADS=8
VOLUME ["/data"]
EXPOSE 8000
# The API serves the built UI on the same port; put a TLS-terminating reverse proxy in front.
CMD ["uvicorn", "ultrahofs.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/backend", "--workers", "2"]
