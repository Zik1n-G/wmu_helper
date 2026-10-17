"""课表数据解析：kbList -> 周次视图。"""

from __future__ import annotations

from typing import Any


# 校历最大节次数（茶山 15 节 / 滨海 15 节）。
# 超过它的「N-M节」不是节次，而是实践课的工位/时段编号（如电子工艺实践 9-16节）。
MAX_SECTION = 15


def parse_sections(jc: str) -> tuple[int, int]:
    """"3-5节" -> (3, 5)；单节 "3" -> (3, 3)。

    超出校历节次范围的（如实践课 "9-16节" 指工位号）返回 (0, 0)，
    交由调用方按无固定节次处理。
    """
    if not jc:
        return (0, 0)
    s = jc.replace("节", "").strip()
    if "-" in s:
        a, b = s.split("-", 1)
        try:
            lo, hi = int(a), int(b)
        except ValueError:
            return (0, 0)
        if not (1 <= lo <= MAX_SECTION and 1 <= hi <= MAX_SECTION):
            return (0, 0)
        return (lo, hi)
    try:
        v = int(s)
        return (v, v) if 1 <= v <= MAX_SECTION else (0, 0)
    except ValueError:
        return (0, 0)


def parse_weeks(zcd: str) -> list[int]:
    """解析教务系统的周次字段，返回显式周次列表。

    实测出现的格式（WMU 2026-10）：
      "1-16周"                      -> 1..16
      "3周,6周"                     -> [3, 6]
      "8-10周(双)"                  -> 双周：[8, 10]（8-10 里的双周）
      "12-14周(双)"                 -> [12, 14]
      "第7周" / "第8周"              -> [7] / [8]（形策等单周课）
      "1-2周,6-8周(双),13-14周"     -> 混合段
      "5周,8-10周(双),11-13周,15周" -> 混合段
    """
    if not zcd:
        return []
    text = str(zcd).strip().replace("第", "")
    weeks: list[int] = []

    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        # 单双周标记：(双) / (单) / 双 / 单
        odd_only = ("单" in part) and ("双" not in part)
        even_only = "双" in part
        part = part.replace("周", "").replace("(", "").replace(")", "")
        part = part.replace("双", "").replace("单", "").strip()
        if not part:
            continue

        if "-" in part:
            a, _, b = part.partition("-")
            try:
                lo, hi = int(a), int(b)
            except ValueError:
                continue
            if lo > hi:
                lo, hi = hi, lo
            seq = range(lo, hi + 1)
            if even_only:
                seq = [w for w in seq if w % 2 == 0]
            elif odd_only:
                seq = [w for w in seq if w % 2 == 1]
            weeks.extend(seq)
        else:
            try:
                weeks.append(int(part))
            except ValueError:
                continue

    return sorted(set(weeks))


def normalize_course(item: dict[str, Any]) -> dict[str, Any]:
    start, end = parse_sections(item.get("jc", ""))
    return {
        "course_id": item.get("kch_id") or item.get("kch", ""),
        "title": item.get("kcmc", ""),
        "teacher": item.get("xm", ""),
        "class_name": item.get("jxbmc", ""),
        "credit": item.get("xf", ""),
        "weekday": int(item.get("xqj") or 0),
        "sections": item.get("jc", ""),
        "section_start": start,
        "section_end": end,
        "weeks_raw": item.get("zcd", ""),
        "weeks": parse_weeks(item.get("zcd", "")),
        "evaluation_mode": item.get("khfsmc", ""),
        "campus": item.get("xqmc", ""),
        "place": item.get("cdmc", ""),
        "hours_composition": item.get("kcxszc", ""),
        "weekly_hours": item.get("zhxs", ""),
        "total_hours": item.get("zxs", ""),
        "teaching_class_id": item.get("jxb_id", ""),
    }


