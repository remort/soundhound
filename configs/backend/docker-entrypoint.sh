#!/bin/bash

set -e

echo "Starting up bot backend"

echo "Waiting for Redis"
wait-for-it.sh \
    --host=redis \
    --port=6379 \
    --timeout=10 \
    --strict \
    -- \
    echo "Redis is up"

echo "Starting $@"
exec $@
