package com.zik1ng.schedule;

import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 用登录会话 Cookie 拉取教务系统课表，并转换成界面所需的周视图 JSON。
 *
 * 接口（与桌面端 CLI 同一套）：
 *   POST /jwglxt/kbcx/xskbcx_cxXsgrkb.html
 *   参数：xnm / xqm / kzlx=ck / xsdm(01-06 六类) / 分页
 *
 * 六类课表（讲课/实验/讨论/实践/在线/自主学习）逐类拉取合并，
 * 否则实验课、实践课会整类丢失。
 */
public final class ScheduleFetcher {
    private static final String TAG = "Zik1nG";

    private static final String BASE = "https://jwxt.wmu.edu.cn";
    private static final String ENTRY = BASE
        + "/jwglxt/kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N2151";
    private static final String ENDPOINT = BASE + "/jwglxt/kbcx/xskbcx_cxXsgrkb.html";
    private static final String[] TYPES = {"01", "02", "03", "04", "05", "06"};

    private static final String UA =
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            + "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

    private ScheduleFetcher() {}

    /** 拉当前学年学期课表，返回界面用的周视图 JSON；失败返回 null。 */
    public static String fetch(String cookie) throws Exception {
        int year = currentAcademicYear();
        int xqm = currentTermCode();

        JSONObject merged = null;
        JSONArray kbAll = new JSONArray();
        JSONArray sjkAll = new JSONArray();

        for (String type : TYPES) {
            JSONObject payload = post(type, year, xqm, cookie);
            if (payload == null) continue;
            if (merged == null) merged = payload;
            JSONArray kb = payload.optJSONArray("kbList");
            if (kb != null) {
                for (int i = 0; i < kb.length(); i++) kbAll.put(kb.optJSONObject(i));
            }
            JSONArray sjk = payload.optJSONArray("sjkList");
            if (sjk != null) {
                for (int i = 0; i < sjk.length(); i++) sjkAll.put(sjk.optJSONObject(i));
            }
        }

        if (merged == null) {
            Log.w(TAG, "all schedule requests failed");
            return null;
        }
        merged.put("kbList", kbAll);
        merged.put("sjkList", sjkAll);

        return ScheduleConverter.toWeekView(merged, year, termOf(xqm));
    }

    private static int termOf(int xqm) {
        return xqm == 3 ? 1 : (xqm == 12 ? 2 : 3);
    }

    /** 学年：9 月及以后算新学年起始年。 */
    public static int currentAcademicYear() {
        java.util.Calendar c = java.util.Calendar.getInstance();
        int y = c.get(java.util.Calendar.YEAR);
        int m = c.get(java.util.Calendar.MONTH) + 1;
        return m >= 9 ? y : y - 1;
    }

    /** 学期码：3=第一学期 / 12=第二学期 / 16=第三学期。 */
    public static int currentTermCode() {
        java.util.Calendar c = java.util.Calendar.getInstance();
        int m = c.get(java.util.Calendar.MONTH) + 1;
        if (m >= 9 || m <= 1) return 3;
        if (m <= 7) return 12;
        return 16;
    }

    private static JSONObject post(String xsdm, int year, int xqm, String cookie)
            throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(ENDPOINT).openConnection();
        conn.setRequestMethod("POST");
        conn.setConnectTimeout(15000);
        conn.setReadTimeout(20000);
        conn.setDoOutput(true);
        conn.setInstanceFollowRedirects(false);

        Map<String, String> headers = new HashMap<>();
        headers.put("User-Agent", UA);
        headers.put("X-Requested-With", "XMLHttpRequest");
        headers.put("Referer", ENTRY);
        headers.put("Content-Type", "application/x-www-form-urlencoded");
        for (Map.Entry<String, String> e : headers.entrySet()) {
            conn.setRequestProperty(e.getKey(), e.getValue());
        }
        if (cookie != null && !cookie.isEmpty()) {
            conn.setRequestProperty("Cookie", cookie);
        }

        StringBuilder body = new StringBuilder();
        body.append("xnm=").append(year);
        body.append("&xqm=").append(xqm);
        body.append("&kzlx=ck");
        body.append("&xsdm=").append(xsdm);
        body.append("&kclbdm=&kclxdm=");
        body.append("&queryModel.showCount=500");
        body.append("&queryModel.currentPage=1");

        try (OutputStream os = conn.getOutputStream()) {
            os.write(body.toString().getBytes(StandardCharsets.UTF_8));
        }

        int code = conn.getResponseCode();
        if (code != 200) {
            Log.w(TAG, "schedule POST " + xsdm + " -> HTTP " + code);
            return null;
        }
        String text = readAll(conn.getInputStream());
        if (text.isEmpty()) {
            Log.w(TAG, "schedule POST " + xsdm + " -> empty");
            return null;
        }
        return new JSONObject(text);
    }

    private static String readAll(InputStream in) throws Exception {
        try (BufferedReader r = new BufferedReader(
                new InputStreamReader(in, StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = r.readLine()) != null) sb.append(line);
            return sb.toString();
        }
    }
}
