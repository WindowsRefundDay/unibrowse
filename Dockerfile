FROM python:3.13-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV BU_CDP_URL=http://127.0.0.1:9223
ENV BH_NO_ACTIVATE=1
ENV BU_NAME=unibrowse

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/unibrowse
COPY . /app/unibrowse

RUN pip install -e ./browser-harness

EXPOSE 9223

CMD chromium \
    --headless=new \
    --no-sandbox \
    --disable-dev-shm-usage \
    --remote-debugging-address=0.0.0.0 \
    --remote-debugging-port=9223 \
    --user-data-dir=/data/chrome-profile \
    about:blank
