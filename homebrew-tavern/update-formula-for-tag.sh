#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORMULA_PATH="${SCRIPT_DIR}/Formula/tavern-game.rb"
REPO="zxuexingzhijie/chatbot"
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage:
  ./update-formula-for-tag.sh <tag> [--repo owner/repo] [--formula path] [--dry-run]

Examples:
  ./update-formula-for-tag.sh 1.0.0.2
  ./update-formula-for-tag.sh v1.0.0.2 --repo myname/chatbot
  ./update-formula-for-tag.sh 1.0.0.2 --dry-run
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

TAG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="$2"
      shift 2
      ;;
    --formula)
      FORMULA_PATH="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "${TAG}" ]]; then
        TAG="$1"
      else
        echo "Unexpected argument: $1" >&2
        usage
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "${TAG}" ]]; then
  echo "Tag is required." >&2
  usage
  exit 1
fi

if [[ ! -f "${FORMULA_PATH}" ]]; then
  echo "Formula file not found: ${FORMULA_PATH}" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required but not found." >&2
  exit 1
fi

clean_tag="${TAG#refs/tags/}"
TARBALL_URL="https://github.com/${REPO}/archive/refs/tags/${clean_tag}.tar.gz"

echo "Resolving sha256 for: ${TARBALL_URL}"
if command -v shasum >/dev/null 2>&1; then
  SHA256="$(curl -fsSL "${TARBALL_URL}" | shasum -a 256 | awk '{print $1}')"
elif command -v sha256sum >/dev/null 2>&1; then
  SHA256="$(curl -fsSL "${TARBALL_URL}" | sha256sum | awk '{print $1}')"
else
  echo "Either shasum or sha256sum is required but not found." >&2
  exit 1
fi

if [[ -z "${SHA256}" ]]; then
  echo "Failed to compute sha256 for ${TARBALL_URL}" >&2
  exit 1
fi

echo "Tag:    ${clean_tag}"
echo "SHA256: ${SHA256}"
echo "Formula: ${FORMULA_PATH}"

if [[ "${DRY_RUN}" == true ]]; then
  echo "Dry run mode: no file changes were made."
  exit 0
fi

tmp_file="$(mktemp)"
trap 'rm -f "${tmp_file}"' EXIT

if ! awk -v new_url="${TARBALL_URL}" -v new_sha="${SHA256}" '
BEGIN { url_count=0; sha_count=0 }
{
  if ($0 ~ /^[[:space:]]*url[[:space:]]+"/) {
    print "  url \"" new_url "\""
    url_count++
    next
  }

  if ($0 ~ /^[[:space:]]*sha256[[:space:]]+"/) {
    print "  sha256 \"" new_sha "\""
    sha_count++
    next
  }

  print
}
END {
  if (url_count != 1 || sha_count != 1) {
    exit 42
  }
}
' "${FORMULA_PATH}" > "${tmp_file}"; then
  echo "Failed to update formula. Ensure exactly one url and one sha256 field exist." >&2
  exit 1
fi

mv "${tmp_file}" "${FORMULA_PATH}"

echo "Updated ${FORMULA_PATH}"
echo "Next steps:"
echo "  1) git add ${FORMULA_PATH}"
echo "  2) git commit -m \"chore(homebrew): bump tavern-game to ${clean_tag}\""
echo "  3) git push"
