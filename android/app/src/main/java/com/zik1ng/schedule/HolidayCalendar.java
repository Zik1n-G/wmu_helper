package com.zik1ng.schedule;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Date;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * 校历节假日引擎：内置 2026-2027 学年第一学期校历安排，
 * 在节假日/调休日提前 ADVANCE_DAYS 天生成铃铛通知。
 *
 * 教务系统课表接口不反映调休（按固定周次返回），
 * 中秋国庆停课、周末补课只写在校历里，所以本地内置。
 *
 * 数据来源：学校校历（README 与 src/wmu_jwxt/core/section_time.py
 * 的 CALENDAR_NOTES 同源）。新学年校历公布后更新 HOLIDAYS/MAKEUPS。
 */
public final class HolidayCalendar {
    /** 提前几天开始提醒 */
    static final int ADVANCE_DAYS = 7;

    /** 一天的毫秒数 */
    private static final long DAY_MS = 24L * 3600 * 1000;

    /**
     * 节假日：ISO 日期 → 名称。
     * 连续假期按整段列出（生成通知时归并为一段）。
     */
    private static final Map<String, String> HOLIDAYS = new LinkedHashMap<>();

    /** 调休补课：ISO 日期 → 说明（当天上的是哪天的课） */
    private static final Map<String, String> MAKEUPS = new LinkedHashMap<>();

    static {
        // 中秋节 2026/9/25(五)-9/27(日)
        HOLIDAYS.put("2026-09-25", "中秋节");
        HOLIDAYS.put("2026-09-26", "中秋节");
        HOLIDAYS.put("2026-09-27", "中秋节");
        // 国庆节 2026/10/1(四)-10/7(三)
        HOLIDAYS.put("2026-10-01", "国庆节");
        HOLIDAYS.put("2026-10-02", "国庆节");
        HOLIDAYS.put("2026-10-03", "国庆节");
        HOLIDAYS.put("2026-10-04", "国庆节");
        HOLIDAYS.put("2026-10-05", "国庆节");
        HOLIDAYS.put("2026-10-06", "国庆节");
        HOLIDAYS.put("2026-10-07", "国庆节");
        // 元旦 2027/1/1(五)
        HOLIDAYS.put("2027-01-01", "元旦");
        // 寒假（学期结束后，仅提醒无需换课）
        HOLIDAYS.put("2027-01-18", "寒假开始");
        HOLIDAYS.put("2027-01-19", "寒假");
        HOLIDAYS.put("2027-02-28", "寒假");
        // 清明 2027/4/3-4/5（周六上班上学可能，先按官方放假日）
        HOLIDAYS.put("2027-04-03", "清明节");
        HOLIDAYS.put("2027-04-04", "清明节");
        HOLIDAYS.put("2027-04-05", "清明节");
        // 劳动节 2027/5/1(六)-5/5(三)
        HOLIDAYS.put("2027-05-01", "劳动节");
        HOLIDAYS.put("2027-05-02", "劳动节");
        HOLIDAYS.put("2027-05-03", "劳动节");
        HOLIDAYS.put("2027-05-04", "劳动节");
        HOLIDAYS.put("2027-05-05", "劳动节");
        // 端午 2027/6/9(三)
        HOLIDAYS.put("2027-06-09", "端午节");

        // 调休补课（校历规定）
        MAKEUPS.put("2026-10-06", "补 9月26日(周六) 的课");   // 周二
        MAKEUPS.put("2026-10-10", "补 9月27日(周日) 的课");   // 周六
    }

    private HolidayCalendar() {}

    /** 日期 → 星期几（1=周一 … 7=周日），供 UI 显示 */
    static int weekdayOf(String iso) {
        try {
            SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd", Locale.CHINA);
            Calendar c = Calendar.getInstance();
            c.setTime(f.parse(iso));
            int w = c.get(Calendar.DAY_OF_WEEK);   // 1=周日 … 7=周六
            return w == 1 ? 7 : w - 1;
        } catch (Exception e) {
            return 0;
        }
    }

