"""配置与凭据加载：从 .env 读取，全程不回显真实值。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"

BASE_URL = "https://jwxt.wmu.edu.cn"
JWGLXT = f"{BASE_URL}/jwglxt"


@dataclass
class Config:
    account: str = ""
    password: str = ""
    base_url: str = BASE_URL
    timeout: int = 10
    request_interval: float = 1.0
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    extra: dict = field(default_factory=dict)

    @property
    def jwglxt(self) -> str:
        return f"{self.base_url.rstrip('/')}/jwglxt"


_ENV_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def _parse_env_text(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = _ENV_LINE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def load_env(path: Path | None = None) -> dict:
    path = path or ENV_PATH
    if not path.exists():
        return {}
    return _parse_env_text(path.read_text(encoding="utf-8"))


def load_config(path: Path | None = None) -> Config:
    env = load_env(path)
    cfg = Config()
    cfg.account = env.get("account", "") or os.environ.get("WMU_ACCOUNT", "")
    cfg.password = env.get("password", "") or os.environ.get("WMU_PASSWORD", "")
    cfg.base_url = env.get("base_url", cfg.base_url)
    if "timeout" in env:
        cfg.timeout = int(env["timeout"])
    if "request_interval" in env:
        cfg.request_interval = float(env["request_interval"])
    cfg.extra = {k: v for k, v in env.items() if k not in {"account", "password", "base_url", "timeout", "request_interval"}}
    return cfg


def mask(value: str, keep: int = 1) -> str:
    """脱敏：只保留首尾各 keep 个字符。"""
    if not value:
        return "<empty>"
    if len(value) <= keep * 2:
        return value[0] + "*" * (len(value) - 1)
    return value[:keep] + "*" * (len(value) - keep * 2) + value[-keep:]
