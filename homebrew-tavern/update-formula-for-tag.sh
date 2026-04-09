#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORMULA_PATH="${SCRIPT_DIR}/Formula/tavern-game.rb"
REPO="zxuexingzhijie/chatbot"
DRY_RUN=false
PUSH=false
TAP_REPO_URL=""
TAP_PATH=""
BRANCH="main"
DEFAULT_TAP_REPO_URL="https://github.com/zxuexingzhijie/homebrew-tavern.git"
FORMULA_PATH_EXPLICIT=false
tmp_file=""
tmp_tap_dir=""

cleanup() {
  if [[ -n "${tmp_file}" && -f "${tmp_file}" ]]; then
    rm -f "${tmp_file}"
  fi

  if [[ -n "${tmp_tap_dir}" && -d "${tmp_tap_dir}" ]]; then
    rm -rf "${tmp_tap_dir}"
  fi
}
trap cleanup EXIT

usage() {
  cat <<'EOF'
Usage:
  ./update-formula-for-tag.sh <tag> [options]

Options:
  --repo <owner/repo>       Source repository for tarball URL
  --formula <path>          Formula file path to update
  --dry-run                 Print computed values without writing files
  --tap-repo-url <url>      Clone/update this tap repository
  --tap-path <path>         Use existing local tap repository path
  --push                    Commit and push Formula changes to tap repo
  --branch <name>           Branch to push in tap repo (default: main)

Examples:
  ./update-formula-for-tag.sh 1.0.0.2
  ./update-formula-for-tag.sh v1.0.0.2 --repo myname/chatbot
  ./update-formula-for-tag.sh 1.0.0.2 --dry-run
  ./update-formula-for-tag.sh 1.0.0.2 --push
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
      FORMULA_PATH_EXPLICIT=true
      shift 2
      ;;
    --tap-repo-url)
      TAP_REPO_URL="$2"
      shift 2
      ;;
    --tap-path)
      TAP_PATH="$2"
      shift 2
      ;;
    --push)
      PUSH=true
      shift
      ;;
    --branch)
      BRANCH="$2"
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

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required but not found." >&2
  exit 1
fi

if [[ -n "${TAP_PATH}" && ! -d "${TAP_PATH}/.git" ]]; then
  echo "Invalid tap path (not a git repo): ${TAP_PATH}" >&2
  exit 1
fi

needs_tap_repo=false
if [[ "${PUSH}" == true || -n "${TAP_REPO_URL}" || -n "${TAP_PATH}" ]]; then
  needs_tap_repo=true
fi

if [[ "${needs_tap_repo}" == true ]]; then
  if [[ -z "${TAP_REPO_URL}" ]]; then
    TAP_REPO_URL="${DEFAULT_TAP_REPO_URL}"
  fi

  if [[ -z "${TAP_PATH}" ]]; then
    tmp_tap_dir="$(mktemp -d)"
    TAP_PATH="${tmp_tap_dir}/homebrew-tavern"
    git clone "${TAP_REPO_URL}" "${TAP_PATH}" >/dev/null
  else
    git -C "${TAP_PATH}" pull --ff-only >/dev/null
  fi

  if [[ "${FORMULA_PATH_EXPLICIT}" == false ]]; then
    FORMULA_PATH="${TAP_PATH}/Formula/tavern-game.rb"
  fi

  if [[ "${PUSH}" == true && -n "$(git -C "${TAP_PATH}" status --porcelain)" ]]; then
    echo "Tap repo has uncommitted changes: ${TAP_PATH}" >&2
    exit 1
  fi
fi

if [[ ! -f "${FORMULA_PATH}" ]]; then
  echo "Formula file not found: ${FORMULA_PATH}" >&2
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
tmp_file=""

echo "Updated ${FORMULA_PATH}"

if [[ "${PUSH}" == true ]]; then
  if [[ -z "${TAP_PATH}" ]]; then
    echo "--push requires a tap repository context. Provide --tap-path or --tap-repo-url." >&2
    exit 1
  fi

  case "${FORMULA_PATH}" in
    "${TAP_PATH}"/*) ;;
    *)
      echo "Formula path must be inside tap repo when using --push: ${FORMULA_PATH}" >&2
      exit 1
      ;;
  esac

  relative_formula_path="${FORMULA_PATH#${TAP_PATH}/}"
  git -C "${TAP_PATH}" add "${relative_formula_path}"

  if git -C "${TAP_PATH}" diff --cached --quiet; then
    echo "No staged changes to commit in tap repo."
    exit 0
  fi

  git -C "${TAP_PATH}" commit -m "chore(homebrew): bump tavern-game to ${clean_tag}"
  git -C "${TAP_PATH}" push origin "${BRANCH}"
  echo "Committed and pushed tap update to ${TAP_REPO_URL} (${BRANCH})"
else
  echo "Next steps:"
  echo "  1) git add ${FORMULA_PATH}"
  echo "  2) git commit -m \"chore(homebrew): bump tavern-game to ${clean_tag}\""
  echo "  3) git push"
fi
