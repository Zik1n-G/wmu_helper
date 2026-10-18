package com.zik1ng.schedule;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.graphics.Insets;
import android.os.Build;
import android.os.Bundle;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.CookieManager;
import android.widget.FrameLayout;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * WMU 课表 APP。
 *
 * 数据流（与"打包进 APK"相反，全部走本地持久化）：
 *   1. 启动 → 读本地 schedule.json，有数据直接显示课表
 *   2. 无数据（首次/被删）→ 界面显示登录引导
 *   3. 登录：打开内嵌 WebView 走 CAS（账号密码 + 短信验证码）
 *   4. 登录成功后用会话 Cookie 调教务系统接口拉课表 → 存本地文件
 *   5. 刷新 = 重新走 3-4；删除 = 删本地文件并回到引导页
 *
 * JS 桥（window.AndroidSchedule）：
 *   readSchedule()      → 本地课表 JSON，无则空串
 *   hasSchedule()       → 是否有本地数据
 *   saveSchedule(j)     → 写本地
 *   deleteSchedule()    → 删本地
 *   startLogin()        → 打开 CAS 登录页（首次登录）
 *   refreshSchedule()   → 打开教务首页（会话活着静默拉课表，过期重登）
 *   readLog()           → 运行日志（诊断）
 *   appInfo()           → 版本信息
 */
public class MainActivity extends Activity {
    private static final String TAG = "Zik1nG";
    private static final String START_URL = "file:///android_asset/index.html";
    private static final String DATA_FILE = "schedule.json";

    private static final String CAS_LOGIN_URL =
        "https://authserver.wmu.edu.cn/authserver/login"
            + "?service=http%3A%2F%2Fjwxt.wmu.edu.cn%2Fsso%2Fjziotlogin";
    private static final String JWXT_HOME =
        "https://jwxt.wmu.edu.cn/jwglxt/xtgl/index_initMenu.html";

    private static volatile MainActivity instance;

    private WebView webView;
    private WebView loginWebView;
    private FrameLayout rootLayout;
    private final ExecutorService executor = Executors.newCachedThreadPool();

    /* 课表是否已拉取（防止 onPageFinished 多次触发重复拉取） */
    private volatile boolean scheduleFetched = false;

    /* 是否已发起"导航到教务系统首页"（ticket 中转后只导航一次） */
    private volatile boolean homeNavigated = false;

    /* 是否已探测过登录态（探测失败可重试，故与 scheduleFetched 分开） */
    private volatile boolean loginChecked = false;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Diag.d("onCreate");
        instance = this;
        writeDefaultTermStart();

