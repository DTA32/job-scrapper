ARG PLAYWRIGHT_VERSION=v1.59.0-jammy

FROM mcr.microsoft.com/playwright/python:${PLAYWRIGHT_VERSION} AS builder

WORKDIR /build

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --user -r requirements.txt


FROM mcr.microsoft.com/playwright/python:${PLAYWRIGHT_VERSION} AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/home/pwuser/.local/bin:/usr/local/bin:/usr/bin:/bin

RUN mkdir -p /app/output \
 && chown -R pwuser:pwuser /app

COPY --from=builder --chown=pwuser:pwuser /root/.local /home/pwuser/.local

WORKDIR /app

COPY --chown=pwuser:pwuser scraper ./scraper
COPY --chown=pwuser:pwuser config.yaml ./config.yaml

USER pwuser


FROM runtime-base AS scraper-cli

ENTRYPOINT ["python", "-m", "scraper"]
CMD []


FROM runtime-base AS mcp-server

USER root
COPY --chown=pwuser:pwuser mcp_server ./mcp_server
USER pwuser

ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8080

EXPOSE 8080

ENTRYPOINT ["python", "-m", "mcp_server.server"]
CMD []


FROM node:20-slim AS bot

ARG SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/latest/download/supercronic-linux-amd64

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "$SUPERCRONIC_URL" -o /usr/local/bin/supercronic \
 && chmod +x /usr/local/bin/supercronic

RUN npm install -g @anthropic-ai/claude-code

WORKDIR /workspace/scraper-bot

COPY --chown=node:node cron ./cron
COPY --chown=node:node prompts ./prompts
COPY --chown=node:node claude/mcp.json.example ./.mcp.json

RUN chmod +x cron/entrypoint.sh cron/run-scraper.sh \
 && mkdir -p /home/node/.claude \
 && touch /home/node/.claude.json \
 && chown -R node:node /home/node /workspace

USER node

ENTRYPOINT ["/usr/local/bin/supercronic"]
CMD ["/workspace/scraper-bot/cron/scraper-crontab"]
