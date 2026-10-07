#!/usr/bin/env bash
set -euo pipefail
export npm_config_cache=/private/tmp/radar-npm-cache
export npm_config_loglevel=error
export PWTEST_DAEMON_SESSION_DIR=/private/tmp/radar-pw-daemon
exec bash /Users/joaomarcosramos/.codex/skills/playwright/scripts/playwright_cli.sh --session core-u1-5b "$@"
