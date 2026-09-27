// SPDX-License-Identifier: GPL-3.0-only
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import org.json.JSONObject;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.Drawable;
import android.util.Base64;
import java.io.ByteArrayOutputStream;

/** Read installed app labels as the ADB shell user; no APK installation needed. */
public final class QuestAppLabels {
    public static void main(String[] args) throws Exception {
        android.os.Looper.prepareMainLooper();
        Class<?> threadClass = Class.forName("android.app.ActivityThread");
        Object thread = threadClass.getMethod("systemMain").invoke(null);
        Context context = (Context) threadClass.getMethod("getSystemContext").invoke(thread);
        PackageManager pm = context.createPackageContext("com.android.shell", 0).getPackageManager();
        JSONObject labels = new JSONObject();
        for (String name : args) {
            try {
                ApplicationInfo info = pm.getApplicationInfo(name, 0);
                labels.put(name, pm.getApplicationLabel(info).toString());
                try {
                    Drawable icon = pm.getApplicationIcon(info);
                    Bitmap bitmap = Bitmap.createBitmap(48, 48, Bitmap.Config.ARGB_8888);
                    icon.setBounds(0, 0, 48, 48);
                    icon.draw(new Canvas(bitmap));
                    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                    bitmap.compress(Bitmap.CompressFormat.PNG, 100, bytes);
                    bitmap.recycle();
                    JSONObject record = new JSONObject();
                    record.put("package", name);
                    record.put("icon", Base64.encodeToString(bytes.toByteArray(), Base64.NO_WRAP));
                    System.out.println("Q2F_ICON=" + record.toString());
                } catch (Exception ignored) {
                    // An unreadable icon must not hide an otherwise valid app.
                }
            } catch (PackageManager.NameNotFoundException ignored) {
                // Packages can disappear during a scan; the caller retains its ID.
            }
        }
        System.out.println("Q2F_LABELS=" + labels.toString());
        System.exit(0);
    }
}
