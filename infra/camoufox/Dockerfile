ARG FIREFOX_BASE=lscr.io/linuxserver/firefox@sha256:7e3dbebd9e730952648b8c902ce90fa72c0e2be3e786ab17026c38e0909b47f7
FROM ${FIREFOX_BASE} AS browser
COPY .build/browser.zip /tmp/browser.zip
COPY versions.json install_browser.py managed-preferences.js /tmp/install/
RUN python3 /tmp/install/install_browser.py /tmp/browser.zip \
      /tmp/install/versions.json /tmp/install/managed-preferences.js /opt/camoufox/browser

FROM ${FIREFOX_BASE}
COPY requirements.lock /usr/local/lib/browser-platform/requirements.lock
RUN python3 -m venv --without-pip /opt/camoufox-python \
    && python3 -m pip --python /opt/camoufox-python/bin/python install \
      --no-cache-dir --only-binary=:all: --require-hashes \
      --requirement /usr/local/lib/browser-platform/requirements.lock
COPY --from=browser /opt/camoufox /opt/camoufox
COPY versions.json environment.py spec.tw.json /usr/local/lib/browser-platform/
COPY browser-platform-entrypoint browser-platform-camoufox /usr/local/bin/
COPY autostart /defaults/autostart
COPY configure-desktop.py /tmp/browser-platform-configure-desktop.py
RUN python3 /tmp/browser-platform-configure-desktop.py \
    && rm /tmp/browser-platform-configure-desktop.py
RUN chmod 0755 /usr/local/bin/browser-platform-entrypoint \
      /usr/local/bin/browser-platform-camoufox /defaults/autostart
ENV BROWSER_PLATFORM_ARTIFACT_FILE=/run/browser-platform/environment.json
ENTRYPOINT ["/usr/local/bin/browser-platform-entrypoint"]
