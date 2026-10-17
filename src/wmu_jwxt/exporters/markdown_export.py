"""Markdown 周课表导出。"""

from __future__ import annotations

from pathlib import Path

WEEKDAY_NAMES = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}


def _cell(courses: list[dict]) -> str:
    if not courses:
        return ""
    parts = []
    for c in courses:
        seg = f"**{c['title']}**"
        if c.get("place"):
            seg += f"<br>{c['place']}"
        if c.get("teacher"):
            seg += f"<br>{c['teacher']}"
        parts.append(seg)
    return "<br>---<br>".join(parts)


def export_markdown(schedule: dict, path: Path, term_label: str = "") -> Path:
    student = schedule["student"]
    by_weekday = schedule["by_weekday"]

    lines = [
        f"# {student.get('name') or ''} 的课表（{term_label or f"{schedule['year']} 学年 第 {schedule['term']} 学期"}）",
        "",
        f"- 学号：{student.get('sid', '')}",
        f"- 班级：{student.get('class_name', '')}",
        f"- 课程数：{schedule['count']}",
        "",
    ]

    for day in range(1, 8):
        courses = by_weekday.get(day, [])
        lines.append(f"## {WEEKDAY_NAMES[day]}（{len(courses)} 门）")
        lines.append("")
        if not courses:
            lines.append("无课")
            lines.append("")
            continue
        lines.append("| 节次 | 课程 | 地点 | 教师 | 周次 | 学分 |")
        lines.append("|---|---|---|---|---|---|")
        for c in courses:
            lines.append(
                f"| {c['sections']} | {c['title']} | {c.get('place') or '-'} "
                f"| {c.get('teacher') or '-'} | {c.get('weeks_raw') or '-'} | {c.get('credit') or '-'} |"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
