# 温医助手

每学期都要上好几次教务系统查课表：哪个教室、第几节、哪一周上，一节课一节课翻。
温医助手帮你把这件事变成一次点击：用你的统一身份认证账号登录一次，课表存在手机里，
之后打开就能看，按周次铺开，点课程卡片看教室、老师、学分和上课时间。

Android APP 是主要形态，界面是纯 Web，同一套代码在电脑上也能跑（Python CLI 拉取后本地预览）。

## 能帮你做什么

- 登录一次就够。之后打开 APP 直接看课表，不登录、不发请求；想更新了手动点刷新，想清空点删除
- 课表一门不落。讲课、实验、讨论、实践、在线、自主学习六类合并拉取，实验课和实践课都在，通识选修课单独标了「选修课」
- 哪一周上什么课一眼看清。侧边栏按月份选周，左右滑动切上周/下周，滑太远了一个按钮回本周
- 今天要上什么，点顶栏「今天 周X」胶囊。全屏时间轴按节次铺开，节次号和真实上课钟点都在
- 放假调休不会忘。铃铛提前一周提醒放假和补课安排，补课日单独提醒；通知永久保留，删只能删已读的
- 上课钟点是准的。茶山和滨海两个校区两张作息表，按课程校区分别取时间

## 目录结构

```
curriculum_table_get/
├── main.py                        # CLI：拉课表 / 导出 / 删除 / 缓存管理
├── requirements.txt
├── build-apk.ps1                  # 手动构建 APK（aapt2 + javac + d8，无需 Gradle）
├── .env.example                   # 配置模板（.env 已 gitignore）
├── webapp/                        # 课表界面（HTML/CSS/JS，无框架依赖）
│   ├── index.html
│   ├── style.css
│   └── app.js
├── android/                       # Android 工程（WebView 壳 + 原生桥）
│   └── app/src/main/
│       ├── AndroidManifest.xml
│       ├── assets/                # webapp/ 的副本，打包时同步
│       ├── java/com/zik1ng/schedule/
│       │   ├── MainActivity.java      # WebView 容器 + JS 桥
│       │   ├── HolidayCalendar.java   # 校历节假日引擎（内置校历 + 通知生成）
│       │   ├── NotificationStore.java # 通知持久化（已读态、删除墓碑）
│       │   ├── ScheduleFetcher.java   # 原生 HTTP 拉取（六类合并）
│       │   ├── ScheduleConverter.java # 原始 JSON → 周视图
│       │   └── Diag.java              # 双写日志（logcat + 文件）
│       └── res/                       # 图标、字符串等资源
├── docs/
│   └── login-debug.md            # 登录方案调研记录
├── src/wmu_jwxt/
│   ├── core/
│   │   ├── config.py             # .env 解析、脱敏
│   │   ├── rsa.py                # 纯 Python RSA
│   │   ├── auth_worker.py        # Playwright 后台认证（桌面端登录用）
│   │   ├── login_ui.py           # 极简登录窗口（tkinter，只有输入框）
│   │   ├── client.py             # 课表/成绩/考试客户端
│   │   ├── cookie_store.py       # 会话缓存
│   │   ├── schedule_store.py     # 课表持久化
│   │   └── section_time.py       # 节次↔时间（分校区）+ 教学周 + 校历备注
│   ├── parsers/schedule.py       # kbList → 周次视图
│   └── exporters/
│       ├── json_export.py
│       ├── markdown_export.py
│       ├── ics_export.py
│       └── webapp_export.py      # → webapp/schedule-data.json
└── tests/
    └── test_offline.py           # RSA 往返 + 课表解析
```

## 使用（桌面端）

``` bash
pip install -r requirements.txt
python -m playwright install chromium
```

``` bash
# 首次：登录（弹窗输账号密码 + 短信验证码）→ 拉课表 → 存本地
python main.py --year 2026 --term 1

# 之后：直接读本地，不登录不发请求
python main.py --year 2026 --term 1

# 手动更新课表（重新登录拉取）
python main.py --year 2026 --term 1 --update

# 删除课表
python main.py --delete --year 2026 --term 1

# 本地有哪些课表 / 会话状态
python main.py --list
python main.py --cookie-status

# 预览界面
cd webapp && python -m http.server 8899
```

成绩和考试（始终在线拉取）：

``` bash
python main.py --grades --year 2026 --term 1
python main.py --exams   --year 2026 --term 1
```

## 手机使用

装好后打开 APP，三步：

1. 点「登录教务系统」
2. 在内嵌浏览器里输学号密码，学校要求短信验证就收个码
3. 登录成功自动拉课表，跳回课表界面

之后每次打开直接是课表。数据存在手机本地（应用私有目录），卸载 APP 会一并删除。

### 构建 APK

需要 Android SDK（platform android-36.1、build-tools 36.1.0）和 JDK 17+：

