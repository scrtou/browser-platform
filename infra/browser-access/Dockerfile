ARG WORKER_BASE=browser-platform/worker-base:unconfigured
FROM ${WORKER_BASE}
ARG WORKER_BASE_ID
ARG INPUT_SHA256
COPY session_access.py install.py /usr/local/lib/browser-platform/access-layer/
RUN python3 /usr/local/lib/browser-platform/access-layer/install.py
LABEL io.browser-platform.session-auth="1" \
      io.browser-platform.session-auth-input-sha256="${INPUT_SHA256}" \
      io.browser-platform.worker-base="${WORKER_BASE_ID}"
