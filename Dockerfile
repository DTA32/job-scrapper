ARG PLAYWRIGHT_VERSION=v1.59.0-jammy

FROM mcr.microsoft.com/playwright/python:${PLAYWRIGHT_VERSION} AS builder

WORKDIR /build

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --user -r requirements.txt


FROM mcr.microsoft.com/playwright/python:${PLAYWRIGHT_VERSION}

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

ENTRYPOINT ["python", "-m", "scraper"]
CMD []
