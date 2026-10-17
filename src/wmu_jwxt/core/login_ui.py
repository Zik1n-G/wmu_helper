"""极简登录界面：tkinter 窗口只渲染输入框，后台用 AuthWorker 完成 CAS 认证。

界面只有：学号 / 密码 / 验证码（按需显示）/ 状态行 / 登录按钮。
没有 CAS 官方页的背景图、横幅、页脚、第三方登录入口。

“验证码”输入框是通用的：图片验证码（截图来自浏览器）和
短信验证码（提示用户点“发送”）都复用它。
"""

from __future__ import annotations

import io
import threading

from .auth_worker import AuthWorker


class LoginResult:
    def __init__(self):
        self.cookie: str | None = None
        self.error: str | None = None

    @property
    def ok(self) -> bool:
        return self.cookie is not None


class LoginWindow:
    """tkinter 窗口 + AuthWorker 的粘合层，负责线程安全地更新控件。"""

    def __init__(self, account: str = ""):
        import tkinter as tk

        self.tk = tk
        self.result = LoginResult()
        self._photo = None

        self.root = tk.Tk()
        self.root.title("教务系统登录")
        self.root.geometry("400x330")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        pad = {"padx": 24, "pady": 6}

        tk.Label(self.root, text="学号", anchor="w").pack(fill="x", **pad)
        self.ent_account = tk.Entry(self.root)
        self.ent_account.pack(fill="x", **pad)
        if account:
            self.ent_account.insert(0, account)

        tk.Label(self.root, text="密码", anchor="w").pack(fill="x", **pad)
        self.ent_pwd = tk.Entry(self.root, show="•")
        self.ent_pwd.pack(fill="x", **pad)

        # 验证码区默认隐藏（图片验证码或短信验证码时显示）
        self.captcha_frame = tk.Frame(self.root)
        tk.Label(self.captcha_frame, text="验证码", anchor="w").pack(fill="x")
        self.captcha_img = tk.Label(self.captcha_frame)
        self.captcha_img.pack(side="left", pady=4)
        self.ent_captcha = tk.Entry(self.captcha_frame, width=16)
        self.ent_captcha.pack(side="left", padx=(12, 0))
        self.btn_send = tk.Button(
            self.captcha_frame, text="发送", width=6, command=self._on_send
        )
        # “发送”按钮只在短信验证场景显示

        self.status_var = tk.StringVar(value="正在准备…")
        tk.Label(
            self.root, textvariable=self.status_var, anchor="w", fg="#555",
            wraplength=340, justify="left",
        ).pack(fill="x", **pad)

        self.btn = tk.Button(self.root, text="登 录", height=1, command=self._on_submit)
        self.btn.pack(fill="x", **pad)

        self.worker = AuthWorker(self)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._start_worker)
        self.root.bind("<Return>", lambda e: self._on_submit())

    # ---------------- 用户操作 ----------------
    def _start_worker(self):
        threading.Thread(target=self.worker.run, daemon=True).start()

    def _on_submit(self):
        acc = self.ent_account.get().strip()
        pwd = self.ent_pwd.get()
        cap = self.ent_captcha.get().strip()
        if not acc or not pwd:
            self.status_var.set("请填写账号和密码")
            return
        self.btn.config(state="disabled")
        self.status_var.set("提交中…")
        self.worker.submit(acc, pwd, cap)

    def _on_send(self):
        """短信验证码：空提交一次，让 worker 触发“发送”按钮。"""
        self.worker.submit(
            self.ent_account.get().strip(), self.ent_pwd.get(), ""
        )

    def _on_close(self):
        if self.result.cookie is None:
            self.result.error = "用户取消"
        self.worker.stop()
        self.root.destroy()

    # ---------------- worker 回调（切 UI 线程） ----------------
    def set_status(self, msg: str, enable_submit: bool = False):
        def _apply():
            self.status_var.set(msg)
            if enable_submit:
                self.btn.config(state="normal")

        self.root.after(0, _apply)

    def show_captcha(self, png: bytes):
        from PIL import Image, ImageTk

        def _apply():
            img = Image.open(io.BytesIO(png))
            self._photo = ImageTk.PhotoImage(img)
            self.captcha_img.config(image=self._photo)
            self.btn_send.pack_forget()  # 图片验证码不需要“发送”
            self.captcha_frame.pack(fill="x", padx=24, pady=4)
            self.ent_captcha.focus_set()

        self.root.after(0, _apply)

    def show_sms_prompt(self):
        """切换到短信验证码形态：隐藏图片、显示“发送”按钮。"""

        def _apply():
            self.captcha_img.pack_forget()
            self.btn_send.pack(side="right", padx=(8, 0))
            self.captcha_frame.pack(fill="x", padx=24, pady=4)
            self.ent_captcha.focus_set()

        self.root.after(0, _apply)

    def hide_captcha(self):
        self.root.after(0, lambda: self.captcha_frame.pack_forget())

    def succeed(self, cookie: str):
        def _apply():
            self.result.cookie = cookie
            self.status_var.set("登录成功，正在关闭…")
            self.root.after(500, self.root.destroy)

        self.root.after(0, _apply)

    def fail(self, msg: str):
        def _apply():
            self.status_var.set(msg[:90])
            self.btn.config(state="normal")

        self.root.after(0, _apply)


def run_login_ui(account: str = "") -> LoginResult:
    """弹出极简登录窗口（阻塞 UI 线程），返回登录结果。"""
    win = LoginWindow(account=account)
    win.root.mainloop()
    return win.result


if __name__ == "__main__":
    r = run_login_ui()
    if r.ok:
        print("[+] 登录成功，Cookie 段数:", len(r.cookie.split("; ")))
    else:
        print("[!] 失败:", r.error)
