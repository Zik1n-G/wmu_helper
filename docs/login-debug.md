# 登录方案调研记录（2026-10-17）

本文记录温医助手登录方案的调研过程。结论以文末"最终方案"为准，
前面的排查记录说明为什么排除了直接 POST 登录。

## 本地登录接口排查

最初尝试用 `.env` 账号密码直接 POST 到
`jwxt.wmu.edu.cn/jwglxt/xtgl/login_slogin.html`，服务端返回
`用户名或密码不正确，请重新输入！`（p#tips），且
`Set-Cookie: rememberMe=deleteMe`（认证失败明确信号）。
`mmsrddcshkzfs=0` 表示失败计数关闭，重复尝试不锁号。

### 已排除的因素

| 假设 | 验证方式 | 结论 |
|---|---|---|
| RSA 实现错误 | openssl 1024-bit 密钥对 + cryptography 私钥解密往返 | 实现正确（PKCS#1 v1.5，`hex2b64(rsaKey.encrypt(mm))` 与 login.js 一致） |
| 表单字段缺失 | 页面实际只有 4 个 input（csrftoken/language/yhm/mm×2） | 已全发；19 个隐藏字段是 login.js 里其他部署版本的，WMU 未渲染 |
| 双 mm 同名框漏发 | 同时发两个 `mm=密文` | 无效 |
| 公钥一次性轮换 | 连续两次 getPublicKey，modulus 不同 | 公钥确实每次变，但单次流程（取一次即用）服务端 session 存的应是同一把 |
| 缺 login_logoutAccount 前置 | 按 login.js 顺序补调 | 无效 |
| 缺语言/Referer/UA | 全部按浏览器补齐 | 无效 |

### login.js 权威流程（当时抓取，已缓存于 .cache/research）

1. `$.getJSON /xtgl/login_getPublicKey.html` → modulus/exponent
2. `mmsfjm==1` → `rsaKey.setPublic(b64tohex(modulus), b64tohex(exponent))`；`enPassword = hex2b64(rsaKey.encrypt(mm))`
3. `$("#mm").val(enPassword)` + `$("#hidMm").val(enPassword)`（两个同名 mm 都设）
4. `$.post /xtgl/login_logoutAccount.html`（csrfTokenLogout，WMU 页面无此字段，传空）
5. `document.forms[0].submit()` → 原生表单 POST 到 login_slogin.html

### 开关字段实测值（WMU 本地登录）

- mmsfjm=1（加密开）、mmsrddcshkzfs=0（无失败计数）、dlsfbxyzm=0（无验证码）
- dxsyrz=0（无短信验证）、userPolicyOn=0（无协议勾选）、xxdm=10343（学校代码）

## 失败根因

上述全部排除后仍未成功，进一步验证发现：WMU 教务系统**没有独立账号体系**，
`jwxt.wmu.edu.cn` 的登录入口是统一身份认证（CAS，
`authserver.wmu.edu.cn`）的单点登录代理。本地 `login_slogin.html`
只接受 CAS 签发的票据，账号密码在 CAS 侧校验。

`.env` 里保存的账号密码是统一身份认证的，不是教务系统本地账号。

## 最终方案

放弃脚本 POST 登录，改用内嵌 WebView 走完整 CAS 流程：

1. 打开 `https://authserver.wmu.edu.cn/authserver/login?service=...`
2. 用户在真实浏览器环境输入账号密码（如有风控则短信验证）
3. CAS 回调教务系统建立会话
4. 检测落到教务系统域后，用页面上下文（自动带会话 Cookie）POST 拉六类课表

WebView 方案同时解决了 CAS 的反自动化检测（脚本 POST 触发 401/423
风控）和短信验证码的输入问题。

风险提示：CAS 有账号级风控，脚本化频繁登录会触发手机验证码，
严重时临时锁定。因此 APP 只在首次登录和手动点刷新时走 WebView，
日常打开读本地缓存，不反复登录。
