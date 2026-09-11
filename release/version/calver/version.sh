#!/usr/bin/env bash
set -euo pipefail

if [[ "${VERSION_TAG}" != true && "${VERSION_TAG}" != false ]]; then
  echo '::error::version-tag must be true or false' >&2
  exit 1
fi

# Match usage-syncer/justfile's version and next-version recipes: use the
# latest release tag, increment within its UTC month, otherwise start at zero.
utc_year_month="$(date -u '+%Y %m')"
read -r year month <<< "${utc_year_month}"
month="$((10#${month}))"

# A failed listing must not be treated as an empty release history.
tags="$(git tag --list)"
latest_version="$(
  while IFS= read -r tag; do
    if [[ "${tag}" == "${VERSION_TAG_PREFIX}"[0-9]* ]]; then
      printf '%s\n' "${tag#"${VERSION_TAG_PREFIX}"}"
    fi
  done <<< "${tags}" \
    | sort -V \
    | tail -n 1
)"

previous_version=0.0.0
if [[ -n "${latest_version}" ]]; then
  previous_version="${VERSION_TAG_PREFIX}${latest_version}"
fi

if [[ -n "${latest_version}" && "${latest_version%.*}" == "${year}.${month}" ]]; then
  patch="${latest_version##*.}"
  if [[ ! "${patch}" =~ ^[0-9]+$ ]]; then
    echo '::error::The latest release tag must end with a numeric patch' >&2
    exit 1
  fi
  patch=$((10#${patch} + 1))
else
  patch=0
fi

version="${VERSION_OUTPUT_FORMAT//\{\{.Major\}\}/${year}}"
version="${version//\{\{.Minor\}\}/${month}}"
version="${version//\{\{.Patch\}\}/${patch}}"
if [[ -z "${version}" || "${version}" == *'{{'* || "${version}" == *'}}'* || "${version}" == *$'\n'* || "${version}" == *$'\r'* ]]; then
  echo '::error::version-output-format must be a single nonempty line using only {{.Major}}, {{.Minor}}, and {{.Patch}} template fields' >&2
  exit 1
fi

if [[ "${VERSION_TAG}" == true ]]; then
  git tag -- "${VERSION_TAG_PREFIX}${version}"
fi

{
  printf 'version=%s\n' "${version}"
  printf 'previous-version=%s\n' "${previous_version}"
} >> "${GITHUB_OUTPUT}"
