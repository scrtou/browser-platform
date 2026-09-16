ARG WORKER_BASE=browser-platform/worker-base:unconfigured
FROM ${WORKER_BASE}
ARG WORKER_BASE_ID
ARG INPUT_SHA256
COPY browser-shutdown.py wayland_shutdown.py before-desktop-stop install.py /usr/local/lib/browser-platform/
RUN python3 /usr/local/lib/browser-platform/install.py
LABEL io.browser-platform.browser-shutdown="1" \
      io.browser-platform.shutdown-input-sha256="${INPUT_SHA256}" \
      io.browser-platform.worker-base="${WORKER_BASE_ID}"
