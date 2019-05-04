FROM alpine:latest
LABEL Vadim Bazhov <master@remort.net>

RUN apk add --no-cache tor privoxy supervisor

COPY torrc torsocks.conf /etc/tor/
COPY supervisord.conf /etc/supervisord.conf
COPY privoxy.conf /etc/privoxy/config

EXPOSE 8118
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
