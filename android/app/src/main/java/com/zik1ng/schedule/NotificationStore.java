package com.zik1ng.schedule;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

import java.util.List;

/**
 * 通知存储：notifications.json 永久保存在应用私有目录。
 *
 * 规则：
 *   - 校历生成的通知按 id 去重合并（已有的保留原已读状态，
 *     新生成的插入到最上面）
 *   - 被删除的通知 id 记入墓碑（notifications_deleted.json），
 *     重启后校历同步不再复活它们
 *   - 未读数 > 0 时铃铛显示红点
 *   - 只能删除已读通知（未读的必须先点开看掉）
 */
public final class NotificationStore {
    private static final String FILE = "notifications.json";
    /** 删除墓碑：记录被删通知的 id，防止校历同步时复活 */
    private static final String TOMB_FILE = "notifications_deleted.json";

    private NotificationStore() {}

    private static File file(Context ctx) {
        return new File(ctx.getFilesDir(), FILE);
    }

    private static File tombFile(Context ctx) {
        return new File(ctx.getFilesDir(), TOMB_FILE);
    }

    /** 读墓碑 id 列表 */
    private static synchronized JSONArray loadTombs(Context ctx) {
        File f = tombFile(ctx);
        if (!f.exists()) return new JSONArray();
        try (FileInputStream in = new FileInputStream(f);
             InputStreamReader r = new InputStreamReader(in, StandardCharsets.UTF_8);
             BufferedReader br = new BufferedReader(r)) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
            if (sb.length() == 0) return new JSONArray();
            return new JSONArray(sb.toString());
        } catch (Exception e) {
            return new JSONArray();
        }
    }

    private static synchronized void saveTombs(Context ctx, JSONArray arr) {
        try (FileOutputStream out = new FileOutputStream(tombFile(ctx));
             OutputStreamWriter w = new OutputStreamWriter(out, StandardCharsets.UTF_8)) {
            w.write(arr.toString());
            w.flush();
        } catch (Exception e) {
            Diag.e("tomb save failed", e);
        }
    }

    private static boolean inTombs(JSONArray tombs, String id) {
        for (int i = 0; i < tombs.length(); i++) {
            if (tombs.optString(i).equals(id)) return true;
        }
        return false;
    }

    private static synchronized JSONArray load(Context ctx) {
        File f = file(ctx);
        if (!f.exists()) return new JSONArray();
        try (FileInputStream in = new FileInputStream(f);
             InputStreamReader r = new InputStreamReader(in, StandardCharsets.UTF_8);
             BufferedReader br = new BufferedReader(r)) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
            if (sb.length() == 0) return new JSONArray();
            return new JSONArray(sb.toString());
        } catch (Exception e) {
            Diag.e("notif load failed", e);
            return new JSONArray();
        }
    }

    private static synchronized void save(Context ctx, JSONArray arr) {
        try (FileOutputStream out = new FileOutputStream(file(ctx));
             OutputStreamWriter w = new OutputStreamWriter(out, StandardCharsets.UTF_8)) {
            w.write(arr.toString());
            w.flush();
        } catch (Exception e) {
            Diag.e("notif save failed", e);
        }
    }

    /**
     * 把校历今天生成的通知合并进存储（去重：同 id 不重复插入）。
     * 新通知插到最上面，保持"新的在上"。
     */
    static synchronized void syncFromCalendar(Context ctx, List<JSONObject> fresh)
            throws Exception {
        JSONArray arr = load(ctx);
        JSONArray tombs = loadTombs(ctx);
        boolean changed = false;
        for (JSONObject n : fresh) {
            String id = n.optString("id");
            boolean exists = false;
            for (int i = 0; i < arr.length(); i++) {
                if (arr.optJSONObject(i).optString("id").equals(id)) {
                    exists = true;
                    break;
                }
            }
            if (exists) continue;
            // 墓碑里的（用户删过）不复活
            if (inTombs(tombs, id)) continue;
            n.put("read", false);
            arr.put(n);          // 追加
            changed = true;
        }
        if (changed) {
            // 新的在上面：按 date 倒序 + id 稳定排序
            sortNewestFirst(arr);
            save(ctx, arr);
        }
    }

    /** 全部通知（新的在上），给 JS 显示 */
    static synchronized String getAll(Context ctx) {
        JSONArray arr = load(ctx);
        // 运行时也保证一次顺序（旧数据可能乱序）
        sortNewestFirst(arr);
        return arr.toString();
    }

    private static void sortNewestFirst(JSONArray arr) {
        // 选择排序足够（通知量 < 20）
        for (int i = 0; i < arr.length() - 1; i++) {
            int max = i;
            for (int j = i + 1; j < arr.length(); j++) {
                if (compare(arr.optJSONObject(j), arr.optJSONObject(max)) > 0) max = j;
            }
            if (max != i) {
                try {
                    JSONObject tmp = arr.getJSONObject(i);
                    arr.put(i, arr.get(max));
                    arr.put(max, tmp);
                } catch (Exception ignore) {}
            }
        }
    }

    /** date 倒序；date 相同按 id 倒序（稳定性） */
    private static int compare(JSONObject a, JSONObject b) {
        int c = a.optString("date").compareTo(b.optString("date"));
        if (c != 0) return c;
        return a.optString("id").compareTo(b.optString("id"));
    }

    /** 未读数（>0 显示红点） */
    static synchronized int unreadCount(Context ctx) {
        JSONArray arr = load(ctx);
        int n = 0;
        for (int i = 0; i < arr.length(); i++) {
            if (!arr.optJSONObject(i).optBoolean("read")) n++;
        }
        return n;
    }

    /** 标记已读（点开详情后调用） */
    static synchronized boolean markRead(Context ctx, String id) throws Exception {
        JSONArray arr = load(ctx);
        for (int i = 0; i < arr.length(); i++) {
            JSONObject n = arr.optJSONObject(i);
            if (n.optString("id").equals(id) && !n.optBoolean("read")) {
                n.put("read", true);
                save(ctx, arr);
                return true;
            }
        }
        return false;
    }

    /**
     * 只删除已读的通知；返回被删数量。
     * 未读的删不掉（先点开看掉）。被删的 id 记入墓碑，
     * 防止下次启动校历同步时复活。
     */
    static synchronized int deleteRead(Context ctx) {
        JSONArray arr = load(ctx);
        JSONArray kept = new JSONArray();
        JSONArray tombs = loadTombs(ctx);
        int removed = 0;
        for (int i = 0; i < arr.length(); i++) {
            JSONObject n = arr.optJSONObject(i);
            if (n.optBoolean("read")) {
                removed++;
                String id = n.optString("id");
                if (!inTombs(tombs, id)) tombs.put(id);
            } else {
                kept.put(n);
            }
        }
        if (removed > 0) {
            save(ctx, kept);
            saveTombs(ctx, tombs);
        }
        return removed;
    }
}
