FROM python:3.8-alpine
LABEL maintainer=master@remort.net

ARG environment
ENV PYTHONUNBUFFERED=1 ENV=${environment}

COPY requirements.txt /tmp
COPY wait-for-it.sh docker-entrypoint.sh /usr/local/bin/
COPY gunicorn.py /etc

RUN apk add --no-cache bash coreutils build-base ffmpeg python-dev py-pip jpeg-dev zlib-dev && \
    chmod +x /usr/local/bin/wait-for-it.sh /usr/local/bin/docker-entrypoint.sh && \
    pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt && \
    apk del build-base python-dev py-pip jpeg-dev zlib-dev && \
    rm -rf /usr/share/terminfo /usr/share/X11/locale /tmp/requirements.txt

ENTRYPOINT ["docker-entrypoint.sh"]
