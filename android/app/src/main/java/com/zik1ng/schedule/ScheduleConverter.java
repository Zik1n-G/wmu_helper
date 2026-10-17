package com.zik1ng.schedule;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * 教务系统课表 JSON → 界面周视图 JSON（与桌面端 parsers/schedule.py 逻辑一致）。
 *
 * 关键点：
 *   - 六类课表合并后的 kbList，按 (jxb_id, jc, zcd, cdmc) 去重
 *   - 周次字段 zcd 多格式："1-16周" / "3周,6周" / "8-10周(双)" / "第7周" / 混合段
 *   - 节次 jc 超出 1-15 的是实践课工位号（如 "9-16节"），当无固定节次处理
 *   - 节次时间按校区取表（茶山/滨海两套，来自学校校历）
 *   - sjkList（通识选修课）并入，无固定上课时间
 */
public final class ScheduleConverter {
    private ScheduleConverter() {}

    /* 茶山校区节次表（校历） */
    private static final String[][] CHASHAN = {
        {"08:00", "08:40"}, {"08:45", "09:25"}, {"09:40", "10:20"},
        {"10:25", "11:05"}, {"11:10", "11:50"}, {"11:55", "12:35"},
        {"12:40", "13:20"}, {"13:30", "14:10"}, {"14:15", "14:55"},
        {"15:40", "16:20"}, {"16:25", "17:05"}, {"18:20", "19:00"},
        {"19:05", "19:45"}, {"20:10", "20:50"}, {"19:05", "19:45"},
    };

    /* 滨海校区节次表（校历） */
    private static final String[][] BINHAI = {
        {"08:30", "09:10"}, {"09:15", "09:55"}, {"10:10", "10:50"},
        {"10:55", "11:35"}, {"11:40", "12:20"}, {"12:25", "13:05"},
        {"13:05", "13:45"}, {"13:30", "14:10"}, {"14:15", "14:55"},
        {"15:00", "15:40"}, {"15:45", "16:25"}, {"16:30", "17:10"},
        {"17:15", "17:55"}, {"18:00", "19:00"}, {"19:05", "19:45"},
    };

    private static final int MAX_SECTION = 15;

