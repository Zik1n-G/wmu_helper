"""WMU 正方 v5 教务系统只读客户端。

登录走正方本地入口（RSA 加密密码 + csrftoken），
数据走 /jwglxt/ 前缀接口，只实现只读功能。
"""

from __future__ import annotations

import json
import time
from typing import Any

import requests
from pyquery import PyQuery as pq

from .config import Config
from .rsa import encrypt_password

# 自定义业务状态码
CODE_OK = 1000
CODE_BAD_CREDENTIALS = 1002
CODE_SESSION_EXPIRED = 1006
CODE_MAINTENANCE = 2333
CODE_UNKNOWN = 999


class JwxtError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


class Client:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()
        self.sess = requests.Session()
        self.sess.keep_alive = False
        self.headers = {
            "User-Agent": self.cfg.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._last_request = 0.0
        self.logged_in = False
        self.student_info: dict[str, Any] = {}

    # ---------------------------------------------------------------- 基础
    def _throttle(self) -> None:
        gap = time.monotonic() - self._last_request
        if gap < self.cfg.request_interval:
            time.sleep(self.cfg.request_interval - gap)
        self._last_request = time.monotonic()

    def _url(self, path: str) -> str:
        return f"{self.cfg.jwglxt}/{path.lstrip('/')}"

    def _get(self, path: str, referer: str | None = None, **kw):
        self._throttle()
        headers = dict(self.headers)
        if referer:
            headers["Referer"] = referer
        return self.sess.get(self._url(path), headers=headers, timeout=self.cfg.timeout, **kw)

    def _post(self, path: str, data: dict | list, referer: str | None = None, **kw):
        self._throttle()
        headers = dict(self.headers)
        headers["X-Requested-With"] = "XMLHttpRequest"
        if referer:
            headers["Referer"] = referer
        return self.sess.post(
            self._url(path), headers=headers, data=data, timeout=self.cfg.timeout, **kw
        )

    # ---------------------------------------------------------------- 登录
    def login_with_cookie(self, cookie: str) -> dict:
        """用浏览器登录得到的原始 Cookie 字符串建立会话（禁止 dict 化）。"""
        self.sess.headers["Cookie"] = cookie
        self.logged_in = True
        return {"code": CODE_OK, "msg": "Cookie 会话已建立"}

    def login(self, account: str | None = None, password: str | None = None) -> dict:
        """账号密码登录。认证失败不重试（防锁号 dlsbsdsj=5）。"""
        account = account or self.cfg.account
        password = password or self.cfg.password
        if not account or not password:
            raise JwxtError(CODE_BAD_CREDENTIALS, "缺少账号或密码")

        login_url = self._url("xtgl/login_slogin.html")
        key_url = self._url("xtgl/login_getPublicKey.html")

        r = self._get("xtgl/login_slogin.html")
        if r.status_code != 200:
            raise JwxtError(CODE_MAINTENANCE, f"登录页返回 HTTP {r.status_code}")
        doc = pq(r.text)
        csrf_token = doc("#csrftoken").attr("value")
        if not csrf_token:
            raise JwxtError(CODE_MAINTENANCE, "登录页未找到 csrftoken（系统可能改版）")

        k = self._get(f"xtgl/login_getPublicKey.html?time={int(time.time() * 1000)}", referer=login_url)
        try:
            pub = k.json()
            modulus, exponent = pub["modulus"], pub["exponent"]
        except (ValueError, KeyError) as e:
            raise JwxtError(CODE_MAINTENANCE, f"RSA 公钥接口异常: {e}")

        mm = encrypt_password(password, modulus, exponent)
        # 页面有两个同名 mm 输入框（hidMm=password 防自动填充 + mm=text），
        # 原生表单提交时两个都会发出，服务端取首个非空；只发一个会被判空密码。
        form_data = [
            ("csrftoken", csrf_token),
            ("language", "zh_CN"),
            ("yhm", account),
            ("mm", mm),
            ("mm", mm),
        ]
        r = self._post("xtgl/login_slogin.html", form_data, referer=login_url)
        doc = pq(r.text)
        tips = doc("p#tips")
        if str(tips) != "":
            text = tips.text()
            if "用户名或密码" in text or "密码" in text and "错误" in text:
                raise JwxtError(CODE_BAD_CREDENTIALS, "用户名或密码不正确")
            raise JwxtError(998, f"登录被拒: {text}")

        self.logged_in = True
        return {"code": CODE_OK, "msg": "登录成功"}

    def _ensure_login(self) -> None:
        if not self.logged_in:
            raise JwxtError(CODE_SESSION_EXPIRED, "尚未登录")

    def _check_session(self, resp: requests.Response) -> None:
        if "login_slogin" in resp.url or "用户登录" in resp.text[:2000]:
            raise JwxtError(CODE_SESSION_EXPIRED, "会话失效，请重新登录")

    # ---------------------------------------------------------------- 课表
    # 课表类型（xsbjList 实测，WMU 2026-10）：
    #   01 讲课 / 02 实验 / 03 讨论 / 04 实践 / 05 在线 / 06 自主学习
    # 只发 xsdm 空值会漏掉实验、实践等，必须逐类拉取再合并。
    SCHEDULE_TYPES = ["01", "02", "03", "04", "05", "06"]

    def _fetch_schedule_type(self, year: int, term: int, xqm: int, xsdm: str) -> dict:
        data = {
            "xnm": str(year),
            "xqm": str(xqm),
            "kzlx": "ck",
            "xsdm": xsdm,
            "kclbdm": "",
            "kclxdm": "",
            "queryModel.showCount": "500",
            "queryModel.currentPage": "1",
        }
        entry = self._url("kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N2151")
        r = self._post("kbcx/xskbcx_cxXsgrkb.html", data, referer=entry)
        self._check_session(r)
        try:
            return r.json()
        except ValueError:
            raise JwxtError(CODE_MAINTENANCE, "课表接口未返回 JSON（可能改版）")

    def get_schedule(self, year: int, term: int) -> dict:
        """个人课表（含讲课/实验/讨论/实践/在线/自主学习全类型）。

        term: 1/2/3（映射 xqm=3/12/16）。
        返回合并后的 payload：kbList 为各类型并集，其余字段取首次响应。
        """
        self._ensure_login()
        xqm = {1: 3, 2: 12, 3: 16}.get(term)
        if xqm is None:
            raise JwxtError(CODE_UNKNOWN, f"学期参数仅支持 1/2/3，收到 {term}")

        merged: dict = {}
        kb: list[dict] = []
        seen: set[str] = set()
        sjk: list[dict] = []
        sjk_seen: set[str] = set()

        for xsdm in self.SCHEDULE_TYPES:
            payload = self._fetch_schedule_type(year, term, xqm, xsdm)
            if not merged:
                merged = payload
            for item in payload.get("kbList") or []:
                # 同一门课可能同时出现在讲课/实验两类，按 jxb_id+jc+zcd 去重
                key = "|".join(
                    str(item.get(k, "")) for k in ("jxb_id", "jc", "zcd", "cdmc")
                )
                if key and key not in seen:
                    seen.add(key)
                    kb.append(item)
            for item in payload.get("sjkList") or []:
                key = str(item.get("kcmc", "")) + str(item.get("qsjsz", ""))
                if key and key not in sjk_seen:
                    sjk_seen.add(key)
                    sjk.append(item)

        merged["kbList"] = kb
        merged["sjkList"] = sjk
        return merged

    # ---------------------------------------------------------------- 成绩
    def get_grades(self, year: int, term: int = 0) -> dict:
        """成绩查询。term=0 查全年。"""
        self._ensure_login()
        data = {
            "xnm": str(year),
            "xqm": {1: 3, 2: 12, 3: 16}.get(term, ""),
            "queryModel.showCount": "500",
            "queryModel.currentPage": "1",
        }
        entry = self._url("cjcx/cjcx_cxDgXscj.html?gnmkdm=N305005")
        r = self._post("cjcx/cjcx_cxXsgrcj.html?doType=query", data, referer=entry)
        self._check_session(r)
        try:
            return r.json()
        except ValueError:
            raise JwxtError(CODE_MAINTENANCE, "成绩接口未返回 JSON")

    # ---------------------------------------------------------------- 考试
    def get_exams(self, year: int, term: int = 0) -> dict:
        """考试安排。"""
        self._ensure_login()
        data = {
            "xnm": str(year),
            "xqm": {1: 3, 2: 12, 3: 16}.get(term, ""),
            "queryModel.showCount": "500",
            "queryModel.currentPage": "1",
        }
        entry = self._url("kwgl/kscx_cxXsksxxIndex.html?gnmkdm=N358105")
        r = self._post("kwgl/kscx_cxXsList.html", data, referer=entry)
        self._check_session(r)
        try:
            return r.json()
        except ValueError:
            raise JwxtError(CODE_MAINTENANCE, "考试接口未返回 JSON")

    # ---------------------------------------------------------------- 信息
    def get_student_info(self) -> dict:
        """个人信息（页面内联渲染，做简单解析）。"""
        self._ensure_login()
        entry = self._url("xsxxxggl/xsgrxxwh_cxXsgrxx.html?gnmkdm=N100801")
        r = self._get("xsxxxggl/xsgrxxwh_cxXsgrxx.html?gnmkdm=N100801", referer=entry)
        self._check_session(r)
        doc = pq(r.text)
        info = {}
        for el in doc(".form-group .control-label").items():
            pass  # 占位：不同部署字段容器不一致，按需调整
        return info


def dump_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