def normalize_elective(item: dict[str, Any]) -> dict[str, Any]:
    """sjkList（实践/通识选修课）→ 课程结构。

    这类课没有星期和节次（多为智慧树等网络平台），weekday=0。
    教师与平台信息在 qtkcgs 文本里（"课名◆教师(共N周)/周次/平台"）。
    """
    teacher = ""
    platform = ""
    detail = item.get("qtkcgs") or item.get("sjkcgs") or ""
    if "◆" in detail:
        seg = detail.split("◆", 1)[1]
        teacher = seg.split("(", 1)[0].strip()
        # "金伟琼(共11周)/3-13周/智慧树" → 平台取最后一段
        tail = detail.rsplit("/", 1)[-1].strip()
        if tail and "周" not in tail:
            platform = tail

    return {
        "course_id": "",
        "title": item.get("kcmc", ""),
        "teacher": teacher,
        "class_name": "",
        "credit": item.get("xf", ""),
        "weekday": 0,
        "sections": "",
        "section_start": 0,
        "section_end": 0,
        "weeks_raw": item.get("qsjsz", ""),
        "weeks": parse_weeks(item.get("qsjsz", "")),
        "evaluation_mode": "",
        "campus": item.get("xqmc", ""),
        # place 用平台名（智慧树等网络课无实体教室）
        "place": platform or (item.get("kklxdm") if item.get("kklxdm") == "10" else "") or "网络课程",
        "hours_composition": "",
        "weekly_hours": "",
        "total_hours": "",
        "teaching_class_id": "",
        "category": item.get("kclb", "通识选修课"),
        "is_elective": True,
        "note": detail,
    }


def parse_schedule(payload: dict[str, Any], year: int, term: int) -> dict[str, Any]:
    kb_list = payload.get("kbList") or []
    xsxx = payload.get("xsxx") or {}
    courses = [normalize_course(c) for c in kb_list]
    # sjkList：通识选修课/实践课，无固定上课时间
    electives = [normalize_elective(c) for c in (payload.get("sjkList") or [])]

    courses.sort(key=lambda c: (c["weekday"], c["section_start"]))

    by_weekday: dict[int, list[dict]] = {}
    for c in courses:
        by_weekday.setdefault(c["weekday"], []).append(c)

    return {
        "student": {
            "sid": xsxx.get("XH", ""),
            "name": xsxx.get("XM", ""),
            "class_name": xsxx.get("BJMC", ""),
        },
        "year": year,
        "term": term,
        "count": len(courses) + len(electives),
        "by_weekday": by_weekday,
        "courses": courses,
        "electives": electives,
    }


def build_week_view(
    schedule: dict[str, Any],
    current_week: int = 1,
    term_start: str | None = None,
) -> dict[str, Any]:
    """按周次展开：每周每天有哪些课。

    产物结构（直接给前端用）：
    {
      "total_weeks": 20,
      "current_week": 9,
      "week_dates": {"1": "09-07", ...},
      "week_months": {"1": 9, ...},
      "weeks": {"1": {"1": [course...], ..., "0": [选修课...]}}
    }
    weeks 里的 "0" 键是选修课（通识选修/网络课，无固定星期节次），
    按周次落在对应周。每门课附带 time_text（按校区取节次表）。
    """
    import datetime as dt

    from ..core.section_time import parse_custom_times, section_time_text

    custom = parse_custom_times(schedule.get("section_times"))

    total = 0
    for c in schedule["courses"]:
        if c["weeks"]:
            total = max(total, max(c["weeks"]))
        c["time_text"] = section_time_text(
            c.get("sections", ""), c.get("campus"), custom
        )
    for e in schedule.get("electives") or []:
        if e["weeks"]:
            total = max(total, max(e["weeks"]))

    weeks: dict[str, dict[str, list[dict]]] = {}
    for w in range(1, total + 1):
        # "0" 键专放选修课（无固定上课时间）
        weeks[str(w)] = {str(d): [] for d in range(0, 8)}

    for c in schedule["courses"]:
        for w in c["weeks"]:
            key = str(w)
            if key in weeks:
                weeks[key][str(c["weekday"])].append(c)

    # 选修课按周次落入（weekday=0）
    for e in schedule.get("electives") or []:
        for w in e["weeks"]:
            key = str(w)
            if key in weeks:
                weeks[key]["0"].append(e)

    # 第 N 周周一的日期（侧边栏按月份分组用）
    week_dates: dict[str, str] = {}
    week_months: dict[str, int] = {}
    start = None
    if term_start:
        try:
            start = dt.date.fromisoformat(term_start)
            start = start - dt.timedelta(days=start.weekday())
        except ValueError:
            start = None
    for w in range(1, total + 1):
        if start:
            monday = start + dt.timedelta(weeks=w - 1)
            week_dates[str(w)] = monday.strftime("%m-%d")
            week_months[str(w)] = monday.month
        else:
            week_dates[str(w)] = ""
            week_months[str(w)] = 0

    return {
        "student": schedule["student"],
        "year": schedule["year"],
        "term": schedule["term"],
        "count": schedule["count"],
        "total_weeks": total,
        "current_week": max(1, min(current_week, total or 1)),
        "week_dates": week_dates,
        "week_months": week_months,
        "weeks": weeks,
    }
