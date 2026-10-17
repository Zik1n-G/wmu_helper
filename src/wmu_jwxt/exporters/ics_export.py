"""ICS 日历导出：每门课按周次展开为重复事件。"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

WEEKDAY_ISO = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7}

from ..core.section_time import (
    parse_custom_times,
    section_time_text,
    table_for_campus,
    term_start_date,
)


def _fmt(dtobj: dt.datetime) -> str:
    return dtobj.strftime("%Y%m%dT%H%M%S")


def export_ics(
    schedule: dict,
    path: Path,
    section_times_text: str | None = None,
    term_start: dt.date | None = None,
) -> Path:
    custom = parse_custom_times(section_times_text)
    start_date = term_start or term_start_date(schedule["year"], schedule["term"])

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wmu-jwxt//timetable//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{schedule['student'].get('name', '')} 课表 {schedule['year']}-{schedule['term']}",
    ]

    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    for i, c in enumerate(schedule["courses"]):
        wd = WEEKDAY_ISO.get(c["weekday"])
        if not wd or not c["weeks"]:
            continue
        first_week = min(c["weeks"])
        last_week = max(c["weeks"])
        day = start_date + dt.timedelta(weeks=first_week - 1, days=wd - 1)

        # 按课程校区取节次表（茶山/滨海两套作息不同）
        times = custom or table_for_campus(c.get("campus"))
        s_range = times.get(c["section_start"], ("08:00", "08:45"))
        e_range = times.get(c["section_end"], ("08:00", "08:45"))
        sh, sm = map(int, s_range[0].split(":"))
        eh, em = map(int, e_range[1].split(":"))
        begin = dt.datetime.combine(day, dt.time(sh, sm))
        end = dt.datetime.combine(day, dt.time(eh, em))

        # 中间缺周（如 1-4周,6-17周）用 EXDATE 排除
        all_weeks = set(range(first_week, last_week + 1))
        missing = sorted(all_weeks - set(c["weeks"]))
        exdates = [
            (start_date + dt.timedelta(weeks=w - 1, days=wd - 1)).strftime("%Y%m%d")
            for w in missing
        ]

        desc = f"教师:{c.get('teacher') or '-'} | 周次:{c.get('weeks_raw') or '-'} | 学分:{c.get('credit') or '-'}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:wmu-{schedule['year']}-{schedule['term']}-{i}-{c['course_id']}@wmu-jwxt",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_fmt(begin)}",
            f"DTEND:{_fmt(end)}",
            f"RRULE:FREQ=WEEKLY;COUNT={last_week - first_week + 1}",
            f"SUMMARY:{c['title']} @ {c.get('place') or '-'}",
            f"DESCRIPTION:{desc}",
            f"LOCATION:{c.get('place') or ''}",
        ]
        if exdates:
            lines.append("EXDATE;VALUE=DATE:" + ",".join(exdates))
        lines += ["END:VEVENT"]

    lines.append("END:VCALENDAR")
    path.write_text("\r\n".join(lines), encoding="utf-8")
    return path
