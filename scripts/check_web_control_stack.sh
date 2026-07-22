#!/usr/bin/env bash
set -euo pipefail

WEB_URL="${AIP_WEB_URL:-http://127.0.0.1:8080/}"
LOG_FILE="${AIP_CENTRAL_LOG:-/tmp/aip_central_main_sub.log}"

failures=0

ok() {
  printf '[OK] %s\n' "$1"
}

fail() {
  printf '[FAIL] %s\n' "$1"
  failures=$((failures + 1))
}

has_port() {
  local pattern="$1"
  ss -ltnup 2>/dev/null | grep -E "$pattern" >/dev/null
}

if has_port ':8080'; then
  ok 'dashboard tcp/8080 is listening'
else
  fail 'dashboard tcp/8080 is not listening'
fi

if has_port ':19051'; then
  ok 'UDP heartbeat adapter udp/19051 is listening'
else
  fail 'UDP heartbeat adapter udp/19051 is not listening'
fi

if has_port ':11811'; then
  ok 'FastDDS discovery server udp/11811 is listening'
else
  fail 'FastDDS discovery server udp/11811 is not listening'
fi

if has_port ':19050'; then
  if [[ "${AIP_ALLOW_DIRECT_UDP_OVERLAY:-0}" == "1" ]]; then
    ok 'dashboard direct UDP overlay udp/19050 is listening by explicit allowance'
  else
    fail 'dashboard direct UDP overlay udp/19050 is listening; expected disabled by default'
  fi
else
  ok 'dashboard direct UDP overlay udp/19050 is disabled'
fi

if curl -fsS --max-time 5 "$WEB_URL" >/dev/null; then
  ok "dashboard HTTP responds at $WEB_URL"
else
  fail "dashboard HTTP does not respond at $WEB_URL"
fi

if [[ -f "$LOG_FILE" ]]; then
  if grep -q 'UDP heartbeat adapter listening on .*19051' "$LOG_FILE"; then
    ok 'central log shows UDP heartbeat adapter startup'
  else
    fail 'central log does not show UDP heartbeat adapter startup'
  fi

  if grep -q 'UDP status overlay disabled' "$LOG_FILE"; then
    ok 'central log shows dashboard direct UDP overlay disabled'
  else
    fail 'central log does not show dashboard direct UDP overlay disabled'
  fi

  if grep -q 'AIP Dashboard server started' "$LOG_FILE"; then
    ok 'central log shows dashboard startup'
  else
    fail 'central log does not show dashboard startup'
  fi
else
  fail "central log file not found: $LOG_FILE"
fi

if [[ -f "$HOME/aip_maps/latest_fleet_map.yaml" && -f "$HOME/aip_maps/latest_fleet_map.pgm" ]]; then
  ok 'saved latest_fleet_map exists'
else
  fail 'saved latest_fleet_map files are missing'
fi

if (( failures > 0 )); then
  printf '\n%d check(s) failed.\n' "$failures"
  exit 1
fi

printf '\nAll web-control stack checks passed.\n'
