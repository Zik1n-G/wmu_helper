"""AuthWorker：后台线程里驱动 Playwright 完成 CAS 登录。

CAS 页面结构（WMU 实测，2026-10-17）：
- /authserver/login 是外壳页，登录表单在 iframe /authserver/cas/login-normal.html 里
- iframe 内： #unPassword（学号）/ #pwPassword（密码）/ .submit-btn（登录按钮）
- 点登录后由 iframe 的 loginPassword() 调父页面 doLogin() 提交 CAS 表单
- 账号密码通过后，CAS 对该账号要求短信二次验证：
  主页面出现 #token（验证码）/ #btnSend（发送）/ #btnSubmit（确定）
- 也可能出现图片验证码 #cptPassword（iframe 内）

所有 Playwright 调用都在同一个线程（run()）内完成：
同步 API 的 greenlet 不能跨线程切换，故 submit() 只入队，
由 run() 的循环在同线程执行。
"""

from __future__ import annotations

import queue
import threading
import time
from urllib.parse import quote, urlparse

from playwright.sync_api import sync_playwright

# CAS 外壳页（登录表单在其 iframe 内）
CAS_LOGIN = (
    "https://authserver.wmu.edu.cn/authserver/login"
    "?service=" + quote("http://jwxt.wmu.edu.cn/sso/jziotlogin", safe="")
)
JWXT_HOME = "https://jwxt.wmu.edu.cn/jwglxt/xtgl/index_initMenu.html"

JWXT_HOST = "jwxt.wmu.edu.cn"
LOGIN_IFRAME_MARK = "login-normal.html"
CAPTCHA_IN_IFRAME = "#cptPassword"
SUBMIT_IN_IFRAME = ".submit-btn"
SMS_TOKEN = "#token"
SMS_SEND = "#btnSend"
SMS_SUBMIT = "#btnSubmit"


