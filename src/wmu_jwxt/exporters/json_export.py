"""JSON 导出。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_json(data: dict[str, Any], path: Path) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