    public static String toWeekView(JSONObject payload, int year, int term) throws Exception {
        JSONArray kbList = payload.optJSONArray("kbList");
        if (kbList == null) kbList = new JSONArray();
        JSONArray sjkList = payload.optJSONArray("sjkList");
        if (sjkList == null) sjkList = new JSONArray();

        List<JSONObject> courses = new ArrayList<>();
        Map<String, Boolean> seen = new HashMap<>();

        for (int i = 0; i < kbList.length(); i++) {
            JSONObject item = kbList.optJSONObject(i);
            if (item == null) continue;
            String key = item.optString("jxb_id") + "|" + item.optString("jc")
                + "|" + item.optString("zcd") + "|" + item.optString("cdmc");
            if (seen.containsKey(key)) continue;
            seen.put(key, Boolean.TRUE);

            String jc = item.optString("jc");
            String campus = item.optString("xqmc");
            int[] sec = parseSections(jc);

            JSONObject c = new JSONObject();
            c.put("course_id", item.optString("kch_id", item.optString("kch")));
            c.put("title", item.optString("kcmc"));
            c.put("teacher", item.optString("xm"));
            c.put("class_name", item.optString("jxbmc"));
            c.put("credit", item.optString("xf"));
            c.put("weekday", parseInt(item.optString("xqj")));
            c.put("sections", jc);
            c.put("section_start", sec[0]);
            c.put("section_end", sec[1]);
            c.put("weeks_raw", item.optString("zcd"));
            c.put("weeks", new JSONArray(parseWeeks(item.optString("zcd"))));
            c.put("evaluation_mode", item.optString("khfsmc"));
            c.put("campus", campus);
            c.put("place", item.optString("cdmc"));
            c.put("weekly_hours", item.optString("zhxs"));
            c.put("total_hours", item.optString("zxs"));
            c.put("is_elective", false);
            c.put("time_text", sectionTimeText(jc, campus, sec));
            courses.add(c);
        }

        /* 选修课（sjkList）：无固定上课时间，weekday=0 */
        for (int i = 0; i < sjkList.length(); i++) {
            JSONObject item = sjkList.optJSONObject(i);
            if (item == null) continue;
            String detail = item.optString("qtkcgs", item.optString("sjkcgs"));
            String teacher = "";
            String platform = "";
            if (detail.contains("◆")) {
                String seg = detail.substring(detail.indexOf("◆") + 1);
                int p = seg.indexOf('(');
                teacher = (p > 0 ? seg.substring(0, p) : seg).trim();
                int slash = detail.lastIndexOf('/');
                if (slash >= 0) {
                    String tail = detail.substring(slash + 1).trim();
                    if (!tail.isEmpty() && !tail.contains("周")) platform = tail;
                }
            }
            JSONObject c = new JSONObject();
            c.put("course_id", "");
            c.put("title", item.optString("kcmc"));
            c.put("teacher", teacher);
            c.put("class_name", "");
            c.put("credit", item.optString("xf"));
            c.put("weekday", 0);
            c.put("sections", "");
            c.put("section_start", 0);
            c.put("section_end", 0);
            c.put("weeks_raw", item.optString("qsjsz"));
            c.put("weeks", new JSONArray(parseWeeks(item.optString("qsjsz"))));
            c.put("evaluation_mode", "");
            c.put("campus", item.optString("xqmc"));
            c.put("place", platform.isEmpty()
                ? (item.optString("kklxdm").equals("10") ? "网络课程" : item.optString("kklxdm"))
                : platform);
            c.put("weekly_hours", "");
            c.put("total_hours", "");
            c.put("category", item.optString("kclb", "通识选修课"));
            c.put("is_elective", true);
            c.put("note", detail);
            courses.add(c);
        }

        /* 总周数 */
        int total = 0;
        for (JSONObject c : courses) {
            JSONArray ws = c.optJSONArray("weeks");
            if (ws == null) continue;
            for (int i = 0; i < ws.length(); i++) total = Math.max(total, ws.optInt(i));
        }

        /* 按周展开：weeks[w]["0"] 放选修课 */
        Map<String, Map<String, List<JSONObject>>> weeks = new TreeMap<>();
        for (int w = 1; w <= total; w++) {
            Map<String, List<JSONObject>> days = new HashMap<>();
            for (int d = 0; d <= 7; d++) days.put(String.valueOf(d), new ArrayList<JSONObject>());
            weeks.put(String.valueOf(w), days);
        }
        for (JSONObject c : courses) {
            JSONArray ws = c.optJSONArray("weeks");
            if (ws == null) continue;
            for (int i = 0; i < ws.length(); i++) {
                Map<String, List<JSONObject>> days = weeks.get(String.valueOf(ws.optInt(i)));
                if (days != null) {
                    days.get(String.valueOf(c.optInt("weekday"))).add(c);
                }
            }
        }

        JSONObject xsxx = payload.optJSONObject("xsxx");
        JSONObject student = new JSONObject();
        if (xsxx != null) {
            student.put("sid", xsxx.optString("XH"));
            student.put("name", xsxx.optString("XM"));
            student.put("class_name", xsxx.optString("BJMC"));
        } else {
            student.put("sid", "").put("name", "").put("class_name", "");
        }

        /* 学期第一周周一：优先读配置的校历基准（term_start），
           否则按惯例取秋学期 9 月第一个周一。 */
        long startMs = termStartMs(year, term);

        /* 当前教学周（周一刷新由界面侧的 today 字段负责，这里只算今天在第几周） */
        long todayMs = System.currentTimeMillis();
        int currentWeek = (int) ((todayMs - startMs) / (7L * 24 * 3600 * 1000)) + 1;
        if (currentWeek < 1) currentWeek = 1;
        if (currentWeek > total) currentWeek = total > 0 ? total : 1;

        /* 组装（界面直接消费） */
        JSONObject out = new JSONObject();
        out.put("student", student);
        out.put("year", year);
        out.put("term", term);
        out.put("count", courses.size());
        out.put("total_weeks", total);
        out.put("current_week", currentWeek);

        JSONObject weekDates = new JSONObject();
        JSONObject weekMonths = new JSONObject();
        JSONObject weeksOut = new JSONObject();
        for (Map.Entry<String, Map<String, List<JSONObject>>> e : weeks.entrySet()) {
            int w = Integer.parseInt(e.getKey());
            JSONObject daysOut = new JSONObject();
            for (Map.Entry<String, List<JSONObject>> d : e.getValue().entrySet()) {
                daysOut.put(d.getKey(), new JSONArray(d.getValue()));
            }
            weeksOut.put(e.getKey(), daysOut);

            java.util.Calendar mc = java.util.Calendar.getInstance();
            mc.setTimeInMillis(startMs + (long) (w - 1) * 7 * 24 * 3600 * 1000);
            weekDates.put(e.getKey(),
                String.format("%02d-%02d",
                    mc.get(java.util.Calendar.MONTH) + 1,
                    mc.get(java.util.Calendar.DAY_OF_MONTH)));
            weekMonths.put(e.getKey(), mc.get(java.util.Calendar.MONTH) + 1);
        }
        out.put("week_dates", weekDates);
        out.put("week_months", weekMonths);
        out.put("weeks", weeksOut);

        /* 今天在学期里的位置（界面据此高亮"本周"和当日胶囊） */
        JSONObject today = new JSONObject();
        java.util.Calendar tc = java.util.Calendar.getInstance();
        int tw = (int) ((todayMs - startMs) / (7L * 24 * 3600 * 1000)) + 1;
        today.put("today_iso", String.format("%04d-%02d-%02d",
            tc.get(java.util.Calendar.YEAR),
            tc.get(java.util.Calendar.MONTH) + 1,
            tc.get(java.util.Calendar.DAY_OF_MONTH)));
        today.put("today_weekday", tw > 0 && tw <= total
            ? ((tc.get(java.util.Calendar.DAY_OF_WEEK) + 5) % 7) + 1 : 0);
        today.put("today_week", (tw >= 1 && tw <= total) ? tw : 0);
        today.put("in_term", tw >= 1 && tw <= total);
        out.put("today", today);

        /* 节次时间表（纵轴用） */
        JSONObject tables = new JSONObject();
        tables.put("default", timesToJson(CHASHAN, true));
        tables.put("binhai", timesToJson(BINHAI, true));
        out.put("section_tables", tables);

        return out.toString();
    }

