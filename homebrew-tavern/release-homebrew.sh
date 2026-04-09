#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYPROJECT_PATH="${PROJECT_ROOT}/pyproject.toml"
UPDATE_FORMULA_SCRIPT="${SCRIPT_DIR}/update-formula-for-tag.sh"

REMOTE="origin"
BRANCH="main"
SOURCE_REPO="zxuexingzhijie/chatbot"
TAP_REPO_URL="https://github.com/zxuexingzhijie/homebrew-tavern.git"
TAP_PATH=""
NO_PUSH=false
SKIP_VERSION_BUMP=false
ALLOW_DIRTY=false

usage() {
  cat <<'EOF'
Usage:
  ./release-homebrew.sh <version> [options]

Arguments:
  version                     Release version, e.g. 1.0.0.3

Options:
  --remote <name>             Git remote for source repo (default: origin)
  --branch <name>             Git branch to push in source repo (default: main)
  --source-repo <owner/repo>  GitHub source repo for tarball (default: zxuexingzhijie/chatbot)
  --tap-repo-url <url>        Git URL for Homebrew tap repo
  --tap-path <path>           Existing local tap repo path; if omitted, clone to temp dir
  --no-push                   Do not push source repo or tap repo
  --skip-version-bump         Skip pyproject.toml version update/commit
  --allow-dirty               Allow running with uncommitted changes
  -h, --help                  Show help

Example:
  ./release-homebrew.sh 1.0.0.3
  ./release-homebrew.sh 1.0.0.3 --no-push
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

VERSION=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote)
      REMOTE="$2"
      shift 2
      ;;
    --branch)
      BRANCH="$2"
      shift 2
      ;;
    --source-repo)
      SOURCE_REPO="$2"
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
    --no-push)
      NO_PUSH=true
      shift
      ;;
    --skip-version-bump)
      SKIP_VERSION_BUMP=true
      shift
      ;;
    --allow-dirty)
      ALLOW_DIRTY=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "${VERSION}" ]]; then
        VERSION="$1"
      else
        echo "Unexpected argument: $1" >&2
        usage
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "${VERSION}" ]]; then
  echo "version is required" >&2
  usage
  exit 1
fi

if [[ ! -f "${PYPROJECT_PATH}" ]]; then
  echo "pyproject.toml not found: ${PYPROJECT_PATH}" >&2
  exit 1
fi

if [[ ! -x "${UPDATE_FORMULA_SCRIPT}" ]]; then
  echo "Required script is missing or not executable: ${UPDATE_FORMULA_SCRIPT}" >&2
  exit 1
fi

if [[ "${ALLOW_DIRTY}" == false ]]; then
  if [[ -n "$(git -C "${PROJECT_ROOT}" status --porcelain)" ]]; then
    echo "Source repo has uncommitted changes. Commit/stash first, or use --allow-dirty." >&2
    exit 1
  fi
fi

if git -C "${PROJECT_ROOT}" rev-parse --verify --quiet "refs/tags/${VERSION}" >/dev/null; then
  echo "Tag already exists locally: ${VERSION}" >&2
  exit 1
fi

current_version="$(awk -F'"' '/^version = "/ {print $2; exit}' "${PYPROJECT_PATH}")"
if [[ -z "${current_version}" ]]; then
  echo "Failed to read version from ${PYPROJECT_PATH}" >&2
  exit 1
fi

echo "Release version: ${VERSION}"
echo "Current version: ${current_version}"

if [[ "${SKIP_VERSION_BUMP}" == false ]]; then
  tmp_file="$(mktemp)"
  trap 'rm -f "${tmp_file}"' EXIT

  if ! awk -v new_version="${VERSION}" '
BEGIN { updated=0 }
{
  if (!updated && $0 ~ /^version = "/) {
    print "version = \"" new_version "\""
    updated=1
    next
  }
  print
}
END {
  if (updated != 1) {
    exit 42
  }
}
' "${PYPROJECT_PATH}" > "${tmp_file}"; then
    echo "Failed to update version in ${PYPROJECT_PATH}" >&2
    exit 1
  fi

  mv "${tmp_file}" "${PYPROJECT_PATH}"

  git -C "${PROJECT_ROOT}" add pyproject.toml
  if git -C "${PROJECT_ROOT}" diff --cached --quiet; then
    echo "No version change detected in pyproject.toml"
  else
    git -C "${PROJECT_ROOT}" commit -m "chore(release): bump version to ${VERSION}"
  fi
else
  echo "Skipping pyproject.toml version update (--skip-version-bump)"
fi

git -C "${PROJECT_ROOT}" tag "${VERSION}"

echo "Created tag: ${VERSION}"

if [[ "${NO_PUSH}" == false ]]; then
  git -C "${PROJECT_ROOT}" push "${REMOTE}" "${BRANCH}"
  git -C "${PROJECT_ROOT}" push "${REMOTE}" "${VERSION}"
  echo "Pushed source repo branch and tag"
else
  echo "Skip pushing source repo (--no-push)"
fi

tmp_tap_dir=""
cleanup() {
  if [[ -n "${tmp_tap_dir}" && -d "${tmp_tap_dir}" ]]; then
    rm -rf "${tmp_tap_dir}"
  fi
}
trap cleanup EXIT

if [[ -z "${TAP_PATH}" ]]; then
  tmp_tap_dir="$(mktemp -d)"
  TAP_PATH="${tmp_tap_dir}/homebrew-tavern"
  git clone "${TAP_REPO_URL}" "${TAP_PATH}" >/dev/null
else
  if [[ ! -d "${TAP_PATH}/.git" ]]; then
    echo "Invalid tap path (not a git repo): ${TAP_PATH}" >&2
    exit 1
  fi
  git -C "${TAP_PATH}" pull --ff-only
fi

if [[ "${ALLOW_DIRTY}" == false ]]; then
  if [[ -n "$(git -C "${TAP_PATH}" status --porcelain)" ]]; then
    echo "Tap repo has uncommitted changes: ${TAP_PATH}" >&2
    exit 1
  fi
fi

"${UPDATE_FORMULA_SCRIPT}" "${VERSION}" --repo "${SOURCE_REPO}" --formula "${TAP_PATH}/Formula/tavern-game.rb"

git -C "${TAP_PATH}" add Formula/tavern-game.rb
if git -C "${TAP_PATH}" diff --cached --quiet; then
  echo "No formula changes detected."
else
  git -C "${TAP_PATH}" commit -m "chore(homebrew): bump tavern-game to ${VERSION}"

  if [[ "${NO_PUSH}" == false ]]; then
    git -C "${TAP_PATH}" push
    echo "Pushed tap repo formula update"
  else
    echo "Skip pushing tap repo (--no-push)"
  fi
fi

echo "Release workflow completed successfully."