    /** 今天（本地时区）的 ISO 日期 */
    static String todayIso() {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.CHINA)
            .format(new Date());
    }

    /** a - b 的天数差（按日期，不含时分） */
    static int daysBetween(String isoA, String isoB) {
        try {
            SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd", Locale.CHINA);
            long a = f.parse(isoA).getTime();
            long b = f.parse(isoB).getTime();
            return (int) Math.round((a - b) / (double) DAY_MS);
        } catch (Exception e) {
            return Integer.MAX_VALUE;
        }
    }

    /**
     * 把连续同名节假日归并成一段：返回 [起始ISO, 结束ISO, 名称] 列表。
     */
    private static List<String[]> mergeRanges() {
        List<String[]> ranges = new ArrayList<>();
        String start = null, end = null, name = null;
        for (Map.Entry<String, String> e : HOLIDAYS.entrySet()) {
            String d = e.getKey();
            String n = e.getValue();
            if (name != null && n.equals(name) && daysBetween(d, end) == 1) {
                end = d;   // 连续同名：延长当前段
            } else {
                if (name != null) ranges.add(new String[]{start, end, name});
                start = d; end = d; name = n;
            }
        }
        if (name != null) ranges.add(new String[]{start, end, name});
        return ranges;
    }

    /** 10月1日 → "10月1日"；1月1日 → "1月1日"（去年份，通知文案用） */
    private static String shortDate(String iso) {
        return iso.substring(5).replace("-", "月") + "日";
    }

    /**
     * 生成今天应存在的通知列表（不查已读状态，只管生成）。
     * 通知在事件前 ADVANCE_DAYS 天内开始出现，永久保留（由存储层按 id 去重）。
     *
     * @param now 当前毫秒时间戳（通知显示时间精确到分钟，用这个）
     */
    static List<JSONObject> generateToday(long now) throws Exception {
        SimpleDateFormat dayFmt = new SimpleDateFormat("yyyy-MM-dd", Locale.CHINA);
        SimpleDateFormat timeFmt = new SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.CHINA);
        String today = dayFmt.format(new Date(now));
        String stamp = timeFmt.format(new Date(now));   // 通知生成时间，精确到分钟
        List<JSONObject> list = new ArrayList<>();

        // 1) 节假日段：进入提醒窗口（今天 >= 起始-7天）即生成
        for (String[] r : mergeRanges()) {
            int offset = daysBetween(r[0], today);   // 段首-今天（正=未来，负=已开始）
            if (offset > ADVANCE_DAYS) continue;
            JSONObject n = new JSONObject();
            n.put("id", "hol-" + r[0]);
            n.put("type", "holiday");
            String range = r[0].equals(r[1])
                ? shortDate(r[0])
                : shortDate(r[0]) + " - " + shortDate(r[1]);
            if (offset > 0) {
                n.put("title", r[2] + "放假提醒（" + offset + "天后）");
            } else if (offset == 0) {
                n.put("title", r[2] + "今天开始放假");
            } else {
                // 假期进行中/已结束：仍保留，标题去掉倒计时
                n.put("title", r[2] + "放假（" + range + "）");
            }
            n.put("content", range + "放假。"
                + (r[2].contains("寒假") ? "假期愉快！" : "注意调休安排，别忘带课本。"));
            n.put("date", stamp);
            n.put("target", r[0]);
            list.add(n);
        }

        // 2) 调休补课日：提前 ADVANCE_DAYS 天内生成，重点提醒换课
        for (Map.Entry<String, String> e : MAKEUPS.entrySet()) {
            String d = e.getKey();
            int offset = daysBetween(d, today);   // 补课日-今天：正=未来
            if (offset > ADVANCE_DAYS) continue;
            JSONObject n = new JSONObject();
            n.put("id", "mk-" + d);
            n.put("type", "makeup");
            String wd = "周" + "一二三四五六日".charAt(weekdayOf(d) - 1);
            String tail = offset > 0 ? "（" + offset + "天后）" : offset == 0 ? "（今天）" : "";
            n.put("title", "节假日换课提醒" + tail);
            n.put("content", d.replace("-", "月") + "日" + wd + " " + e.getValue()
                + "。当天按被补日期的课表上课，注意别走错教室。");
            n.put("date", stamp);
            n.put("target", d);
            list.add(n);
        }

        return list;
    }
}
