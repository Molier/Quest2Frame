// SPDX-License-Identifier: GPL-3.0-only
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import org.json.JSONObject;

/** Read installed app labels as the ADB shell user; no APK installation needed. */
public final class QuestAppLabels {
    public static void main(String[] args) throws Exception {
        Class<?> threadClass = Class.forName("android.app.ActivityThread");
        Object thread = threadClass.getMethod("systemMain").invoke(null);
        Context context = (Context) threadClass.getMethod("getSystemContext").invoke(thread);
        PackageManager pm = context.createPackageContext("com.android.shell", 0).getPackageManager();
        JSONObject labels = new JSONObject();
        for (String name : args) {
            try {
                ApplicationInfo info = pm.getApplicationInfo(name, 0);
                labels.put(name, pm.getApplicationLabel(info).toString());
            } catch (PackageManager.NameNotFoundException ignored) {
                // Packages can disappear during a scan; the caller retains its ID.
            }
        }
        System.out.println("Q2F_LABELS=" + labels.toString());
        System.exit(0);
    }
}
