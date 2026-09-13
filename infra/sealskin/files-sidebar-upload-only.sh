#!/bin/sh
# Existing Workers use this LinuxServer custom-init hook. New Workers receive
# the same two settings from their SealSkin application definition.
set -eu

printf '%s' true > /run/s6/container_environment/SELKIES_UI_SIDEBAR_SHOW_FILES
printf '%s' upload > /run/s6/container_environment/SELKIES_FILE_TRANSFERS
