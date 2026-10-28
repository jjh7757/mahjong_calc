package dev.jjh.mahjong_calc

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.view.Surface
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import io.flutter.embedding.android.FlutterActivity
import io.flutter.view.TextureRegistry
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import kotlin.math.max
import kotlin.math.min

/// 카메라 헤드 전용 카메라: 셔터(ImageCapture) 없이 **미리보기 + 최대 해상도 YUV 스트림** 두 use case 만 묶는다.
///
/// camera 플러그인은 미리보기·촬영(JPEG)·스트림(YUV) 셋을 늘 같이 묶는데, Camera2 보장 스트림 조합에서는 JPEG 가
/// MAXIMUM 자리를 가져가 YUV 가 PREVIEW/RECORD 크기(S25 Ultra 1440×1080)로 제한된다(NOTES 32). FULL 이상 기기는
/// "PRIV(PREVIEW) + YUV(MAXIMUM)" 두 개 조합이 보장되므로, 촬영을 빼면 스트림에서 12MP(4080×3060) 프레임을 받는다.
/// 미리보기(`/preview`)와 촬영(`/capture`)을 모두 이 스트림의 최신 프레임에서 JPEG 로 만든다 → 셔터음 없음.
///
/// 프레임은 분석 스레드가 NV21 로 복사해 둔다(12MP 한 장 18MB, 복사 수 ms). 300ms 에 한 번만 복사하고
/// (`fresh` 요청이면 다음 프레임을 바로), JPEG 변환은 따로 스레드에서. 긴 변을 줄일 때는 NV21 을 건너뛰어 뽑아
/// (step) 작게 만든 뒤 압축한다(12MP 디코딩 없이 수십 ms).
class HeadCamera(private val activity: FlutterActivity, private val textures: TextureRegistry) {
    private var provider: ProcessCameraProvider? = null
    private var camera: Camera? = null
    private var preview: Preview? = null
    private var analysis: ImageAnalysis? = null
    private var entry: TextureRegistry.SurfaceTextureEntry? = null
    private val analysisExecutor = Executors.newSingleThreadExecutor()
    private val jpegExecutor = Executors.newSingleThreadExecutor()

    private val lock = Object()
    private var nv21: ByteArray? = null
    private var frameW = 0
    private var frameH = 0
    private var frameSeq = 0L
    private var lastCopyAt = 0L
    @Volatile private var wantFresh = false
    private var pendingStart: ((Result<Map<String, Any?>>) -> Unit)? = null
    private var pendingZoom = 1.0

    val isRunning get() = camera != null

