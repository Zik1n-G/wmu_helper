# 方案：WMU 教务系统课表一键获取工具

> 目标：用学生账号密码直接登录 `jwxt.wmu.edu.cn`，拉取个人课表，输出结构化数据（JSON / 周次视图 / 可导出 ICS）。
> 状态：调研 + 公开端点实测完成，待审批后开发。

---

## 一、GitHub 现成项目调研结论

**结论：有多个成熟项目可借鉴，最佳选择是 `openschoolcn/zfn_api`（274★，Python）。**

| 项目 | 语言 | ★ | 适用性 | 说明 |
|---|---|---|---|---|
| [openschoolcn/zfn_api](https://github.com/openschoolcn/zfn_api) | Python | 274 | ⭐⭐⭐ 最佳借鉴 | 新正方 v5 API 全家桶：登录/课表/成绩/考试；登录走**正方本地入口（RSA+csrftoken）**，课表接口 `/jwglxt/kbcx/xskbcx_cxXsKb.html` 与 WMU 逆向文档记录的路径完全一致 |
| [nghuyong/ZhengFang](https://github.com/nghuyong/ZhengFang) | Python | 162 | ⭐⭐ 参考 | 正方助手，偏老版本正方 |
| [vhyz/ZF_Spider](https://github.com/vhyz/ZF_Spider) | Python | 251 | ⭐⭐ 参考 | 抢课脚本，含 RSA 登录实现 |
| [FarmerChillax/new-school-sdk](https://github.com/FarmerChillax/new-school-sdk) | Python | 124 | ⭐⭐ 参考 | 新正方 SDK，自动识别验证码 |
| [lndj/Lcrawl](https://github.com/lndj/Lcrawl) | PHP | 118 | ⭐ 参考 | PHP 爬虫，登录方案较老 |
| [dairoot/school-api](https://github.com/dairoot/school-api) | Python | 237 | ⭐⭐ 参考 | 正方 SDK，架构清晰可读 |

**没有找到专门针对 WMU 课表的项目**——因为正方 v5 是同一套产品、接口同构，`zfn_api` 这类通用 SDK 可直接适配 WMU，无需针对 WMU 单独开发登录部分。

## 二、关键决策：登录走哪条路

本地逆向文档（Project_WmuJwxtxkreverse）已实测两条路径：

| 路径 | 机制 | 状态 | 本方案选择 |
|---|---|---|---|
| A. CAS 统一认证（authserver） | 明文密码 + execution JWT | 🔴 脚本登录被账号级风控 401 拦截（实测 17:42 成功→17:53 被拒） | **不采用** |
| B. 正方本地登录（/jwglxt/xtgl/login_slogin.html） | RSA 公钥加密密码 + csrftoken | 逆向完成未走通；但 zfn_api 已在 274★ 规模上验证此路径可用 | **✅ 采用** |

**为什么 B 可行**：本地文档记录了 B 的完整报文细节（公钥接口、csrftoken 格式、mmsfjm=1 加密开关），zfn_api 的 `encrypt_password()` 就是纯 Python 实现的 RSA（b64tohex + RSAKey），无需第三方加密库。且 B 是设计内的正规登录通道，不是绕过风控。

**风险提示**：若 WMU 部署了正方本地登录的 IP 频率风控，需加请求间隔；若该入口被 CAS 完全旁路禁用，则退路是 Playwright 真浏览器登录 + 导出 Cookie（本地文档路径 B"Cookie 复用"，已验证稳定）。

## 三、实测证据（2026-10-17，只读探测，未用任何凭据）

| # | 探测项 | 结果 |
|---|---|---|
| 1 | CAS 登录页 `authserver.wmu.edu.cn/authserver/login?service=...` | HTTP 200，含 `execution` 字段（UUID 格式） |
| 2 | 正方本地登录页 `jwxt.wmu.edu.cn/jwglxt/xtgl/login_slogin.html` | HTTP 200，21.6KB，含 `csrftoken`（UUID）、`mmsfjm=1`（RSA 加密开）、`yzcskz=10`、`dlsbsdsj=5`（5 次失败锁号） |
| 3 | RSA 公钥接口 `/jwglxt/xtgl/login_getPublicKey.html?time=<ms>` | HTTP 200，`{"modulus":"<1024-bit b64>","exponent":"AQAB"}` —— 标准 RSA，zfn_api 加密方案直接适配 |
| 4 | 课表入口页裸访问（无 gnmkdm） | 302 → 登录页（与本地文档 ⛔6 记录一致） |
| 5 | 课表入口页带 `gnmkdm=N2151` 未登录访问 | 302 → 登录页（会话校验正常） |

**结论：公开层全通，接口形态与 2026-08 逆向时完全一致，未改版。**

## 四、技术方案

### 架构

```
curriculum_table_get/
├── wmu_jwxt/
│   ├── client.py        # 核心客户端：登录 + 课表/成绩/考试拉取（基于 zfn_api 思路重写）
│   ├── rsa.py           # 纯 Python RSA 加密（移植 zfn_api encrypt_password）
│   ├── schedule.py      # 课表结构化：按周次展开、节次解析、合并同一时段多课
│   └── export.py        # 输出：JSON / Markdown 周课表 / ICS 日历
├── main.py              # CLI 入口：python main.py --user 学号 --pass 密码 --term 2026-1
├── .env.example         # 账号密码/Cookie 配置样例
├── requirements.txt     # requests, pyquery（+ lxml）
└── README.md
```

### 核心流程

1. **登录**：GET 登录页取 `csrftoken` → GET `login_getPublicKey.html` 取 modulus/exponent → RSA 加密密码 → POST `login_slogin.html`（字段：csrftoken/yhm/mm）→ Session 带 Cookie
2. **取课表**：POST `/jwglxt/kbcx/xskbcx_cxXsgrkb.html`（本地文档实测接口，返回 JSON 含 xsxx/kbList），参数 `xnm=2026&xqm=3&kzlx=ck&xsdm=&kclbdm=&kclxdm=` + 分页；入口需 `gnmkdm=N2151`
3. **解析输出**：kbList 每条含 kcmc/kch/xqj/jc/cdmc/xm/zcd/xf 等字段 → 三种视图：
   - `timetable.json`：原始结构化数据
   - `周课表.md`：周一~周日的 Markdown 表格，按节次排
   - `课表.ics`：标准日历格式，可导入手机/系统日历（每节课按周次展开为事件）

### 兼容 zfn_api 的差异点（WMU 专属适配）

| 点 | zfn_api 默认 | WMU 实测 | 处理 |
|---|---|---|---|
| 课表数据端点 | `kbcx/xskbcx_cxXsKb.html` | 本地文档实测 `kbcx/xskbcx_cxXsgrkb.html`（v5 新端点） | 两个都带，`_cxXsgrkb` 优先，失败回退 |
| 学期参数 xqm | term²×3（1→3, 2→12） | 与本地文档一致（3/12/16） | 沿用 |
| Cookie 双 JSESSIONID | dict 化（zfn_api 用 requests.Session） | requests.Session 自动按 jar 管理，**不涉及手动 dict 重建问题** | 用 Session 对象即可 |
| 校区/学期 | 无 | WMU 有 xqh_id（3=滨海/5=茶山） | 课表接口不需要，忽略 |

### 安全红线（继承本地项目）

- 密码只从命令行参数或交互输入读，**不落盘**（.env 仅存可选 Cookie）
- 认证类失败（1002 密码错）**0 次重试**（防 5 次锁号）
- 数据请求间隔 ≥1s
- 只读：不碰任何写接口（选课/退课/报名）

## 五、验证计划（开发后自测）

1. 单元：RSA 加密输出与 zfn_api 样例比对格式一致
2. 集成：用真实账号跑通登录 → 拉 2026 学年第一学期课表 → 校验课程数与教务系统页面显示一致
3. 降级：Cookie 失效时给出明确提示；密码错时立即停止并提示（不重试）

## 六、未执行的项

- 未用真实账号密码实测完整登录（等审批后联调，会在你监督下输入凭据）
- 未验证课表接口 `_cxXsgrkb.html` 在登录态下的实际返回（本地文档标 🟡 JS 确认，本次只验证了入口页可达性）

## 七、待你决策的点

1. **目标系统确认**：本方案默认 `jwxt.wmu.edu.cn`（来自本地逆向项目）。若你要做的是另一所学校/另一个正方系统，告诉我域名，改 `base_url` 即可（zfn_api 的通用性正是为此设计）。
2. **凭据提供方式**：开发完成后你本地输入，还是希望我把账号密码配到 `.env`（后者不建议，密码会落盘）。
3. **输出格式优先级**：默认做 JSON + Markdown 周课表 + ICS 三件套，如只要其中一种可以砍。
