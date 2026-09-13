#!/bin/sh
# LinuxServer runs custom init after init-nginx rebuilds the dashboard assets.
set -eu
python3 /opt/browser-platform/selkies-paste/enable-screenshot-paste.py