    /** 学期第一周周一的时间戳。配置来源：filesDir/term_start.txt（ISO 日期）。 */
    private static long termStartMs(int year, int term) {
        String cfg = readTermStartConfig();
        if (cfg != null) {
            try {
                java.util.Calendar c = parseIso(cfg);
                int dow = c.get(java.util.Calendar.DAY_OF_WEEK);
                c.add(java.util.Calendar.DAY_OF_MONTH, -((dow + 5) % 7));   // 归到当周周一
                return c.getTimeInMillis();
            } catch (Exception ignored) { }
        }
        java.util.Calendar cal = java.util.Calendar.getInstance();
        cal.set(year, term == 1 ? 8 : 2, 1);
        int dow = cal.get(java.util.Calendar.DAY_OF_WEEK);
        cal.add(java.util.Calendar.DAY_OF_MONTH, -((dow + 5) % 7));
        return cal.getTimeInMillis();
    }

    private static String readTermStartConfig() {
        try {
            File f = new File(context().getFilesDir(), "term_start.txt");
            if (!f.exists()) return null;
            java.io.FileInputStream in = new java.io.FileInputStream(f);
            byte[] buf = new byte[in.available()];
            in.read(buf);
            in.close();
            String s = new String(buf, StandardCharsets.UTF_8).trim();
            return s.isEmpty() ? null : s;
        } catch (Exception e) {
            return null;
        }
    }

