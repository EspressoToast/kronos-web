"""Local-only Web UI launcher; keeps upstream application unchanged."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(ROOT / ".cache/huggingface"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from webui.app import app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "7071")), debug=False, threaded=False)
