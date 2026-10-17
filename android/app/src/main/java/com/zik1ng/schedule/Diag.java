package com.zik1ng.schedule;

import android.util.Log;

import java.io.File;
import java.io.FileWriter;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * 日志：同时写 logcat 和手机存储里的日志文件。
 *
 * 文件位置（无需任何权限）：
 *   /Android/data/com.zik1ng.schedule/files/Download/wmu_schedule_log.txt
 *
 * 没有 USB 线时，用系统文件管理器进入上述路径即可取出，
 * 或用「文件」应用的「Android/data/com.zik1ng.schedule/files/Download/」找到。
 */
public final class Diag {
    private static final String TAG = "Zik1nG";
    private static final String FILE_NAME = "wmu_schedule_log.txt";
    private static final SimpleDateFormat FMT =
        new SimpleDateFormat("HH:mm:ss.SSS", Locale.US);

    private Diag() {}

    public static void d(String msg) {
        Log.d(TAG, msg);
        append(msg);
    }

    public static void e(String msg) {
        Log.e(TAG, msg);
        append(msg);
    }

    /** 带异常的错误日志。 */
    public static void e(String msg, Throwable t) {
        Log.e(TAG, msg, t);
        append(msg + " | " + t);
    }

    /** 每次启动时清空，避免日志无限增长。 */
    public static void clear() {
        try {
            logFile().delete();
        } catch (Exception ignored) { }
    }

    /** 日志内容（供界面直接显示/分享）。 */
    public static String readAll() {
        File f = logFile();
        if (!f.exists()) return "";
        try {
            byte[] buf = new byte[(int) f.length()];
            java.io.FileInputStream in = new java.io.FileInputStream(f);
            in.read(buf);
            in.close();
            return new String(buf, "UTF-8");
        } catch (Exception e) {
            return "";
        }
    }

    private static File logFile() {
        File dir = MainActivity.instance().getExternalFilesDir(
            android.os.Environment.DIRECTORY_DOWNLOADS);
        if (dir == null) {
            dir = MainActivity.instance().getFilesDir();
        }
        return new File(dir, FILE_NAME);
    }

    private static void append(String msg) {
        String line = FMT.format(new Date()) + " " + msg + "\n";
        FileWriter w = null;
        try {
            w = new FileWriter(logFile(), true);
            w.write(line);
            w.flush();
        } catch (Exception e) {
            Log.w(TAG, "log append failed", e);
        } finally {
            try {
                if (w != null) w.close();
            } catch (Exception ignored) { }
        }
    }
}
