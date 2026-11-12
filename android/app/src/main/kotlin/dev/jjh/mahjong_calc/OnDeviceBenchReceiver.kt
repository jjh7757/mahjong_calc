package dev.jjh.mahjong_calc

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/// 기기 판독 실험(exp/on-device-read) 측정 입구: adb 로만(보내는 쪽에 DUMP 권한 필요 — 셸·시스템) 부른다.
///   adb shell am broadcast -n dev.jjh.mahjong_calc.ondevice/dev.jjh.mahjong_calc.OnDeviceBenchReceiver                     (폴더만 만듦)
///   adb shell am broadcast -n dev.jjh.mahjong_calc.ondevice/dev.jjh.mahjong_calc.OnDeviceBenchReceiver --es manifest manifest_<tag>.json   (Python 판독만)
///   adb shell am broadcast -n dev.jjh.mahjong_calc.ondevice/dev.jjh.mahjong_calc.OnDeviceBenchReceiver --es flow flow_<tag>.json           (앱 흐름, Dart)
///   adb shell am broadcast -n dev.jjh.mahjong_calc.ondevice/dev.jjh.mahjong_calc.OnDeviceBenchReceiver --es track track_<tag>.json         (추적 분석 시간, Dart)
/// 앱을 앞에 띄워 둔 채로 부른다(수십 초 걸려 goAsync 시간 제한을 넘으므로 스레드만 띄우고 바로 돌아온다).
/// Python `ondevice.bench(manifest)` 가 목록의 사진을 서버와 같은 판독으로 읽고 결과 JSON 을 manifest 옆에 쓴다(logcat 태그 ondevice-bench).
class OnDeviceBenchReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val app = context.applicationContext
        // 앱 소유 외부 폴더(…/Android/data/<패키지>/files/bench)를 앱이 직접 만든다 — adb 셸이 만들면 셸 소유라 앱이 못 읽는다.
        val dir = app.getExternalFilesDir("bench") ?: return
        // 추적 분석(analyzeTableFrame) 시간: --es track track_<tag>.json (Dart, 앱이 앞에 떠 있어야 함).
        intent.getStringExtra("track")?.let { f ->
            val path = if (f.startsWith("/")) f else java.io.File(dir, f).absolutePath
            val ch = MainActivity.benchChannel ?: run {
                Log.e(TAG, "track failed: 앱 화면이 떠 있지 않음")
                return
            }
            android.os.Handler(android.os.Looper.getMainLooper()).post {
                ch.invokeMethod("track", path, object : io.flutter.plugin.common.MethodChannel.Result {
                    override fun success(result: Any?) { Log.i(TAG, "track done $result") }
                    override fun error(code: String, msg: String?, details: Any?) { Log.e(TAG, "track failed $code $msg") }
                    override fun notImplemented() { Log.e(TAG, "track failed notImplemented") }
                })
            }
            return
        }
        intent.getStringExtra("flow")?.let { f ->
            // 앱 흐름(Dart readGrid → 병합 → 점수)을 모드별로. 앱이 앞에 떠 있어야 한다.
            val path = if (f.startsWith("/")) f else java.io.File(dir, f).absolutePath
            val ch = MainActivity.benchChannel
            if (ch == null) {
                Log.e(TAG, "flow failed: 앱 화면이 떠 있지 않음")
                return
            }
            android.os.Handler(android.os.Looper.getMainLooper()).post {
                ch.invokeMethod("flow", path, object : io.flutter.plugin.common.MethodChannel.Result {
                    override fun success(result: Any?) {
                        Log.i(TAG, "flow done $result")
                    }

                    override fun error(code: String, msg: String?, details: Any?) {
                        Log.e(TAG, "flow failed $code $msg")
                    }

                    override fun notImplemented() {
                        Log.e(TAG, "flow failed notImplemented")
                    }
                })
            }
            return
        }
        val name = intent.getStringExtra("manifest")
        if (name == null) {
            Log.i(TAG, "ready ${dir.absolutePath}")
            return
        }
        val manifest = if (name.startsWith("/")) name else java.io.File(dir, name).absolutePath
        Thread({
            try {
                if (!Python.isStarted()) Python.start(AndroidPlatform(app))
                val out = Python.getInstance().getModule("ondevice").callAttr("bench", manifest).toString()
                Log.i(TAG, "done $out")
            } catch (e: Throwable) {
                Log.e(TAG, "failed", e)
            }
        }, "ondevice-bench").start()
    }

    companion object {
        const val TAG = "ondevice-bench"
    }
}
