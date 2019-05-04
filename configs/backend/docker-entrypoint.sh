#!/bin/bash

set -e

echo "Starting up bot backend"

echo "Waiting for Privoxy"
wait-for-it.sh \
    --host=proxy \
    --port=8118 \
    --timeout=15 \
    --strict \
    -- \
    echo "Privoxy is up"

sleep 10
echo "Starting $@"
exec $@
