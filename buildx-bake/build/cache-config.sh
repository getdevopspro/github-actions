#!/usr/bin/env bash
set -euo pipefail

# Resolve only Docker's platform variables; never evaluate caller-supplied shell.
IFS=/ read -r cache_os cache_arch cache_variant <<< "$BUILD_PLATFORM"
CACHE_MAP=${CACHE_MAP//\$\{TARGETOS\}/$cache_os}
CACHE_MAP=${CACHE_MAP//\$\{TARGETARCH\}/$cache_arch}
CACHE_MAP=${CACHE_MAP//\$\{TARGETVARIANT\}/$cache_variant}
cache_map=''
if [[ -n "$CACHE_MAP" ]]; then
  cache_map=$(jq -ceS '
    if type == "object" and all(keys[]; test("^cache-mount/[a-zA-Z0-9][a-zA-Z0-9_.-]*$"))
    then . else error("cache-map must be an object with cache-mount/<name> archive paths") end
    | if any(.. | strings; contains("$"))
      then error("cache-map must use resolved paths and IDs; only platform variables are expanded")
      else . end
  ' <<< "$CACHE_MAP")
fi
# Keep configuration/platform identity stable while each run saves a new archive.
cache_hash=$(printf '%s\n' "$BUILD_FILES_HASH" "$BAKE_TARGET" "$cache_map" | sha256sum)
cache_hash=${cache_hash%% *}
{
  printf 'cache-map=%s\n' "$cache_map"
  printf 'prefix=cache-mount-v2-%s-%s-%s-\n' "$CACHE_SCOPE" "${BUILD_PLATFORM//\//-}" "$cache_hash"
} >> "$GITHUB_OUTPUT"
