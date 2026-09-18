"""Phase 39 runner: delegates to the canonical explain/attention_viz module."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))

from explain.attention_viz import main


if __name__ == "__main__":
    raise SystemExit(main())
