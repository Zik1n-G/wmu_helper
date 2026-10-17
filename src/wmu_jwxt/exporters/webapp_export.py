"""导出 webapp 用的周视图数据（schedule-data.json）。

界面按周次展示课程、点卡片看详情，都依赖 build_week_view() 的产物。
同时支持从 .cache 里的课表 JSON 反构（读缓存导出时用）。
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from ..core import section_time
from ..parsers.schedule import build_week_view

WEBAPP_DIR = Path(__file__).resolve().parents[3] / "webapp"
DATA_PATH = WEBAPP_DIR / "schedule-data.json"


def _today_info(start: dt.date | None) -> dict:
    """今天在学期里的位置：周几、第几周、是否本周有课。

    界面靠这个把「今天」高亮、把周数标签定位到当日课程。
    """
    today = dt.date.today()
    info = {
        "today_iso": today.isoformat(),
        "today_weekday": today.weekday() + 1,  # 1=周一
        "today_week": 0,                      # 0 = 不在教学周范围内
        "in_term": False,
    }
    if start:
        delta = (today - start).days
        if delta >= 0:
            week = delta // 7 + 1
            info["today_week"] = week
            info["in_term"] = True
    return info


def export_webapp_data(schedule: dict, path: Path | None = None,
                       current_week: int = 1,
                       term_start: str | None = None) -> Path:
    """schedule（parse_schedule 产物）→ webapp/schedule-data.json。"""
    view = build_week_view(schedule, current_week, term_start)

    start = None
    if term_start:
        try:
            start = dt.date.fromisoformat(term_start)
            start = start - dt.timedelta(days=start.weekday())
        except ValueError:
            start = None
    view["today"] = _today_info(start)
    # 节次时间表（当日页纵轴直接用，不再从课程反查）
    view["section_tables"] = {
        "default": {str(k): v[0] for k, v in section_time.CAMPUS_CHASHAN.items()},
        "binhai": {str(k): v[0] for k, v in section_time.CAMPUS_BINHAI.items()},
    }

    return write_view(view, path)


def write_view(view: dict, path: Path | None = None) -> Path:
    target = path or DATA_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(view, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def export_from_cached(year: int, term: int, path: Path | None = None) -> Path | None:
    """从 .cache 的课表 JSON 反构周视图（键已存在则直接重组）。"""
    from .schedule_store import load

    schedule = load(year, term)
    if not schedule:
        return None
    # .cache 里存的是 parse_schedule 产物，缺 weeks 字段时按需重建
    if "weeks" not in schedule and "by_weekday" in schedule:
        schedule = _rebuild_courses(schedule)
    return export_webapp_data(schedule, path)


def _rebuild_courses(schedule: dict) -> dict:
    """旧缓存只有 by_weekday（无 weeks 列表）时，用 by_weekday 重组 courses。"""
    courses: list[dict] = []
    for day_list in schedule.get("by_weekday", {}).values():
        courses.extend(day_list)
    return {**schedule, "courses": courses}
