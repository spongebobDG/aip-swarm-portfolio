#!/usr/bin/env bash
# sros2_init.sh — one-time SROS2 keystore setup for the AIP fleet central PC.
#
# Run this script once per deployment (or when rotating certificates).
# The generated keystore is gitignored. Back it up securely.
#
# Prerequisites:
#   source /opt/ros/humble/setup.bash
#   source ~/aip_swarm_ws/install/setup.bash
#
# Usage:
#   cd ~/aip_swarm_ws
#   bash scripts/sros2_init.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_ROOT="$(dirname "$SCRIPT_DIR")"
KEYSTORE="$WS_ROOT/config/security/keystore"
POLICY="$WS_ROOT/config/security/sros2_policy.xml"

# Sanity checks
if ! command -v ros2 &>/dev/null; then
    echo "ERROR: ros2 not found. Run: source /opt/ros/humble/setup.bash" >&2
    exit 1
fi
if [[ ! -f "$POLICY" ]]; then
    echo "ERROR: Policy file not found: $POLICY" >&2
    exit 1
fi

echo "=== AIP Fleet SROS2 keystore initialisation ==="
echo "Keystore path : $KEYSTORE"
echo "Policy file   : $POLICY"
echo ""

# -- 1. Create CA and keystore directory structure -------------------------
if [[ -d "$KEYSTORE" ]]; then
    echo "WARNING: Keystore already exists at $KEYSTORE"
    read -r -p "Re-initialise (this will REVOKE all existing certs)? [y/N] " confirm
    [[ "${confirm,,}" == "y" ]] || { echo "Aborted."; exit 0; }
    rm -rf "$KEYSTORE"
fi

echo "[1/3] Creating keystore CA..."
ros2 security create_keystore "$KEYSTORE"

# -- 2. Generate per-node keys ---------------------------------------------
echo "[2/3] Generating node keys..."
ENCLAVE_PATHS=(
    /aip_fleet_supervisor
    /aip_fleet_watchdog
    /foxglove_bridge
    /coordinator_aip2
    /coordinator_aip3
)

for ep in "${ENCLAVE_PATHS[@]}"; do
    echo "  enclave: $ep"
    ros2 security create_enclave "$KEYSTORE" "$ep"
done

# -- 3. Generate permissions from policy XML --------------------------------
echo "[3/3] Generating permissions..."
for ep in "${ENCLAVE_PATHS[@]}"; do
    echo "  permission: $ep"
    ros2 security create_permission "$KEYSTORE" "$ep" "$POLICY"
done

echo ""
echo "=== Done. Keystore at: $KEYSTORE ==="
echo ""
echo "To enable SROS2, launch with:"
echo "  ros2 launch aip_fleet_bringup central.launch.py with_security:=true"
echo ""
echo "IMPORTANT: Back up $KEYSTORE securely. Do NOT commit it to git."
