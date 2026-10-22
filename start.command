#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo '请先运行：python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt'
  exit 1
fi
mkdir -p logs
export HF_HOME="${HF_HOME:-$PWD/.cache/huggingface}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-$PWD/.cache/matplotlib}"
export PYTORCH_ENABLE_MPS_FALLBACK=1
echo "Kronos Web: http://127.0.0.1:${PORT:-7071}"
echo "日志：logs/webui.log；停止：Control+C"
exec .venv/bin/python -u run.py >> logs/webui.log 2>&1
