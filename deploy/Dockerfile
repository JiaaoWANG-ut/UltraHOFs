# UltraHOFs runtime image: web UI + API + job worker + Zeo++ + MACE (CPU), with the experimental HOF
# database baked in. Used by the GitHub Codespaces trial (.devcontainer/) and for internal servers.
#
# Build from the repository root after putting the data bundle into deploy/seed/, either
#   ultrahofs export-seed deploy/seed                                   (from an existing installation) or
#   tar -xzf ultrahofs-data-<version>.tar.gz -C deploy/seed --strip-components=1   (release asset)
# then:  docker build -f deploy/Dockerfile -t ultrahofs .
#
# The MACE-OFF24 model (Academic Software License) is not included; it is downloaded on first use.

FROM docker.io/library/node:22-bookworm-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM docker.io/mambaorg/micromamba:1.5-bookworm-slim
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git less procps \
 && rm -rf /var/lib/apt/lists/*
COPY deploy/environment.runtime.yml /tmp/environment.yml
RUN micromamba install -y -n base -f /tmp/environment.yml && micromamba clean -a -y
ENV PATH=/opt/conda/bin:$PATH
COPY deploy/constraints.txt /tmp/constraints.txt
RUN pip install --no-cache-dir -c /tmp/constraints.txt torch --index-url https://download.pytorch.org/whl/cpu
COPY backend/ /app/backend/
RUN pip install --no-cache-dir -c /tmp/constraints.txt "/app/backend[relax]" "psycopg[binary]"
COPY --from=web /src/frontend/dist /app/frontend/dist
COPY deploy/seed/ /opt/ultrahofs/seed/
COPY deploy/entrypoint.sh /usr/local/bin/ultrahofs-entrypoint
COPY deploy/codespaces-start.sh /usr/local/bin/ultrahofs-codespaces-start
COPY LICENSE THIRD_PARTY_NOTICES.md /app/
RUN chmod 755 /usr/local/bin/ultrahofs-entrypoint /usr/local/bin/ultrahofs-codespaces-start \
 && test -f /opt/ultrahofs/seed/ultrahofs.db \
 && python -c "import rdkit, pymatgen, gemmi, spglib, torch, mace, ultrahofs; print('imports ok')" \
 && command -v network

ENV ULTRAHOFS_VAR_DIR=/data/var \
    ULTRAHOFS_DATA_DIR=/data/data \
    ULTRAHOFS_WEB_DIR=/app/frontend/dist \
    ULTRAHOFS_SEED_DIR=/opt/ultrahofs/seed \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8000
LABEL org.opencontainers.image.title="UltraHOFs" \
      org.opencontainers.image.description="HOF design platform by Ultra-X (知声无界)" \
      org.opencontainers.image.source="https://github.com/JiaaoWANG-ut/UltraHOFs" \
      org.opencontainers.image.licenses="LicenseRef-UltraX-Proprietary"
ENTRYPOINT ["ultrahofs-entrypoint"]
CMD ["all"]
