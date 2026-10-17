"""节次 ↔ 时间映射，以及教学周计算。

节次时间来自温州医科大学官方校历（2026-2027 学年第一学期）的两张表：
  - 茶山校区：表1（1-6 节上午、7 节中午、8-11 下午、12-15 晚上）
  - 滨海校区：表2（1-6 节上午、7-13 下午、14-15 晚上）
同一门课在哪个校区上课，就取哪张表——课表数据里有 xqmc（校区）字段。

校历要点（2026-2027 学年第一学期）：
  - 第一周周一 = 2026-09-07（老生 9/7 上课，新生 9/22 正式上课）
  - 9/25-27 中秋放假；10/1-7 国庆放假，但 10/6(周二)、10/10(周六) 要上课
  - 学期含 2027 年 1 月上旬

教学周计算以 .env 的 term_start（第一周周一）为基准，每 7 天进一周。
「每周一检测一次」通过 .cache/week.json 实现：记录
{term_key, week, detected_on(周一日期)}，同一天重复打开不重新算，
跨到下个周一才刷新。
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

# 茶山校区（校历「教学作息时间表1」）
CAMPUS_CHASHAN = {
    1: ("08:00", "08:40"),
    2: ("08:45", "09:25"),
    3: ("09:40", "10:20"),
    4: ("10:25", "11:05"),
    5: ("11:10", "11:50"),
    6: ("11:55", "12:35"),
    7: ("12:40", "13:20"),
    8: ("13:30", "14:10"),
    9: ("14:15", "14:55"),
    10: ("15:40", "16:20"),
    11: ("16:25", "17:05"),
    12: ("18:20", "19:00"),
    13: ("19:05", "19:45"),
    14: ("20:10", "20:50"),
    15: ("19:05", "19:45"),
}

# 滨海校区（校历「教学作息时间表2」）
CAMPUS_BINHAI = {
    1: ("08:30", "09:10"),
    2: ("09:15", "09:55"),
    3: ("10:10", "10:50"),
    4: ("10:55", "11:35"),
    5: ("11:40", "12:20"),
    6: ("12:25", "13:05"),
    7: ("13:05", "13:45"),
    8: ("13:30", "14:10"),
    9: ("14:15", "14:55"),
    10: ("15:00", "15:40"),
    11: ("15:45", "16:25"),
    12: ("16:30", "17:10"),
    13: ("17:15", "17:55"),
    14: ("18:00", "19:00"),
    15: ("19:05", "19:45"),
}

# 默认表：茶山（多数课程）；按 xqmc 匹配另一张
DEFAULT_CAMPUS = CAMPUS_CHASHAN

WEEK_CACHE = Path(__file__).resolve().parents[3] / ".cache" / "week.json"

# 校历里的特殊安排（2026-2027 学年第一学期）
# 键为 ISO 日期，值为说明；这些日期的课程是否停课由学校通知决定，
# 这里只做记录，界面不据此自动删课。
CALENDAR_NOTES = {
    "2026-09-25": "中秋节放假",
    "2026-09-26": "中秋节放假（补10月6日周二课程）",
    "2026-09-27": "中秋节放假（补10月10日周一课程）",
    "2026-10-01": "国庆节放假",
    "2026-10-06": "上课（补9月26日周六课程）",
    "2026-10-07": "国庆节放假",
    "2027-01-01": "元旦放假",
}


def table_for_campus(campus: str | None) -> dict[int, tuple[str, str]]:
    """按校区名取节次表。校名字段含「滨海」用表2，其余用茶山表1。"""
    if campus and "滨海" in campus:
        return CAMPUS_BINHAI
    return DEFAULT_CAMPUS


def parse_custom_times(text: str | None) -> dict[int, tuple[str, str]] | None:
    """.env 的 section_times 覆盖茶山表；格式 1:08:00-08:40,2:08:45-09:25,..."""
    if not text:
        return None
    times: dict[int, tuple[str, str]] = {}
    for part in text.split(","):
        part = part.strip()
        if ":" not in part or "-" not in part:
            continue
        idx, rest = part.split(":", 1)
        start, end = rest.split("-", 1)
        try:
            times[int(idx)] = (start.strip(), end.strip())
        except ValueError:
            continue
    return times or None


def section_time_text(
    jc: str,
    campus: str | None = None,
    custom: dict[int, tuple[str, str]] | None = None,
) -> str:
    """"3-5节" → "09:40-11:05"（按校区取表）；无节次返回空串。"""
    if not jc:
        return ""
    times = custom or table_for_campus(campus)
    s = jc.replace("节", "").strip()
    parts = s.split("-")
    try:
        start_idx = int(parts[0])
        end_idx = int(parts[1]) if len(parts) > 1 else start_idx
    except ValueError:
        return ""
    if start_idx not in times or end_idx not in times:
        return ""
    return f"{times[start_idx][0]}-{times[end_idx][1]}"


def term_start_date(year: int, term: int, override: str | None = None) -> dt.date:
    """学期第 1 周的周一。

    override 为 .env 的 term_start（ISO 日期，如 2026-09-07），优先。
    无 override 时按校历惯例：秋学期取 9 月第一个周一。
    """
    if override:
        try:
            d = dt.date.fromisoformat(override.strip())
            return d - dt.timedelta(days=d.weekday())  # 归到当周周一
        except ValueError:
            pass
    if term == 1:
        d = dt.date(year, 9, 1)
    elif term == 2:
        d = dt.date(year, 3, 1)
    else:
        d = dt.date(year, 7, 1)
    return d - dt.timedelta(days=d.weekday())


def current_week(
    today: dt.date | None = None,
    start: dt.date | None = None,
    total_weeks: int = 22,
) -> int:
    """今天是第几周。开学前返回 1，学期结束后钳位到 total_weeks。"""
    today = today or dt.date.today()
    if start is None:
        return 1
    delta = (today - start).days
    if delta < 0:
        return 1
    return max(1, min(delta // 7 + 1, total_weeks))


def load_week_cache() -> dict | None:
    if not WEEK_CACHE.exists():
        return None
    try:
        return json.loads(WEEK_CACHE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def save_week_cache(term_key: str, week: int, detected_on: str) -> None:
    WEEK_CACHE.parent.mkdir(parents=True, exist_ok=True)
    WEEK_CACHE.write_text(
        json.dumps({"term_key": term_key, "week": week, "detected_on": detected_on}),
        encoding="utf-8",
    )


def resolve_week(start: dt.date, term_key: str, total_weeks: int = 22) -> dict:
    """决定界面应跳到第几周。

    规则：
    - 缓存 term_key 匹配且 detected_on 是本周一 → 直接用缓存（周一不重复检测）
    - 否则重算当前周并写缓存
    """
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    monday_str = monday.isoformat()

    cached = load_week_cache()
    if (
        cached
        and cached.get("term_key") == term_key
        and cached.get("detected_on") == monday_str
    ):
        return {"week": int(cached.get("week", 1)), "refreshed": False}

    week = current_week(today, start, total_weeks)
    save_week_cache(term_key, week, monday_str)
    return {"week": week, "refreshed": True}
