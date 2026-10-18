# Baseline harness: our own plain tool-calling loop. Stdlib only.
# Build from the repo root:  docker build -f harnesses/baseline/Dockerfile -t aep/harness-baseline .
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/aep
COPY workers/evalworker/__init__.py ./evalworker/__init__.py
COPY workers/evalworker/adapters ./evalworker/adapters
ENV PYTHONPATH=/opt/aep PYTHONUNBUFFERED=1
