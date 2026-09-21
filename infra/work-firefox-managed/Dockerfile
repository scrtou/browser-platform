ARG WORK_BASE=browser-platform/work-base:unconfigured
FROM ${WORK_BASE}
ARG WORK_BASE_ID
ARG INPUT_SHA256

COPY browser-platform-autoconfig.js /usr/lib/firefox/defaults/pref/browser-platform-autoconfig.js
COPY browser-platform.cfg /usr/lib/firefox/browser-platform.cfg

RUN chmod 0644 \
      /usr/lib/firefox/defaults/pref/browser-platform-autoconfig.js \
      /usr/lib/firefox/browser-platform.cfg

LABEL io.browser-platform.managed-firefox-network="1" \
      io.browser-platform.managed-firefox-network-input-sha256="${INPUT_SHA256}" \
      io.browser-platform.managed-firefox-network-base="${WORK_BASE_ID}"
