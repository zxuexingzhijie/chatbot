#!/usr/bin/env bash
# Generate Homebrew resource blocks with real sha256 values.
# Requires: pip, poet (pip install homebrew-pypi-poet)
#
# Usage:
#   1. pip install homebrew-pypi-poet
#   2. pip install tavern-game[openai]   # or install from local
#   3. poet tavern-game
#
# Then paste the output into Formula/tavern-game.rb replacing the
# PLACEHOLDER resource blocks.
#
# To get the source tarball sha256:
#   curl -sL https://github.com/zxuexingzhijie/chatbot/archive/refs/tags/v0.1.0.tar.gz | shasum -a 256

set -euo pipefail

echo "Step 1: Ensure poet is installed"
pip install homebrew-pypi-poet 2>/dev/null

echo ""
echo "Step 2: Generate resource blocks"
echo "   (make sure tavern-game[openai] is installed in current env)"
echo ""
poet tavern-game 2>/dev/null || echo "tavern-game not found on PyPI yet. Install locally first: pip install -e '.[openai]' && poet tavern"
