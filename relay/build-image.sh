#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
image_name="${PROFILE_RELAY_IMAGE:-browser-platform/profile-relay:relay-v1}"

mkdir -p "${script_dir}/build"
cd "${script_dir}"
CGO_ENABLED=0 GOOS=linux GOARCH="$(go env GOARCH)" \
    go build -buildvcs=false -trimpath \
    -o "${script_dir}/build/profile-relay" \
    ./cmd/profile-relay
chmod 0755 "${script_dir}/build/profile-relay"
docker build --pull=false --tag "${image_name}" "${script_dir}"