        webView = new WebView(this);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view,
                                                              WebResourceRequest request) {
                String path = request.getUrl().getPath();
                if (path != null && path.endsWith("/schedule-data.json")) {
                    // 兼容旧引用：返回本地数据（无则空）
                    String local = readScheduleFile();
                    if (local.isEmpty()) local = "{}";
                    return new WebResourceResponse("application/json", "UTF-8",
                        new java.io.ByteArrayInputStream(local.getBytes(StandardCharsets.UTF_8)));
                }
                return null;
            }
        });

        webView.addJavascriptInterface(new ScheduleBridge(), "AndroidSchedule");

        // 校历通知：启动时生成/合并一次（提前 7 天的节假日/换课提醒）
        try {
            NotificationStore.syncFromCalendar(this, HolidayCalendar.generateToday(System.currentTimeMillis()));
        } catch (Exception e) {
            Diag.e("notif sync failed", e);
        }

        rootLayout = new FrameLayout(this);
        rootLayout.addView(webView, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(rootLayout);
        applyWindowInsets(rootLayout);

        webView.loadUrl(START_URL);
        Diag.d("loadUrl " + START_URL);
    }

    /** 供 ScheduleConverter 取 Context 读配置。 */
    public static MainActivity instance() {
        return instance;
    }

    @Override
    protected void onDestroy() {
        instance = null;
        super.onDestroy();
    }

    /** 首次运行写入校历基准（2026-2027 学年第一学期第一周周一）。 */
    private void writeDefaultTermStart() {
        File f = new File(getFilesDir(), "term_start.txt");
        if (f.exists()) return;
        try (FileOutputStream out = new FileOutputStream(f);
             OutputStreamWriter w = new OutputStreamWriter(out, StandardCharsets.UTF_8)) {
            w.write("2026-09-07");
            w.flush();
        } catch (Exception e) {
            Diag.e("write term_start failed", e);
        }
    }

    /* ---------------- 本地持久化 ---------------- */

    private File dataFile() {
        return new File(getFilesDir(), DATA_FILE);
    }

    private String readScheduleFile() {
        File f = dataFile();
        if (!f.exists()) return "";
        try (FileInputStream in = new FileInputStream(f);
             InputStreamReader r = new InputStreamReader(in, StandardCharsets.UTF_8);
             BufferedReader br = new BufferedReader(r)) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
            return sb.toString();
        } catch (Exception e) {
            Diag.e("readScheduleFile failed", e);
            return "";
        }
    }

    private boolean writeScheduleFile(String json) {
        try (FileOutputStream out = new FileOutputStream(dataFile());
             OutputStreamWriter w = new OutputStreamWriter(out, StandardCharsets.UTF_8)) {
            w.write(json);
            w.flush();
            return true;
        } catch (Exception e) {
            Diag.e("writeScheduleFile failed", e);
            return false;
        }
    }

    private boolean deleteScheduleFile() {
        File f = dataFile();
        return !f.exists() || f.delete();
    }

    /* ---------------- 登录流程 ---------------- */

    /**
     * 打开内嵌 WebView 走 CAS 登录。
     * 用户在真浏览器环境里输账号密码、过验证码/短信，
     * 跳转到教务系统后原生抓 Cookie，再拉课表。
     *
     * @param startUrl 首次登录传 CAS_LOGIN_URL；
     *                 刷新传 JWXT_HOME（会话活着静默拉课表，
     *                 过期会被 302 回 CAS 重新登录）
     */
    @SuppressLint("SetJavaScriptEnabled")
    private void startLoginFlow(final String startUrl) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
            if (loginWebView == null) {
                loginWebView = new WebView(MainActivity.this);
                WebSettings s = loginWebView.getSettings();
                s.setJavaScriptEnabled(true);
                s.setDomStorageEnabled(true);
                s.setAllowFileAccess(true);
                s.setAllowContentAccess(true);
                CookieManager.getInstance().setAcceptCookie(true);
                CookieManager.getInstance().setAcceptThirdPartyCookies(loginWebView, true);

                loginWebView.addJavascriptInterface(
                    new Object() {
                        @JavascriptInterface
                        public void onScheduleFetched(String raw) {
                            MainActivity.this.onScheduleFetched(raw);
                        }

                        @JavascriptInterface
                        public void diag(String msg) {
                            // 诊断信息只进日志文件（≡ 按钮可看），不弹吐司打扰
                            Diag.d("diag: " + msg);
                        }

                        @JavascriptInterface
                        public void onProbeResult(String logged, int status, int length) {
                            MainActivity.this.onProbeResult(logged, status, length);
                        }
                    }, "__nativeBridge");

                loginWebView.setWebViewClient(new WebViewClient() {
                    @Override
                    public void onPageFinished(WebView view, String url) {
                        // 注意：onPageFinished 对页面内的 iframe 也会回调
                        // （CAS 登录页就含指向 jwxt 域的 iframe），
                        // 所以不能只看 URL，必须探测真实登录态。
                        if (scheduleFetched || loginChecked) return;
                        if (!url.contains("jwxt.wmu.edu.cn")) return;
                        if (url.contains("/sso/")) return;   // ticket 中转页，继续等

                        // 探测登录态：请求一个需要登录的接口，
                        // 200 = 已登录；302 回登录页 = 未登录（iframe 误触发）。
                        loginChecked = true;
                        Diag.d("probing login state, url=" + url);
                        probeLoginState(loginWebView);
                    }
                });
            }
            rootLayout.addView(loginWebView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
            scheduleFetched = false;
            homeNavigated = false;
            loginChecked = false;
            loginWebView.loadUrl(startUrl);
            Diag.d("login flow started: " + startUrl);
            }
        });
    }

    /**
     * 探测会话是否已真正登录：请求需要登录的课表入口页。
     * 未登录时服务端 302 回登录页（XHR 会拿到登录页 HTML，不是 JSON）。
     * 已登录才继续拉课表；否则允许后续页面再次探测。
     */
    private void probeLoginState(final WebView view) {
        final String probe =
            "(function(){"
            + "var x=new XMLHttpRequest();"
            + "x.open('GET','https://jwxt.wmu.edu.cn/jwglxt/kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N2151',true);"
            + "x.onreadystatechange=function(){"
            + "  if(x.readyState!==4)return;"
            + "  var t=x.responseText||'';"
            + "  var logged=(x.status===200&&t.indexOf('login_slogin')<0&&t.length>2000);"
            + "  if(window.__nativeBridge)window.__nativeBridge.onProbeResult(logged?'1':'0',x.status,t.length);"
            + "};"
            + "x.onerror=function(){"
            + "  if(window.__nativeBridge)window.__nativeBridge.onProbeResult('0',0,0);"
            + "};"
            + "x.send();"
            + "})();";
        view.evaluateJavascript(probe, null);
    }

    /** 登录态探测结果（JS 桥调用，运行在 JavaBridge 线程）。 */
    @JavascriptInterface
    public void onProbeResult(final String logged, final int status, final int length) {
        Diag.d("probe result: logged=" + logged + " status=" + status + " len=" + length);
        if (!"1".equals(logged)) {
            // 未登录（iframe 误触发或会话还没建立）：放行，等下次页面完成再探
            loginChecked = false;
            return;
        }
        // evaluateJavascript 必须在 UI 线程调用，否则抛异常崩溃
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                if (scheduleFetched) return;
                scheduleFetched = true;
                onReachedJwxt(loginWebView);
            }
        });
    }

    /**
     * 登录成功（已落到教务系统域）：由登录 WebView 页面内 fetch 拉课表。
     * 页面 fetch 会自动带浏览器会话 Cookie，避免原生手动拼 Cookie 出错。
     */
    private void onReachedJwxt(final WebView view) {
        Diag.d("reached jwxt, fetching schedule in page");
        if (Looper.myLooper() != Looper.getMainLooper()) {
            // 防御：非 UI 线程调用时切回 UI 线程
            runOnUiThread(new Runnable() {
                @Override
                public void run() { onReachedJwxt(view); }
            });
            return;
        }
        notifyUi("正在拉取课表…");

        final int year = ScheduleFetcher.currentAcademicYear();
        final int xqm = ScheduleFetcher.currentTermCode();

        // 页面内依次拉六类课表，合并后交给原生转换。
        // 用绝对 https URL：CAS 回调页是 http://，相对路径会解析成 http 请求。
        // 整段写成单个字符串 + String.format 注入参数，避免拼接漏 '+' 导致 JS 语法错误。
        final String js = String.format(
            "(function(){"
            + "if(window.__nativeBridge)window.__nativeBridge.diag('js injected, bridge='+(!!window.__nativeBridge));"
            + "var types=['01','02','03','04','05','06'];"
            + "var url='https://jwxt.wmu.edu.cn/jwglxt/kbcx/xskbcx_cxXsgrkb.html';"
            + "var all=[];var sjk=[];var xsxx=null;var done=0;"
            + "function post(t){"
            + "  var b='xnm=%d&xqm=%d&kzlx=ck&xsdm='+t+'&kclbdm=&kclxdm='"
            + "        +'&queryModel.showCount=500&queryModel.currentPage=1';"
            + "  var x=new XMLHttpRequest();"
            + "  x.open('POST',url,true);"
            + "  x.setRequestHeader('X-Requested-With','XMLHttpRequest');"
            + "  x.setRequestHeader('Content-Type','application/x-www-form-urlencoded');"
            + "  x.onreadystatechange=function(){"
            + "    if(x.readyState!==4)return;"
            + "    done++;"
            + "    if(window.__nativeBridge&&window.__nativeBridge.diag)"
            + "      window.__nativeBridge.diag('type='+t+' status='+x.status+' len='+(x.responseText||'').length);"
            + "    if(x.status===200&&x.responseText){"
            + "      try{var j=JSON.parse(x.responseText);"
            + "        if(!xsxx&&j.xsxx)xsxx=j.xsxx;"
            + "        (j.kbList||[]).forEach(function(k){all.push(k);});"
            + "        (j.sjkList||[]).forEach(function(k){sjk.push(k);});"
            + "      }catch(e){}}"
            + "    if(done===types.length){"
            + "      var out={kbList:all,sjkList:sjk,xsxx:xsxx};"
            + "      if(window.__nativeBridge)window.__nativeBridge.onScheduleFetched(JSON.stringify(out));"
            + "    }"
            + "  };"
            + "  x.send(b);"
            + "}"
            + "types.forEach(post);"
            + "if(window.__nativeBridge)window.__nativeBridge.diag('all posts sent');"
            + "})();",
            year, xqm);

        view.evaluateJavascript(js, null);
    }

    /** 页面内 fetch 完成，收到原始课表 JSON（JS 桥线程，勿碰 UI）。 */
    @JavascriptInterface
    public void onScheduleFetched(String rawJson) {
        Diag.d("schedule fetched in page, len=" + (rawJson == null ? 0 : rawJson.length()));
        executor.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    JSONObject payload = new JSONObject(rawJson);
                    int xqm = ScheduleFetcher.currentTermCode();
                    String json = ScheduleConverter.toWeekView(
                        payload,
                        ScheduleFetcher.currentAcademicYear(),
                        xqm == 3 ? 1 : (xqm == 12 ? 2 : 3));
                    writeScheduleFile(json);
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            if (loginWebView != null) {
                                rootLayout.removeView(loginWebView);
                            }
                            notifyUi(null);
                        }
                    });
                } catch (Exception e) {
                    Diag.e("convert failed", e);
                    notifyUi("课表解析失败：" + e.getMessage());
                }
            }
        });
    }

    private void notifyUi(final String message) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                if (message != null) {
                    android.widget.Toast.makeText(
                        MainActivity.this, message, android.widget.Toast.LENGTH_SHORT).show();
                }
                webView.evaluateJavascript(
                    "(function(){ if (window.__onNativeEvent) window.__onNativeEvent("
                        + (message == null ? "null" : JSONObject.quote(message)) + "); })()",
                    null);
            }
        });
    }

    /* ---------------- 返回键 ---------------- */

    @Override
    public void onBackPressed() {
        // 登录页打开时，返回键先回界面（取消登录）
        if (loginWebView != null && loginWebView.getParent() != null) {
            rootLayout.removeView(loginWebView);
            return;
        }
        webView.evaluateJavascript(
            "(function(){ if (window.__onNativeBack) { window.__onNativeBack(); return true; } return false; })()",
            new android.webkit.ValueCallback<String>() {
                @Override
                public void onReceiveValue(String value) {
                    if (value == null || !value.contains("true")) {
                        finish();
                    }
                }
            });
    }

    /* ---------------- JS 桥 ---------------- */

    private class ScheduleBridge {
        @JavascriptInterface
        public String readSchedule() {
            return readScheduleFile();
        }

        @JavascriptInterface
        public boolean hasSchedule() {
            return dataFile().exists() && !readScheduleFile().isEmpty();
        }

        @JavascriptInterface
        public boolean saveSchedule(String json) {
            return writeScheduleFile(json);
        }

        @JavascriptInterface
        public boolean deleteSchedule() {
            boolean ok = deleteScheduleFile();
            Diag.d("deleteSchedule -> " + ok);
            return ok;
        }

        @JavascriptInterface
        public void startLogin() {
            startLoginFlow(CAS_LOGIN_URL);
        }

        @JavascriptInterface
        public void refreshSchedule() {
            // 刷新：直接进教务首页。会话活着 → 探测通过 → 静默拉课表；
            // 过期 → 服务端 302 回 CAS 登录页重新登录。
            startLoginFlow(JWXT_HOME);
        }

        @JavascriptInterface
        public void fetchSchedule() {
            // 与 refreshSchedule 同义：进教务首页，会话活着静默拉，过期重登
            startLoginFlow(JWXT_HOME);
        }

        @JavascriptInterface
        public String readLog() {
            // 日志功能保留但入口已隐藏（铃铛占位）：
            // 需要调试时在 index.html 加回 btn-log 按钮即可。
            return Diag.readAll();
        }

        @JavascriptInterface
        public String getNotifications() {
            return NotificationStore.getAll(MainActivity.this);
        }

        @JavascriptInterface
        public boolean markNotificationRead(String id) {
            try {
                return NotificationStore.markRead(MainActivity.this, id);
            } catch (Exception e) {
                Diag.e("markRead failed", e);
                return false;
            }
        }

        @JavascriptInterface
        public int deleteReadNotifications() {
            int n = NotificationStore.deleteRead(MainActivity.this);
            Diag.d("deleteReadNotifications -> " + n);
            return n;
        }

        @JavascriptInterface
        public String appInfo() {
            return "{\"version\":\"1.01\",\"platform\":\"android\"}";
        }
    }

    /* ---------------- 系统栏避让 ---------------- */

    private void applyWindowInsets(final View root) {
        if (Build.VERSION.SDK_INT < 23) return;
        root.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener() {
            @Override
            public WindowInsets onApplyWindowInsets(View v, WindowInsets insets) {
                int left = 0, top = 0, right = 0, bottom = 0;
                if (Build.VERSION.SDK_INT >= 29) {
                    Insets bars = insets.getSystemWindowInsets();
                    left = bars.left; top = bars.top; right = bars.right; bottom = bars.bottom;
                } else {
                    top = insets.getSystemWindowInsetTop();
                    bottom = insets.getSystemWindowInsetBottom();
                    left = insets.getSystemWindowInsetLeft();
                    right = insets.getSystemWindowInsetRight();
                }
                v.setPadding(left, top, right, bottom);
                return insets.consumeSystemWindowInsets();
            }
        });
    }
}
