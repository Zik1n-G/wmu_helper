#!/usr/bin/env python3
"""WMU 教务系统课表一键获取 CLI。

课表持久化策略：
    首次运行：登录 → 拉课表 → 存 .cache/schedules/
    后续运行：直接读本地数据（不登录、不发请求）
    想更新：  --update 才重新登录拉取

用法：
    python main.py --year 2026 --term 1              # 读本地，无则拉取
    python main.py --year 2026 --term 1 --update     # 强制重新拉取
    python main.py --grades --year 2026 --term 1     # 成绩（始终在线拉取）
    python main.py --exams --year 2026 --term 1      # 考试安排（始终在线）
    python main.py --list                            # 看本地有哪些课表
    python main.py --cookie-status                   # 会话缓存状态
    python main.py --logout                          # 清除登录会话
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wmu_jwxt import Client, JwxtError, load_config, mask  # noqa: E402
from wmu_jwxt.core import cookie_store, schedule_store, section_time  # noqa: E402
from wmu_jwxt.core.login_ui import run_login_ui  # noqa: E402
from wmu_jwxt.exporters.ics_export import export_ics  # noqa: E402
from wmu_jwxt.exporters.json_export import export_json  # noqa: E402
from wmu_jwxt.exporters.markdown_export import export_markdown  # noqa: E402
from wmu_jwxt.exporters.webapp_export import export_webapp_data  # noqa: E402
from wmu_jwxt.parsers.schedule import build_week_view  # noqa: E402

OUTPUT_DIR = PROJECT_ROOT / "output"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="WMU 教务系统课表一键获取")
    p.add_argument("--year", type=int, help="学年，如 2026（2026-2027 学年）")
    p.add_argument("--term", type=int, default=1, choices=[1, 2, 3], help="学期：1/2/3")
    p.add_argument("--grades", action="store_true", help="改为拉取成绩")
    p.add_argument("--exams", action="store_true", help="改为拉取考试安排")
    p.add_argument("--only", choices=["json", "md", "ics"], help="只导出指定格式（默认全部）")
    p.add_argument("--outdir", default=str(OUTPUT_DIR), help="输出目录")
    p.add_argument("--update", action="store_true", help="强制重新登录拉取课表")
    p.add_argument("--relogin", action="store_true", help="忽略会话缓存，重新登录")
    p.add_argument("--list", action="store_true", help="列出本地已存课表")
    p.add_argument("--delete", action="store_true", help="删除指定学年学期的本地课表数据")
    p.add_argument("--cookie-status", action="store_true", help="查看会话缓存状态")
    p.add_argument("--logout", action="store_true", help="清除登录会话")
    return p.parse_args(argv)


def ensure_session(cfg, force_relogin: bool = False) -> Client:
    """建立已登录会话：优先缓存 Cookie，失效则弹窗人工登录。"""
    client = Client(cfg)

    cookie = None if force_relogin else cookie_store.load_cookie()
    if cookie:
        print(f"[*] 使用登录缓存（{cookie_store.cookie_age_str()}）")
        client.login_with_cookie(cookie)
        if _session_alive(client):
            print("[+] 会话有效，免登录")
            return client
        print("[!] 会话已失效，需要重新登录")
        cookie_store.clear_cookie()

    result = run_login_ui(account=cfg.account)
    if not result.ok:
        print(f"[!] 登录失败: {result.error}", file=sys.stderr)
        raise SystemExit(1)

    cookie_store.save_cookie(result.cookie)
    client.login_with_cookie(result.cookie)
    print("[+] 登录成功，会话已缓存（约 4 小时免重复登录）")
    return client


def _session_alive(client: Client) -> bool:
    try:
        r = client._get("kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N2151")
        return "login_slogin" not in r.url and r.status_code == 200
    except Exception:
        return False


def get_schedule(cfg, year: int, term: int, update: bool, relogin: bool) -> dict:
    """读本地课表；无缓存或 --update 时才登录拉取。"""
    if not update:
        cached = schedule_store.load(year, term)
        if cached:
            print(f"[*] 使用本地课表（{schedule_store.meta_str(year, term)}）")
            if "weeks" not in cached and "by_weekday" in cached:
                cached = _rebuild_courses(cached)
            _sync_webapp(cached, cfg)
            return cached
        print("[*] 本地无课表数据，需要登录拉取")

    client = ensure_session(cfg, force_relogin=relogin)
    try:
        payload = client.get_schedule(year, term)
    except JwxtError as e:
        print(f"[!] 拉取失败（code={e.code}）：{e.msg}", file=sys.stderr)
        raise SystemExit(1)

    kb_list = payload.get("kbList") or []
    if not kb_list:
        print("[!] 课表为空：该学期可能无排课数据", file=sys.stderr)
        raise SystemExit(2)

    schedule = schedule_store.save_from_payload(payload, year, term)
    print(f"[+] 课表已拉取并保存（{schedule['count']} 门）")
    _sync_webapp(schedule, cfg)
    return schedule


def _rebuild_courses(schedule: dict) -> dict:
    """旧缓存只有 by_weekday（无 weeks 列表）时，用 by_weekday 重组 courses。"""
    courses: list[dict] = []
    for day_list in schedule.get("by_weekday", {}).values():
        courses.extend(day_list)
    return {**schedule, "courses": courses}


def _sync_webapp(schedule: dict, cfg=None) -> None:
    """拉取/读到课表后，同步一份给 webapp 界面（含当前教学周）。"""
    try:
        year, term = schedule["year"], schedule["term"]
        total = schedule.get("total_weeks") or _max_weeks(schedule)
        override = (cfg.extra.get("term_start") if cfg else None)
        start = section_time.term_start_date(year, term, override)
        wk = section_time.resolve_week(
            start, f"{year}-{term}", total
        )
        if wk["refreshed"]:
            print(f"[*] 本周为第 {wk['week']} 周（学期首周周一 {start.isoformat()}）")
        p = export_webapp_data(
            schedule, current_week=wk["week"], term_start=start.isoformat()
        )
        print(f"[+] 界面数据已更新：{p}")
    except Exception as e:  # noqa: BLE001 - 界面数据是附加产物，失败不阻断主流程
        print(f"[!] 界面数据同步失败（不影响课表导出）: {e}")


def _max_weeks(schedule: dict) -> int:
    weeks = [w for c in schedule.get("courses", []) for w in c.get("weeks", [])]
    return max(weeks) if weeks else 20


def export_all(schedule: dict, outdir: Path, only: str | None, section_times: str | None) -> None:
    tag = f"{schedule['year']}-{schedule['term']}"
    label = f"{schedule['year']} 学年 第 {schedule['term']} 学期"
    made = []
    if only in (None, "json"):
        made.append(export_json(schedule, outdir / f"schedule_{tag}.json"))
    if only in (None, "md"):
        made.append(export_markdown(schedule, outdir / f"schedule_{tag}.md", label))
    if only in (None, "ics"):
        made.append(export_ics(schedule, outdir / f"schedule_{tag}.ics", section_times_text=section_times))
    for p in made:
        print(f"[+] 已保存：{p}")
    print(
        f"[✓] {schedule['student'].get('name', '')}"
        f"（学号 {mask(schedule['student'].get('sid', ''))}）"
        f" {label} 共 {schedule['count']} 门课"
    )


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = load_config()

    if args.cookie_status:
        print(cookie_store.cookie_age_str())
        return 0
    if args.logout:
        cookie_store.clear_cookie()
        print("[+] 登录会话已清除")
        return 0
    if args.list:
        cached = schedule_store.list_cached()
        if not cached:
            print("本地暂无课表数据")
        for y, t in cached:
            print(f"  {y} 学年 第 {t} 学期：{schedule_store.meta_str(y, t)}")
        return 0

    if args.delete:
        if not args.year:
            print("[!] 请指定要删除的学年学期，如 --delete --year 2026 --term 1", file=sys.stderr)
            return 1
        if schedule_store.delete(args.year, args.term):
            # 界面数据一并清掉，避免显示已删除的课表
            webapp_data = PROJECT_ROOT / "webapp" / "schedule-data.json"
            if webapp_data.exists():
                webapp_data.unlink()
            print(f"[+] 已删除 {args.year} 学年 第 {args.term} 学期课表数据")
        else:
            print(f"[!] 本地没有 {args.year} 学年 第 {args.term} 学期课表数据")
        return 0

    if not args.year:
        print("[!] 请指定学年，如 --year 2026", file=sys.stderr)
        return 1

    if args.grades or args.exams:
        client = ensure_session(cfg, force_relogin=args.relogin)
        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        tag = f"{args.year}-{args.term}"
        try:
            if args.grades:
                payload = client.get_grades(args.year, args.term)
                path = export_json(payload, outdir / f"grades_{tag}.json")
                print(f"[+] 成绩已保存：{path}（{len(payload.get('items', []))} 条）")
            else:
                payload = client.get_exams(args.year, args.term)
                path = export_json(payload, outdir / f"exams_{tag}.json")
                print(f"[+] 考试安排已保存：{path}")
        except JwxtError as e:
            print(f"[!] 拉取失败（code={e.code}）：{e.msg}", file=sys.stderr)
            return 1
        return 0

    schedule = get_schedule(cfg, args.year, args.term, args.update, args.relogin)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    export_all(schedule, outdir, args.only, cfg.extra.get("section_times"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
