FROM python:3.8-slim
LABEL Vadim Bazhov <master@remort.net>

ARG environment
ENV PYTHONUNBUFFERED=1 ENV=${environment}

COPY requirements.txt /tmp
COPY wait-for-it.sh docker-entrypoint.sh /usr/local/bin/
COPY gunicorn.py /etc

RUN apt-get update && apt-get install ffmpeg --yes --no-install-recommends && \
    chmod +x /usr/local/bin/wait-for-it.sh /usr/local/bin/docker-entrypoint.sh && \
    pip install --disable-pip-version-check -r /tmp/requirements.txt && \
    rm -f /tmp/requirements.txt

ENTRYPOINT ["docker-entrypoint.sh"]
