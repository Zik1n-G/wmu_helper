"""Cookie 缓存：把浏览器登录得到的 Cookie 存本地，复用期内免重复登录。

风控教训：CAS 对短时间内的重复登录有账号级风控（会要求短信验证），
所以必须缓存 Cookie、尽量少登录。缓存文件权限收紧，内容不进 git。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

CACHE_PATH = Path(__file__).resolve().parents[3] / ".cache" / "cookie.json"
# 正方会话一般数小时有效，取保守值
DEFAULT_TTL = 4 * 3600


def save_cookie(cookie: str, ttl: int = DEFAULT_TTL) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"cookie": cookie, "saved_at": time.time(), "ttl": ttl}
    CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(CACHE_PATH, 0o600)
    except OSError:
        pass  # Windows 上 chmod 语义有限，忽略


def load_cookie(ttl: int | None = None) -> str | None:
    """返回未过期的缓存 Cookie；不存在或过期返回 None。"""
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    age = time.time() - data.get("saved_at", 0)
    limit = ttl if ttl is not None else data.get("ttl", DEFAULT_TTL)
    if age > limit:
        return None
    cookie = data.get("cookie", "")
    return cookie or None


def cookie_age_str() -> str:
    if not CACHE_PATH.exists():
        return "无缓存"
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return "缓存损坏"
    age = time.time() - data.get("saved_at", 0)
    ttl = data.get("ttl", DEFAULT_TTL)
    if age > ttl:
        return f"已过期（{age/60:.0f} 分钟前保存，上限 {ttl/3600:.1f} 小时）"
    return f"{age/60:.0f} 分钟前保存，剩余有效约 {(ttl-age)/60:.0f} 分钟"


def clear_cookie() -> None:
    if CACHE_PATH.exists():
        CACHE_PATH.unlink()
