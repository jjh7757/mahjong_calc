package dev.jjh.mahjong_calc

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.util.concurrent.Executors

/// 기기 판독 실험(exp/on-device-read): 서버 자체 판독(`/v2/localroles`·`/v2/localdora`·`/v2/locallast3`)을 앱 안 Python(Chaquopy)으로.
/// Python 모듈 `ondevice.observe(kind, images, query)` 가 서버 응답과 같은 JSON 문자열을 돌려준다.
/// 앱이 세 호출을 동시에 보내므로 스레드 3개(서버도 실행기 스레드에서 동시에 돈다. 처음엔 1개라 강 끝이 앞 둘을 기다렸다 — metrics 표 4-1).
class OnDeviceReader(private val context: Context) {
    private val worker = Executors.newFixedThreadPool(3) { r -> Thread(r, "ondevice-read") }
    private var module: PyObject? = null

    @Synchronized
    private fun mod(): PyObject {
        module?.let { return it }
        if (!Python.isStarted()) Python.start(AndroidPlatform(context))
        return Python.getInstance().getModule("ondevice").also { module = it }
    }

    /// [kind] = localroles | localdora | locallast3, [images] = JPEG 바이트들, [query] = 서버 URL 쿼리와 같은 키·값.
    fun observe(kind: String, images: List<ByteArray>, query: Map<String, String>, cb: (Result<String>) -> Unit) {
        worker.execute {
            cb(runCatching {
                val m = mod()
                val py = Python.getInstance()
                val list = py.builtins.callAttr("list")
                for (b in images) list.callAttr("append", PyObject.fromJava(b))
                val q = py.builtins.callAttr("dict")
                for ((k, v) in query) q.callAttr("__setitem__", k, v)
                m.callAttr("observe", kind, list, q).toString()
            })
        }
    }

    /// 판 중 겹쳐 보기(실험): 사진 전체의 앞면 패마다 상자·종류·역할(ondevice.overlay). 판독 스레드와 따로(한 번에 하나).
    private val overlayWorker = Executors.newSingleThreadExecutor { r -> Thread(r, "ondevice-overlay") }

    fun overlay(image: ByteArray, query: Map<String, String>, cb: (Result<String>) -> Unit) {
        overlayWorker.execute {
            cb(runCatching {
                val m = mod()
                val q = Python.getInstance().builtins.callAttr("dict")
                for ((k, v) in query) q.callAttr("__setitem__", k, v)
                m.callAttr("overlay", PyObject.fromJava(image), q).toString()
            })
        }
    }

    /// 측정용: prepare 방식("server" | "skip").
    fun setPrep(v: String, cb: (Result<String>) -> Unit) {
        worker.execute { cb(runCatching { mod().callAttr("set_prep", v).toString() }) }
    }

    /// 모델·모듈을 미리 올린다(첫 판독이 늦지 않게). 결과는 올리는 데 걸린 초를 담은 JSON.
    fun warmup(cb: (Result<String>) -> Unit) {
        worker.execute { cb(runCatching { mod().callAttr("warmup").toString() }) }
    }
}