class AuthWorker:
    """后台认证线程。UI 通过 ui 回调收到状态（回调需自行切 UI 线程）。"""

    def __init__(self, ui):
        self.ui = ui
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._busy = threading.Lock()
        self._done = threading.Event()
        self._requests: queue.Queue = queue.Queue()

    # ---------------- 生命周期 ----------------
    def run(self) -> None:
        try:
            with sync_playwright() as pw:
                self.playwright = pw
                self.browser = pw.chromium.launch(headless=True)
                self.context = self._new_context()
                self.page = self.context.new_page()
                self.page.goto(CAS_LOGIN, wait_until="load", timeout=60000)
                self._wait_login_iframe()
                self.ui.set_status("就绪：请输入账号密码", enable_submit=True)
                while not self._done.is_set():
                    try:
                        req = self._requests.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if req is None:
                        break
                    self._handle_submit(*req)
        except Exception as e:  # noqa: BLE001 - 顶层兜底
            if not self._done.is_set():
                self.ui.fail(f"登录过程出错: {type(e).__name__}: {e}")
        finally:
            self._close_browser()

    def stop(self) -> None:
        self._done.set()

    def submit(self, account: str, password: str, captcha: str = "") -> None:
        """UI 线程调用：只入队。"""
        self._requests.put((account, password, captcha))

    # ---------------- 页面定位 ----------------
    def _login_frame(self):
        """返回登录表单所在的 iframe frame 对象（可能已被移除，返回 None）。"""
        try:
            for f in self.page.frames:
                if LOGIN_IFRAME_MARK in f.url:
                    return f
        except Exception:
            pass
        return None

    def _wait_login_iframe(self, timeout_ms: int = 20000) -> None:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            f = self._login_frame()
            if f and f.query_selector("#unPassword"):
                return
            self.page.wait_for_timeout(300)
        raise RuntimeError("登录表单加载超时（iframe 未就绪）")

    def _new_context(self):
        return self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            viewport={"width": 1280, "height": 800},
        )

    # ---------------- 提交处理 ----------------
    def _handle_submit(self, account: str, password: str, captcha: str) -> None:
        if not self._busy.acquire(blocking=False):
            self.ui.set_status("正在处理，请稍候…")
            return
        try:
            if self.page is None:
                self._done.set()
                self.ui.fail("浏览器未就绪")
                return

            # 场景 A：短信验证码输入中
            if self._sms_form_visible():
                self._submit_sms(captcha)
                return

            self.ui.set_status("提交中…", enable_submit=False)
            frame = self._login_frame()
            if frame is None:
                self._done.set()
                self.ui.fail("登录表单已消失，请重试")
                return

            frame.fill("#unPassword", account, timeout=10000)
            frame.fill("#pwPassword", password, timeout=10000)

            # 场景 B：iframe 内图片验证码可见
            cap = frame.query_selector(CAPTCHA_IN_IFRAME)
            if cap and cap.is_visible():
                if not captcha:
                    self._show_iframe_captcha(frame)
                    self.ui.set_status("请输入验证码", enable_submit=True)
                    return
                frame.fill(CAPTCHA_IN_IFRAME, captcha, timeout=5000)

            frame.query_selector(SUBMIT_IN_IFRAME).click(timeout=10000)
            self.ui.set_status("正在登录…")
            self._wait_result()
        except Exception as e:  # noqa: BLE001
            self._done.set()
            self.ui.fail(f"提交失败: {type(e).__name__}: {e}")
        finally:
            self._busy.release()

    def _submit_sms(self, code: str) -> None:
        page = self.page
        if not code:
            # 自动帮点“发送”，减少用户操作
            try:
                btn = page.query_selector(SMS_SEND)
                if btn and btn.is_visible() and btn.is_enabled():
                    btn.click()
                    if hasattr(self.ui, "show_sms_prompt"):
                        self.ui.show_sms_prompt()
                    self.ui.set_status("验证码已发送，请查看手机短信", enable_submit=True)
                    return
            except Exception:
                pass
            if hasattr(self.ui, "show_sms_prompt"):
                self.ui.show_sms_prompt()
            self.ui.set_status("请点击“发送验证码”并输入收到的短信验证码", enable_submit=True)
            return
        page.fill(SMS_TOKEN, code, timeout=5000)
        page.query_selector(SMS_SUBMIT).click(timeout=10000)
        self.ui.set_status("正在验证…")
        self._wait_result()

    def _sms_form_visible(self) -> bool:
        try:
            el = self.page.query_selector(SMS_TOKEN)
            return bool(el and el.is_visible())
        except Exception:
            return False

    def _show_iframe_captcha(self, frame) -> None:
        img = frame.query_selector("img[src*='captcha'], img[src*='yzm'], #captchaImg")
        if img:
            try:
                self.ui.show_captcha(img.screenshot())
            except Exception:
                pass

    # ---------------- 结果等待 ----------------
    def _wait_result(self) -> None:
        page = self.page
        deadline = time.monotonic() + 150
        seen = ""
        while time.monotonic() < deadline:
            if urlparse(page.url).netloc == JWXT_HOST:
                self._finish()
                return

            # 短信验证页出现
            if self._sms_form_visible():
                if hasattr(self.ui, "show_sms_prompt"):
                    self.ui.show_sms_prompt()
                self.ui.set_status(
                    "账号密码已通过，请点“发送”获取短信验证码",
                    enable_submit=True,
                )
                return

            # iframe 内错误提示
            frame = self._login_frame()
            if frame:
                cap = frame.query_selector(CAPTCHA_IN_IFRAME)
                if cap and cap.is_visible():
                    self._show_iframe_captcha(frame)
                    self.ui.set_status("验证码有误，请重新输入", enable_submit=True)
                    return
                for sel in (".error", ".tips", "#tips"):
                    el = frame.query_selector(sel)
                    if el and el.is_visible():
                        text = (el.inner_text() or "").strip()
                        if text and text != seen:
                            seen = text
                            self.ui.set_status(f"提示: {text[:70]}", enable_submit=True)
                            return
                        break
            page.wait_for_timeout(500)
        self._done.set()
        self.ui.fail("等待登录结果超时，请重试")

    # ---------------- 收尾 ----------------
    def _finish(self) -> None:
        page = self.page
        if "jwglxt" not in page.url:
            page.goto(JWXT_HOME, wait_until="load", timeout=60000)
        page.wait_for_timeout(1500)
        cookies = self.context.cookies()
        if not any(c["name"] == "JSESSIONID" for c in cookies):
            self._done.set()
            self.ui.fail("登录后未取得会话 Cookie")
            return
        cookie = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        self._done.set()
        self.ui.succeed(cookie)

    def _close_browser(self) -> None:
        for closer in (self.context, self.browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        self.context = None
        self.browser = None
