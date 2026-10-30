package dev.jjh.mahjong_calc

import android.content.ContentValues
import android.os.Build
import android.provider.MediaStore
import android.view.KeyEvent
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/// 두 가지 네이티브 보조.
/// 1) 볼륨키: 거치 촬영 모드에서 볼륨키(블루투스 셀카 리모컨)를 촬영 버튼으로 쓴다.
///    Flutter 의 Focus/onKeyEvent 로는 Android 볼륨키가 오지 않아(시스템 볼륨 UI 가 가로챔) 여기서 받는다.
///    Flutter 쪽이 setCapture(true) 를 보낸 동안만 가로채고, 아니면 평소처럼 볼륨이 바뀐다.
/// 2) 파일 저장: 촬영 기록을 Download/mahjong_calc/... 에 MediaStore 로 쓴다(권한 불필요, API 29+).
/// 3) 화면 켜 두기: 카메라 헤드 모드에서 화면이 꺼지지 않게 FLAG_KEEP_SCREEN_ON 을 켠다.
/// 4) 카메라 헤드 카메라(HeadCamera): 셔터 없이 미리보기 + 12MP YUV 스트림. start/stop/setZoom/jpeg.
class MainActivity : FlutterActivity() {
    private var volumeChannel: MethodChannel? = null
    private var capture = false
    private var headCamera: HeadCamera? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val messenger = flutterEngine.dartExecutor.binaryMessenger
        MethodChannel(messenger, HEAD_CHANNEL).setMethodCallHandler { call, result ->
            val head = headCamera ?: HeadCamera(this, flutterEngine.renderer).also { headCamera = it }
            fun reply(r: Result<Map<String, Any?>>) = runOnUiThread {
                r.fold({ result.success(it) }, { result.error("HEAD", it.toString(), null) })
            }
            when (call.method) {
                "start" -> head.start(call.argument<Double>("zoom") ?: 1.0, ::reply)
                "stop" -> {
                    head.stop()
                    result.success(null)
                }
                "setZoom" -> result.success(head.setZoom(call.argument<Double>("zoom") ?: 1.0))
                "jpeg" -> head.jpeg(
                    call.argument<Int>("longSide"),
                    call.argument<Int>("quality") ?: 75,
                    call.argument<Boolean>("fresh") ?: false,
                    ::reply,
                )
                else -> result.notImplemented()
            }
        }
        volumeChannel = MethodChannel(messenger, VOLUME_CHANNEL).also { ch ->
            ch.setMethodCallHandler { call, result ->
                when (call.method) {
                    "setCapture" -> {
                        capture = call.arguments as? Boolean ?: false
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
        }
        MethodChannel(messenger, SCREEN_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "keepOn" -> {
                    val on = call.arguments as? Boolean ?: false
                    if (on) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
        MethodChannel(messenger, FILES_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "save" -> {
                    val dir = call.argument<String>("dir")
                    val name = call.argument<String>("name")
                    val bytes = call.argument<ByteArray>("bytes")
                    val mime = call.argument<String>("mime") ?: "application/octet-stream"
                    val overwrite = call.argument<Boolean>("overwrite") ?: false
                    if (dir == null || name == null || bytes == null) {
                        result.error("ARG", "dir/name/bytes 필요", null)
                    } else {
                        Thread {
                            try {
                                val uri = saveToDownloads(dir, name, bytes, mime, overwrite)
                                runOnUiThread { result.success(uri) }
                            } catch (e: Exception) {
                                runOnUiThread { result.error("SAVE", e.toString(), null) }
                            }
                        }.start()
                    }
                }
                else -> result.notImplemented()
            }
        }
    }

    /// Download/<dir> 에 파일을 쓴다. 같은 이름이 있으면 MediaStore 가 (1) 을 붙인다.
    /// [overwrite] 면 이 앱이 만든 같은 이름 파일을 덮어쓴다(track.json 처럼 저장할 때마다 전체를 다시 쓰는 파일,
    /// 2026-10-30: 사본이 29분에 31개 쌓였다). 못 찾거나 덮어쓰기가 거부되면(재설치로 소유권이 빠짐) 새 파일로 쓴다.
    private fun saveToDownloads(dir: String, name: String, bytes: ByteArray, mime: String, overwrite: Boolean): String {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            throw IllegalStateException("Android 10 미만은 지원하지 않음")
        }
        val rel = dir.trimEnd('/') + "/"
        if (overwrite) {
            val existing = findDownload(rel, name)
            if (existing != null) {
                try {
                    contentResolver.openOutputStream(existing, "wt")?.use { it.write(bytes) }
                        ?: throw IllegalStateException("openOutputStream 실패")
                    return existing.toString()
                } catch (_: SecurityException) {
                    // 이 앱 소유가 아님(재설치 전 파일) → 아래에서 새로 만든다.
                }
            }
        }
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, name)
            put(MediaStore.MediaColumns.MIME_TYPE, mime)
            put(MediaStore.MediaColumns.RELATIVE_PATH, rel)
        }
        val resolver = contentResolver
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: throw IllegalStateException("MediaStore insert 실패")
        resolver.openOutputStream(uri)?.use { it.write(bytes) }
            ?: throw IllegalStateException("openOutputStream 실패")
        return uri.toString()
    }

    /// Download/<rel><name> 의 MediaStore 주소(이 앱이 볼 수 있는 것 중 가장 최근), 없으면 null.
    private fun findDownload(rel: String, name: String): android.net.Uri? {
        val col = MediaStore.Downloads.EXTERNAL_CONTENT_URI
        contentResolver.query(
            col,
            arrayOf(MediaStore.MediaColumns._ID),
            "${MediaStore.MediaColumns.RELATIVE_PATH}=? AND ${MediaStore.MediaColumns.DISPLAY_NAME}=?",
            arrayOf(rel, name),
            "${MediaStore.MediaColumns.DATE_MODIFIED} DESC",
        )?.use { c ->
            if (c.moveToFirst()) return android.content.ContentUris.withAppendedId(col, c.getLong(0))
        }
        return null
    }

    private fun isVolume(keyCode: Int) =
        keyCode == KeyEvent.KEYCODE_VOLUME_UP || keyCode == KeyEvent.KEYCODE_VOLUME_DOWN

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (capture && isVolume(keyCode)) {
            if (event == null || event.repeatCount == 0) volumeChannel?.invokeMethod("volume", keyCode)
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent?): Boolean {
        if (capture && isVolume(keyCode)) return true
        return super.onKeyUp(keyCode, event)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        headCamera?.onPermission(requestCode, grantResults.isNotEmpty() && grantResults[0] == android.content.pm.PackageManager.PERMISSION_GRANTED)
    }

    override fun onDestroy() {
        headCamera?.stop()
        super.onDestroy()
    }

    companion object {
        const val HEAD_CHANNEL = "dev.jjh.mahjong_calc/head_camera"
        const val VOLUME_CHANNEL = "dev.jjh.mahjong_calc/volume"
        const val FILES_CHANNEL = "dev.jjh.mahjong_calc/files"
        const val SCREEN_CHANNEL = "dev.jjh.mahjong_calc/screen"
    }
}