    /// 카메라를 열고 묶는다. 권한이 없으면 묻고, 허락되면 이어서 연다. 결과: textureId·미리보기 크기·센서 방향·최대 줌.
    fun start(zoom: Double, cb: (Result<Map<String, Any?>>) -> Unit) {
        pendingZoom = zoom
        if (ContextCompat.checkSelfPermission(activity, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            pendingStart = cb
            ActivityCompat.requestPermissions(activity, arrayOf(Manifest.permission.CAMERA), PERMISSION_REQUEST)
            return
        }
        open(zoom, cb)
    }

    /// MainActivity.onRequestPermissionsResult 가 넘겨 준다.
    fun onPermission(requestCode: Int, granted: Boolean) {
        if (requestCode != PERMISSION_REQUEST) return
        val cb = pendingStart ?: return
        pendingStart = null
        if (granted) open(pendingZoom, cb) else cb(Result.failure(IllegalStateException("카메라 권한이 없습니다")))
    }

    private fun open(zoom: Double, cb: (Result<Map<String, Any?>>) -> Unit) {
        val future = ProcessCameraProvider.getInstance(activity)
        future.addListener({
            try {
                val p = future.get()
                provider = p
                p.unbindAll()
                val e = entry ?: textures.createSurfaceTexture().also { entry = it }
                val pv = Preview.Builder().build()
                val mainExecutor = ContextCompat.getMainExecutor(activity)
                pv.setSurfaceProvider { request ->
                    val st = e.surfaceTexture()
                    st.setDefaultBufferSize(request.resolution.width, request.resolution.height)
                    val surface = Surface(st)
                    request.provideSurface(surface, mainExecutor) { surface.release() }
                }
                val selector = ResolutionSelector.Builder()
                    .setResolutionStrategy(ResolutionStrategy.HIGHEST_AVAILABLE_STRATEGY)
                    .setAllowedResolutionMode(ResolutionSelector.PREFER_HIGHER_RESOLUTION_OVER_CAPTURE_RATE)
                    .build()
                val an = ImageAnalysis.Builder()
                    .setResolutionSelector(selector)
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
                    .build()
                an.setAnalyzer(analysisExecutor) { image ->
                    try {
                        maybeCopy(image)
                    } finally {
                        image.close()
                    }
                }
                val cam = p.bindToLifecycle(activity as LifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, pv, an)
                camera = cam
                preview = pv
                analysis = an
                val maxZoom = cam.cameraInfo.zoomState.value?.maxZoomRatio ?: 1f
                cam.cameraControl.setZoomRatio(zoom.toFloat().coerceIn(1f, maxZoom))
                val pres = pv.resolutionInfo?.resolution
                val ares = an.resolutionInfo?.resolution
                cb(Result.success(mapOf(
                    "textureId" to e.id(),
                    "previewWidth" to (pres?.width ?: 0),
                    "previewHeight" to (pres?.height ?: 0),
                    "streamWidth" to (ares?.width ?: 0),
                    "streamHeight" to (ares?.height ?: 0),
                    "sensorOrientation" to cam.cameraInfo.sensorRotationDegrees,
                    "maxZoom" to maxZoom.toDouble(),
                )))
            } catch (ex: Exception) {
                cb(Result.failure(ex))
            }
        }, ContextCompat.getMainExecutor(activity))
    }

    fun setZoom(zoom: Double): Double {
        val cam = camera ?: return 1.0
        val maxZoom = cam.cameraInfo.zoomState.value?.maxZoomRatio ?: 1f
        val z = zoom.toFloat().coerceIn(1f, maxZoom)
        cam.cameraControl.setZoomRatio(z)
        return z.toDouble()
    }

    fun stop() {
        try {
            provider?.unbindAll()
        } catch (_: Exception) {
        }
        camera = null
        preview = null
        analysis = null
        entry?.release()
        entry = null
        synchronized(lock) {
            nv21 = null
            frameW = 0
            frameH = 0
        }
    }

    /// 최신 프레임 → JPEG. [longSide] 가 프레임보다 작으면 건너뛰어 줄인다. [fresh] 면 이 호출 뒤 들어온 프레임을 기다린다(최대 1.5초).
    /// 결과: bytes·width·height(JPEG 크기)·frameWidth·frameHeight(스트림 프레임 크기).
    fun jpeg(longSide: Int?, quality: Int, fresh: Boolean, cb: (Result<Map<String, Any?>>) -> Unit) {
        jpegExecutor.execute {
            try {
                val (buf, w, h) = synchronized(lock) {
                    val seq0 = frameSeq
                    if (fresh) {
                        wantFresh = true
                        val deadline = System.currentTimeMillis() + 1500
                        while (frameSeq == seq0 && System.currentTimeMillis() < deadline) {
                            lock.wait(100)
                        }
                    }
                    val src = nv21 ?: throw IllegalStateException("미리보기 프레임이 아직 없습니다")
                    val w = frameW
                    val h = frameH
                    val long = max(w, h)
                    // 건너뛰기 간격은 내림 — 결과 긴 변이 요청값 이상이 되게(4080 에 w=2000 → step 2 → 2040).
                    val step = if (longSide == null || long <= longSide) 1 else max(1, long / longSide)
                    if (step <= 1) Triple(src.copyOf(), w, h) else Triple(subsample(src, w, h, step), (w / step) and 1.inv(), (h / step) and 1.inv())
                }
                val out = ByteArrayOutputStream(w * h / 4)
                YuvImage(buf, ImageFormat.NV21, w, h, null).compressToJpeg(Rect(0, 0, w, h), quality.coerceIn(30, 100), out)
                val (fw, fh) = synchronized(lock) { Pair(frameW, frameH) }
                cb(Result.success(mapOf(
                    "bytes" to out.toByteArray(),
                    "width" to w,
                    "height" to h,
                    "frameWidth" to fw,
                    "frameHeight" to fh,
                )))
            } catch (ex: Exception) {
                cb(Result.failure(ex))
            }
        }
    }

    /// 300ms 에 한 번(또는 fresh 요청이 있으면 바로) 프레임을 NV21 로 복사해 둔다.
    private fun maybeCopy(image: ImageProxy) {
        val now = System.currentTimeMillis()
        if (!wantFresh && now - lastCopyAt < COPY_INTERVAL_MS) return
        val w = image.width
        val h = image.height
        val planes = image.planes
        val size = w * h * 3 / 2
        synchronized(lock) {
            val out = nv21?.takeIf { it.size == size } ?: ByteArray(size)
            // Y
            val y = planes[0].buffer
            val yRs = planes[0].rowStride
            for (row in 0 until h) {
                y.position(row * yRs)
                y.get(out, row * w, w)
            }
            // VU 섞인 평면(NV21): pixelStride 2 면 V 평면 버퍼가 V,U,V,U… 로 이어져 그대로 복사한다.
            val u = planes[1]
            val v = planes[2]
            val uvRows = h / 2
            val base = w * h
            if (v.pixelStride == 2 && u.pixelStride == 2) {
                val vb = v.buffer
                val ub = u.buffer
                val rs = v.rowStride
                for (row in 0 until uvRows) {
                    vb.position(row * rs)
                    val n = min(w, vb.remaining())
                    vb.get(out, base + row * w, n)
                    if (n < w) {
                        // 마지막 줄 끝 U 한 바이트는 V 버퍼 밖에 있다.
                        ub.position(row * u.rowStride + (w - 2))
                        out[base + row * w + w - 1] = ub.get()
                    }
                }
            } else {
                val vb = v.buffer
                val ub = u.buffer
                for (row in 0 until uvRows) {
                    val vo = row * v.rowStride
                    val uo = row * u.rowStride
                    val o = base + row * w
                    for (col in 0 until w / 2) {
                        out[o + 2 * col] = vb.get(vo + col * v.pixelStride)
                        out[o + 2 * col + 1] = ub.get(uo + col * u.pixelStride)
                    }
                }
            }
            nv21 = out
            frameW = w
            frameH = h
            frameSeq++
            lastCopyAt = now
            wantFresh = false
            lock.notifyAll()
        }
    }

    companion object {
        const val PERMISSION_REQUEST = 7311
        const val COPY_INTERVAL_MS = 300L

        /// NV21 을 step 마다 한 픽셀씩 뽑아 작은 NV21 로(가로·세로 짝수로 맞춤).
        fun subsample(src: ByteArray, w: Int, h: Int, step: Int): ByteArray {
            val ow = (w / step) and 1.inv()
            val oh = (h / step) and 1.inv()
            val out = ByteArray(ow * oh * 3 / 2)
            for (j in 0 until oh) {
                val srow = j * step * w
                val orow = j * ow
                for (i in 0 until ow) out[orow + i] = src[srow + i * step]
            }
            val sbase = w * h
            val obase = ow * oh
            for (j in 0 until oh / 2) {
                val srow = sbase + (j * step) * w
                val orow = obase + j * ow
                for (i in 0 until ow / 2) {
                    val sc = srow + 2 * (i * step)
                    out[orow + 2 * i] = src[sc]
                    out[orow + 2 * i + 1] = src[sc + 1]
                }
            }
            return out
        }
    }
}
