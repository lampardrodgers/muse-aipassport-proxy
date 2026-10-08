#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
if ! command -v idf.py >/dev/null 2>&1; then
    echo 'Activate ESP-IDF v6.0.1 first.' >&2
    exit 1
fi
if [ ! -f build-muse-ai-passport/sdkconfig ]; then
    echo 'Restore the verified original sdkconfig in build-muse-ai-passport first.' >&2
    exit 1
fi
export MUSE_PROXY_PROFILES=1
unset MUSE_HTTP_PROXY_HOST MUSE_HTTP_PROXY_PORT
exec idf.py -B build-muse-ai-passport -DIDF_TARGET=esp32c3 \
    -DSDKCONFIG=build-muse-ai-passport/sdkconfig \
    '-DSDKCONFIG_DEFAULTS=sdkconfig.defaults;devices/sdkconfig.muse;devices/sdkconfig.muse-ai-passport' build
