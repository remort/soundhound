FROM python:3.7-slim
LABEL Vadim Bazhov <master@remort.net>

ARG environment
ENV PYTHONUNBUFFERED=1 ENV=${environment}

COPY requirements.txt /tmp
COPY wait-for-it.sh docker-entrypoint.sh /usr/local/bin/

RUN apt update && apt install --yes --no-install-recommends && \
    chmod +x /usr/local/bin/wait-for-it.sh /usr/local/bin/docker-entrypoint.sh && \
    pip install --disable-pip-version-check -r /tmp/requirements.txt && \
    rm -f /tmp/requirements.txt

WORKDIR /app

ENTRYPOINT ["docker-entrypoint.sh"]
