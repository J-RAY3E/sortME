#!/usr/bin/env bash
# One-command orchestration for the LLM reading queue.
#
#   ./run.sh tabs.json all           serve model + full import + open Obsidian
#   ./run.sh tabs.json full          descriptions + relationships
#   ./run.sh tabs.json fast          fast preset
#   ./run.sh tabs.json deep          deep preset
#   ./run.sh tabs.json descriptions  only regenerate English descriptions
#   ./run.sh tabs.json relations     only rebuild the relationship graph
#   ./run.sh tabs.json serve         only start the local model
#   ./run.sh tabs.json open          only open the vault in Obsidian
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

TABS="${1:-tabs.json}"
MODE="${2:-all}"
CONFIG="${CONFIG:-$DIR/config.json}"
[ -f "$CONFIG" ] || CONFIG="$DIR/config.example.json"

VAULT="$(python3 - "$CONFIG" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("vault", ""))
except Exception:
    print("")
PY
)"

server_up() { curl -sf --max-time 2 http://127.0.0.1:8080/health >/dev/null 2>&1; }

ensure_server() {
  if server_up; then
    echo "→ local model already running"
    return
  fi
  echo "→ starting local model (ctx=${CTX:-8192})"
  CTX="${CTX:-8192}" NGL="${NGL:-0}" ./start-local-model.sh >/tmp/sortme-server.log 2>&1 &
  for _ in $(seq 1 90); do
    server_up && { echo "→ model ready"; return; }
    sleep 2
  done
  echo "✗ model did not become ready; see /tmp/sortme-server.log" >&2
  exit 1
}

do_import() {
  python3 tabs_to_obsidian.py import "$TABS" --config "$CONFIG" "$@"
}

case "$MODE" in
  serve)        ensure_server ;;
  descriptions) do_import --llm --descriptions-only ;;
  relations)    do_import --llm --relations-only ;;
  validate)     python3 tabs_to_obsidian.py validate --vault "$VAULT" --config "$CONFIG" ;;
  refresh-ux)   python3 tabs_to_obsidian.py refresh-ux --vault "$VAULT" ;;
  full)         do_import --llm ;;
  fast)         do_import --llm --preset fast ;;
  balanced)     do_import --llm --preset balanced ;;
  deep)         do_import --llm --preset deep ;;
  open)         [ -n "$VAULT" ] && obsidian "$VAULT" ;;
  all)          ensure_server; do_import --llm; [ -n "$VAULT" ] && obsidian "$VAULT" ;;
  *)
    echo "Unknown mode: $MODE" >&2
    echo "Modes: all | serve | full | fast | balanced | deep | descriptions | relations | validate | refresh-ux | open" >&2
    exit 1
    ;;
esac