    private static java.util.Calendar parseIso(String iso) {
        String[] p = iso.split("-");
        java.util.Calendar c = java.util.Calendar.getInstance();
        c.set(Integer.parseInt(p[0]), Integer.parseInt(p[1]) - 1, Integer.parseInt(p[2]),
            0, 0, 0);
        c.set(java.util.Calendar.MILLISECOND, 0);
        return c;
    }

    private static android.content.Context context() {
        return MainActivity.instance();
    }

    private static JSONObject timesToJson(String[][] table, boolean startOnly) throws Exception {
        JSONObject o = new JSONObject();
        for (int i = 0; i < table.length; i++) {
            o.put(String.valueOf(i + 1), startOnly ? table[i][0] : table[i][1]);
        }
        return o;
    }

    /* ---------------- 解析工具 ---------------- */

    private static int parseInt(String s) {
        try {
            return Integer.parseInt(s.trim());
        } catch (Exception e) {
            return 0;
        }
    }

    /** "3-5节" -> [3,5]；超出 1-15（实践课工位号）-> [0,0]。 */
    private static int[] parseSections(String jc) {
        if (jc == null || jc.isEmpty()) return new int[]{0, 0};
        String s = jc.replace("节", "").trim();
        int dash = s.indexOf('-');
        try {
            if (dash > 0) {
                int lo = Integer.parseInt(s.substring(0, dash).trim());
                int hi = Integer.parseInt(s.substring(dash + 1).trim());
                if (lo < 1 || lo > MAX_SECTION || hi < 1 || hi > MAX_SECTION) {
                    return new int[]{0, 0};
                }
                return new int[]{lo, hi};
            }
            int v = Integer.parseInt(s);
            return (v >= 1 && v <= MAX_SECTION) ? new int[]{v, v} : new int[]{0, 0};
        } catch (Exception e) {
            return new int[]{0, 0};
        }
    }

    /** 周次多格式解析，返回升序去重的周次列表。 */
    private static List<Integer> parseWeeks(String zcd) {
        List<Integer> weeks = new ArrayList<>();
        if (zcd == null || zcd.isEmpty()) return weeks;
        String text = zcd.replace("第", "").trim();
        for (String part : text.split(",")) {
            part = part.trim();
            if (part.isEmpty()) continue;
            boolean evenOnly = part.contains("双");
            boolean oddOnly = part.contains("单") && !evenOnly;
            String p = part.replace("周", "").replace("(", "").replace(")", "")
                .replace("双", "").replace("单", "").trim();
            if (p.isEmpty()) continue;
            int dash = p.indexOf('-');
            if (dash > 0) {
                try {
                    int lo = Integer.parseInt(p.substring(0, dash).trim());
                    int hi = Integer.parseInt(p.substring(dash + 1).trim());
                    if (lo > hi) { int t = lo; lo = hi; hi = t; }
                    for (int w = lo; w <= hi; w++) {
                        if (evenOnly && w % 2 != 0) continue;
                        if (oddOnly && w % 2 == 0) continue;
                        weeks.add(w);
                    }
                } catch (Exception ignored) { }
            } else {
                try {
                    weeks.add(Integer.parseInt(p));
                } catch (Exception ignored) { }
            }
        }
        Collections.sort(weeks);
        return weeks;
    }

    /** 按校区取节次表，返回 "10:10-12:20" 这样的时间段。 */
    private static String sectionTimeText(String jc, String campus, int[] sec) {
        if (sec[0] == 0 || sec[1] == 0) return "";
        String[][] table = (campus != null && campus.contains("滨海")) ? BINHAI : CHASHAN;
        if (sec[0] > table.length || sec[1] > table.length) return "";
        return table[sec[0] - 1][0] + "-" + table[sec[1] - 1][1];
    }
}
