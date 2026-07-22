#!/usr/bin/env bash
# Export the AIP swarm workspace to a remote Ubuntu host so a new
# Claude Code agent can pick up work there.
#
# Usage (from Git Bash / WSL on Windows, or from Linux):
#   ./scripts/export_to_ubuntu.sh aip@192.168.0.9
#   ./scripts/export_to_ubuntu.sh aip@192.168.0.9 ~/aip_swarm_ws
#
# What it does:
#   1. rsync the workspace over SSH, excluding build artifacts and secrets
#   2. (optional) hand off a tarball for offline transfer if SSH unavailable
#
# What the agent on the Ubuntu side needs to read first:
#   ~/aip_swarm_ws/CLAUDE.md
#   ~/aip_swarm_ws/docs/HANDOFF.md

set -euo pipefail

REMOTE="${1:-}"
DEST="${2:-~/aip_swarm_ws}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Windows path fix-up: cwrsync (cygwin-based rsync) interprets the MSYS
# `/c/...` path as literal, converts it back to `C:\...`, and then the
# embedded colon makes rsync think the source is remote — producing the
# confusing "source and destination cannot both be remote" error.
# Rewriting to the canonical `/cygdrive/c/...` form sidesteps this.
case "$WS_ROOT" in
    /[a-zA-Z]/*)
        drive="${WS_ROOT:1:1}"
        rest="${WS_ROOT:2}"
        WS_ROOT="/cygdrive/${drive}${rest}"
        ;;
esac

EXCLUDES=(
    --exclude '.pio/'
    --exclude 'build/'
    --exclude 'install/'
    --exclude 'log/'
    --exclude 'node_modules/'
    --exclude 'dist/'
    --exclude '__pycache__/'
    --exclude '*.pyc'
    --exclude '.vscode/'
    --exclude '.idea/'
    # Secrets — never transfer
    --exclude 'secrets.ini'
    --exclude '.env'
    --exclude 'config/security/'
    --exclude '*.pem'
    --exclude '*.key'
    --exclude '*.crt'
)

if [ -z "$REMOTE" ]; then
    cat <<USAGE
Usage: $0 <user@host> [remote_path]

Examples:
  $0 aip@192.168.0.9
  $0 aip@192.168.0.9 /home/aip/aip_swarm_ws

Offline (tarball) fallback:
  tar czf /tmp/aip_swarm_ws.tgz \\
      --exclude='.pio' --exclude='build' --exclude='install' --exclude='log' \\
      --exclude='node_modules' --exclude='__pycache__' \\
      --exclude='secrets.ini' --exclude='.env' --exclude='config/security' \\
      -C "$(dirname "$WS_ROOT")" "$(basename "$WS_ROOT")"

  # then on the Ubuntu side:
  tar xzf aip_swarm_ws.tgz -C ~/
USAGE
    exit 1
fi

echo "[export] syncing $WS_ROOT → $REMOTE:$DEST"

if command -v rsync >/dev/null 2>&1; then
    rsync -avz --delete "${EXCLUDES[@]}" "$WS_ROOT/" "$REMOTE:$DEST/"
else
    # Fallback for Git Bash on Windows (no rsync). Streams a tar archive
    # over SSH so nothing touches a temporary file. Excludes are rewritten
    # into tar's --exclude form. `--delete` is not supported here — the
    # remote directory is overwritten in-place but stale files are NOT
    # removed. Re-sync manually or install rsync if that matters.
    echo "[export] rsync not found — falling back to tar|ssh (no --delete semantics)"
    TAR_EXCLUDES=()
    for ex in "${EXCLUDES[@]}"; do
        if [ "$ex" != "--exclude" ]; then
            TAR_EXCLUDES+=(--exclude="$ex")
        fi
    done
    tar czf - "${TAR_EXCLUDES[@]}" \
        -C "$(dirname "$WS_ROOT")" "$(basename "$WS_ROOT")" \
      | ssh "$REMOTE" "mkdir -p $DEST && tar xzf - --strip-components=1 -C $DEST"
fi

cat <<NEXT

[export] Done.

Next steps on $REMOTE:
  1. ssh $REMOTE
  2. cd $DEST
  3. Read CLAUDE.md (agent instructions)
  4. Read docs/HANDOFF.md (project handoff)
  5. cp docker/central/.env.example docker/central/.env  # fill real creds
  6. Smoke test:
       docker compose -f docker/sim/docker-compose.yml up --build
     or follow docs/SETUP_UBUNTU.md for full production stack.
NEXT
