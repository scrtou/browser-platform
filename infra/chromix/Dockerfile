ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG INPUT_SHA256
COPY chromix /opt/chromix
COPY release.lock.json /opt/chromix/release.lock.json
COPY fonts.lock.json /opt/chromix/fonts.lock.json
COPY fonts.conf.template /opt/chromix/fonts/fonts.conf.template
COPY launcher.py /usr/local/lib/browser-platform/chromix-launcher.py
COPY x11_shutdown.py /usr/local/lib/browser-platform/x11_shutdown.py
COPY shutdown.py /usr/local/lib/browser-platform/browser-shutdown.py
COPY autostart /defaults/autostart
COPY entrypoint /usr/local/bin/browser-platform-chromix-entrypoint
RUN chmod 755 /usr/local/bin/browser-platform-chromix-entrypoint /defaults/autostart \
    && python3 -c 'from pathlib import Path; p=Path("/etc/xdg/openbox/rc.xml"); s=p.read_text(); assert s.count("</applications>")==1; p.write_text(s.replace("</applications>", "<application class=\"chromium\"><maximized>yes</maximized><decor>no</decor></application></applications>"))'
ENV PIXELFLUX_WAYLAND=false TITLE=Chromix SELKIES_UI_TITLE=Chromix
LABEL io.browser-platform.chromix-input-sha256="${INPUT_SHA256}" \
      io.browser-platform.browser-engine="chromix" \
      io.browser-platform.chromix-version="154.0.8037.57" \
      io.browser-platform.browser-shutdown="1" \
      io.browser-platform.session-auth="1"

ENTRYPOINT ["/usr/local/bin/browser-platform-chromix-entrypoint"]
