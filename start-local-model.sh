#!/usr/bin/env bash
# Arranca llama-server con tu GGUF local y expone un endpoint OpenAI-compatible.
# Uso:  ./start-local-model.sh
# Variables: MODEL, PORT, CTX, NGL (capas en GPU; 0 = solo CPU)
set -euo pipefail

MODEL="${MODEL:-/home/azawa/Models/qwen2.5-coder-7b-instruct-q4_k_m.gguf}"
PORT="${PORT:-8080}"
CTX="${CTX:-4096}"
NGL="${NGL:-0}"

if [ ! -f "$MODEL" ]; then
  echo "✗ No existe el modelo: $MODEL" >&2
  exit 1
fi

echo "→ Cargando $MODEL"
echo "→ Endpoint: http://127.0.0.1:$PORT/v1/chat/completions"
echo "→ Contexto: $CTX | GPU layers: $NGL"

exec llama-server \
  -m "$MODEL" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --ctx-size "$CTX" \
  --n-gpu-layers "$NGL" \
  --alias local-llm
