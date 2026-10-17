"""课表持久化：按学年-学期存本地数据，默认读缓存，仅 --update 才重新拉取。

这样后续打开课表无需登录、无需网络请求，既快又不会因频繁登录触发 CAS 风控。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..parsers.schedule import parse_schedule

STORE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "schedules"


def _path(year: int, term: int) -> Path:
    return STORE_DIR / f"schedule_{year}-{term}.json"


def exists(year: int, term: int) -> bool:
    return _path(year, term).exists()


def load(year: int, term: int) -> dict | None:
    """读取已持久化的课表（parse_schedule 的产物），不存在返回 None。"""
    p = _path(year, term)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def save_from_payload(payload: dict, year: int, term: int) -> dict:
    """把教务系统原始返回解析后存盘，返回解析后的课表。"""
    schedule = parse_schedule(payload, year, term)
    save(schedule)
    return schedule


def save(schedule: dict) -> Path:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    year, term = schedule["year"], schedule["term"]
    p = _path(year, term)
    p.write_text(
        json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return p


def delete(year: int, term: int) -> bool:
    """删除某学期课表数据。存在并删除返回 True，不存在返回 False。"""
    p = _path(year, term)
    if not p.exists():
        return False
    p.unlink()
    return True


def meta_str(year: int, term: int) -> str:
    """缓存的可读描述（存在/不存在 + 保存时间）。"""
    p = _path(year, term)
    if not p.exists():
        return "无本地数据"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return "本地数据损坏"
    age_min = (time.time() - p.stat().st_mtime) / 60
    return (
        f"{data.get('count', 0)} 门课，"
        f"{age_min:.0f} 分钟前保存（文件 {p.name}）"
    )


def list_cached() -> list[tuple[int, int]]:
    if not STORE_DIR.exists():
        return []
    out = []
    for p in STORE_DIR.glob("schedule_*.json"):
        stem = p.stem.replace("schedule_", "")
        try:
            y, t = stem.split("-")
            out.append((int(y), int(t)))
        except ValueError:
            continue
    return sorted(out)
