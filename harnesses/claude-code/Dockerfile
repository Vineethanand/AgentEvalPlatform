# Claude Code harness image (the official `claude` CLI, driven headless with `claude -p`).
# Build from the repo root:  docker build -f harnesses/claude-code/Dockerfile -t aep/harness-claude-code .
# Auth: CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`, uses the Pro/Max subscription).
FROM node:22-slim
ARG CLAUDE_CODE_VERSION=latest
RUN apt-get update && apt-get install -y --no-install-recommends python3 git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN ln -s /usr/bin/python3 /usr/local/bin/python
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}
WORKDIR /opt/aep
COPY workers/evalworker/__init__.py ./evalworker/__init__.py
COPY workers/evalworker/adapters ./evalworker/adapters
ENV PYTHONPATH=/opt/aep PYTHONUNBUFFERED=1 DISABLE_AUTOUPDATER=1
# node's image entrypoint would treat our `python ...` command as a node script
ENTRYPOINT []
