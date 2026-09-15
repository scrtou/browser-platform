#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "${script_dir}/build"
cd "${script_dir}"
CGO_ENABLED=0 GOOS=linux GOARCH="$(go env GOARCH)" \
    go build -buildvcs=false -trimpath \
    -o "${script_dir}/build/profile-relay" \
    ./cmd/profile-relay
chmod 0755 "${script_dir}/build/profile-relay"
inputs_revision="$(sha256sum Dockerfile .dockerignore build/profile-relay | sha256sum | cut -d ' ' -f 1)"
image_name="${PROFILE_RELAY_IMAGE:-browser-platform/profile-relay:relay-v2-${inputs_revision:0:16}}"
if existing_revision="$(docker image inspect "${image_name}" --format '{{ index .Config.Labels "io.browser-platform.relay-inputs" }}' 2>/dev/null)"; then
    if [[ "${existing_revision}" != "${inputs_revision}" ]]; then
        printf '%s\n' 'Existing image tag has different or unproven inputs; it was not overwritten.' >&2
        exit 1
    fi
else
    docker build --pull=false --label "io.browser-platform.relay-inputs=${inputs_revision}" --tag "${image_name}" "${script_dir}"
fi
printf '%s\n' "${image_name}"
