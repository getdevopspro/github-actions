#!/usr/bin/env bash
set -euo pipefail

normalize_platform() {
  local platform_os platform_arch platform_variant
  IFS=/ read -r platform_os platform_arch platform_variant <<< "$1"
  case "$platform_arch" in
    x86_64|x86-64) platform_arch=amd64 ;;
    aarch64) platform_arch=arm64 ;;
  esac
  case "$platform_arch/$platform_variant" in
    amd64/v1|arm64/v8|arm64/8|arm64/v8.0) platform_variant='' ;;
  esac
  printf '%s/%s%s' "$platform_os" "$platform_arch" "${platform_variant:+/$platform_variant}"
}

case "$QEMU_MODE" in
  true|false) enabled=$QEMU_MODE ;;
  auto)
    if ! native_platform=$(docker info --format '{{.OSType}}/{{.Architecture}}'); then
      echo '::error::Unable to inspect the Docker daemon platform for automatic QEMU setup'
      exit 1
    fi
    enabled=true
    if [[ "$(normalize_platform "$native_platform")" == "$(normalize_platform "$BUILD_PLATFORM")" ]]; then
      enabled=false
    fi
    ;;
  *)
    echo '::error::qemu must be auto, true or false'
    exit 1
    ;;
esac
printf 'enabled=%s\n' "$enabled" >> "$GITHUB_OUTPUT"
printf 'QEMU setup enabled=%s (mode=%s, target=%s)\n' "$enabled" "$QEMU_MODE" "$BUILD_PLATFORM"
