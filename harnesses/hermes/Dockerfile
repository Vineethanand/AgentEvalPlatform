# Hermes Agent harness image.
# Build from the repo root:  docker build -f harnesses/hermes/Dockerfile -t aep/harness-hermes .
# Pin HERMES_REF to a commit for reproducible results; the image digest is recorded with each config.
FROM python:3.12-slim
ARG HERMES_REF=main
RUN apt-get update && apt-get install -y --no-install-recommends git curl build-essential && rm -rf /var/lib/apt/lists/*
RUN git clone --recurse-submodules https://github.com/NousResearch/hermes-agent.git /opt/hermes \
 && cd /opt/hermes && git checkout ${HERMES_REF} \
 && pip install --no-cache-dir -e . \
 && (pip install --no-cache-dir -e ./mini-swe-agent || true)
WORKDIR /opt/aep
COPY workers/evalworker/__init__.py ./evalworker/__init__.py
COPY workers/evalworker/adapters ./evalworker/adapters
# run_agent.py lives at the root of the Hermes checkout
ENV PYTHONPATH=/opt/aep:/opt/hermes PYTHONUNBUFFERED=1