``` bash
powershell -ExecutionPolicy Bypass -File build-apk.ps1
```

产物在 `android/build/outputs/apk/debug/Zik1nG-Schedule-debug.apk`。
构建流程是 aapt2 编译资源、javac、d8、jar 合包、zipalign、apksigner 签名，
没有用 Gradle，方便直接看每一步做了什么。签名用的本地调试密钥
（`android/debug.keystore`，已 gitignore），正式发布换自己的签名库。

## 配置（.env）

复制 `.env.example` 为 `.env`：

```
account=你的学号
password=你的密码
term_start=2026-09-07
```

| 键 | 默认 | 说明 |
|---|---|---|
| `term_start` | 空（按 9/1 所在周周一） | 第一周周一，决定周数算得准不准，来自校历 |
| `base_url` | `https://jwxt.wmu.edu.cn` | 换学校正方系统改这里 |
| `timeout` | `10` | 请求超时（秒） |
| `request_interval` | `1.0` | 请求间隔（秒） |
| `section_times` | 空（用校历表） | 自定义节次时间 `1:08:00-08:40,...`，覆盖默认表 |

## 登录机制

教务系统没有独立账号体系，`jwxt.wmu.edu.cn` 的登录入口是统一身份认证（CAS，
`authserver.wmu.edu.cn`）的单点登录代理，账号密码在 CAS 侧校验。直接 POST
本地登录接口会返回「用户名或密码不正确」，排查过程记录在
[docs/login-debug.md](docs/login-debug.md)。

CAS 页面是外壳加 iframe 的结构：

- 外壳页 `/authserver/login`，登录表单在 iframe `/authserver/cas/login-normal.html`
- iframe 内填 `#unPassword` / `#pwPassword`，点登录由 `loginPassword()` 调父页 `doLogin()` 提交
- 账号密码通过后 CAS 要求短信二次验证：页面出现 `#token` / `#btnSend` / `#btnSubmit`

桌面端用 Playwright 后台认证，APP 端用内嵌 WebView，用户在真实浏览器环境里
输账号密码、过验证码/短信。CAS 对脚本化登录有风控（返回 401/423），
这是选 WebView 而不是裸 HTTP 请求的主要原因。

风控提示：短时间内反复登录会触发手机验证码，严重时临时锁定账号。
所以 APP 只在首次登录和手动点刷新时走登录流程，日常打开读本地缓存。

## 课表数据完整性

教务系统的课表接口一次只返回一类课，必须按课表类型（xsdm）逐类拉取再合并，
否则实验课、实践课会整类丢失：

| xsdm | 类型 | 说明 |
|---|---|---|
| 01 | 讲课 | 理论课主课表 |
| 02 | 实验 | 实验课（地点常在 6-xxx 实验楼） |
| 03 | 讨论 | |
| 04 | 实践 | 如电子工艺实践 |
| 05 | 在线 | 超星学习通/智慧树网络课 |
| 06 | 自主学习 | |

周次字段 `zcd` 有多种格式，全部要能解析：

| 格式 | 示例 | 展开 |
|---|---|---|
| 连续 | `1-16周` | 1..16 |
| 离散 | `3周,6周` | [3, 6] |
| 单周 | `1-8周(单)` | [1,3,5,7] |
| 双周 | `8-10周(双)` | [8,10] |
| 单次 | `第7周` | [7] |
| 混合 | `5周,8-10周(双),11-13周,15周` | [5,8,10,11,12,13,15] |

实践课的 `jc` 字段可能是工位号而不是节次号（如「9-16节」），按最大节次 15 截断。

## 节次时间（分校区）

时间来自学校官方校历的两张作息表，两校区不同，按课程所在校区分别取。

课表数据里的 `xqmc` 字段含「滨海」用滨海表，否则茶山表。

## 教学周与节假日

以 `.env` 的 `term_start`（第一周周一）为基准，每 7 天进一周。开学前归第 1 周，
超学期末钳位到总周数。

2026-2027 学年第一学期校历要点：第一周周一 2026-09-07；9/25-27 中秋、
10/1-7 国庆放假，其中 10/6(周二) 补 9/26、10/10(周六) 补 9/27；1/1 元旦休。

课表接口不反映调休（按固定周次返回），所以 APP 内置了一份校历，
放假和换课提醒靠本地这份数据生成，不依赖教务系统。换学年时更新
`HolidayCalendar.java` 里的 `HOLIDAYS` 和 `MAKEUPS` 两张表即可。

## 测试

``` bash
python tests/test_offline.py
```

覆盖 RSA 加解密往返、课表解析（六类合并、zcd 各种格式）、节次时间表。

## 安全

- 密码不写日志、不回显，输出一律脱敏（`2****6`）
- `.env` 和 `.cache/`（会话 Cookie）已 gitignore
- 只读：只调课表/成绩/考试三个查询接口

## 作者

Zik1n_G
