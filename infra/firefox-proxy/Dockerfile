ARG FIREFOX_BASE=lscr.io/linuxserver/firefox@sha256:7e3dbebd9e730952648b8c902ce90fa72c0e2be3e786ab17026c38e0909b47f7
FROM ${FIREFOX_BASE}

COPY browser-platform-autoconfig.js /usr/lib/firefox/defaults/pref/browser-platform-autoconfig.js
COPY browser-platform.cfg /usr/lib/firefox/browser-platform.cfg
COPY environment.json /usr/share/browser-platform/environment.json
COPY browser-platform-entrypoint /usr/local/bin/browser-platform-entrypoint

RUN chmod 0644 \
      /usr/lib/firefox/defaults/pref/browser-platform-autoconfig.js \
      /usr/lib/firefox/browser-platform.cfg \
      /usr/share/browser-platform/environment.json \
    && chmod 0755 /usr/local/bin/browser-platform-entrypoint

ENTRYPOINT ["/usr/local/bin/browser-platform-entrypoint"]
