package dev.jjh.mahjong_calc

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CaptureRequest
import android.util.Range
import androidx.annotation.OptIn
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import android.graphics.Rect
import android.graphics.YuvImage
import android.os.Build
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
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
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
///
/// 녹화 모드(시험용, 기본 꺼짐, `recordStart`/`recordStop`/`recordStatus`): 같은 스트림에서 초당 10장까지 골라 2×2 평균으로
/// 줄인 JPEG 를 앱 전용 외부 저장소에 쓴다. 판독 경로(maybeCopy·jpeg)와 잠금·버퍼를 나눠 쓰지 않는다. 아래 "녹화 모드" 절.
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

    /// 스트림 목표 초당 장수(2026-11-12 발열 시험). 제한이 없으면 12MP 를 초당 30장 만들어 녹화를 꺼도 발열 단계가 3~4 까지
    /// 오른다(metrics 표 12-7·12-10). 판독은 3초마다 한 장, 녹화는 초당 10장이라 15장이면 충분하다(S25 Ultra 고정 범위 최저 15).
    /// 0 이면 제한 없음.
    private val streamFps = STREAM_FPS

    // ---- 스트림 속도(녹화와 상관없이 늘 잰다). 분석 스레드만 쓴다(stop() 의 0 으로 되돌리기 빼고). ----
    @Volatile private var streamFirstAt = 0L
    @Volatile private var streamLastAt = 0L
    @Volatile private var streamFrames = 0L
    @Volatile private var streamFpsRecent = 0.0
    private var streamWinAt = 0L
    private var streamWinCount = 0

    // ---- 녹화(시험용, 기본 꺼짐). [lock](판독 버퍼)과 따로 [recLock] 을 쓴다 → jpeg() 는 녹화 때문에 기다리지 않는다. ----
    private val recLock = Any()
    /// 녹화 중인 세션(끝나면 null). 분석 스레드는 이것만 본다.
    @Volatile private var rec: RecordSession? = null
    /// 마지막 세션(끝난 뒤에도 장수·멈춘 까닭을 보고하려고 남긴다. 큰 버퍼는 끝날 때 놓는다).
    @Volatile private var lastRec: RecordSession? = null

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
                val anBuilder = ImageAnalysis.Builder()
                    .setResolutionSelector(selector)
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
                val fpsRange = pickFpsRange(p, streamFps)
                if (fpsRange != null) limitFps(anBuilder, fpsRange)
                val an = anBuilder.build()
                an.setAnalyzer(analysisExecutor) { image ->
                    try {
                        val now = System.currentTimeMillis()
                        noteStreamFrame(now)
                        maybeCopy(image)
                        // 판독용 복사가 먼저, 녹화는 그 뒤(녹화가 꺼져 있으면 아무것도 안 한다).
                        maybeRecord(image, now)
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
                    "fpsRange" to fpsRange?.let { "${it.lower}-${it.upper}" },
                )))
            } catch (ex: Exception) {
                cb(Result.failure(ex))
            }
        }, ContextCompat.getMainExecutor(activity))
    }

    /// 스트림 목표 장수에 맞는 AE 목표 범위: [fps] 이상인 고정 범위(lower == upper) 중 가장 낮은 것, 없으면 upper 가 [fps] 이상인
    /// 범위 중 upper 가 가장 낮은 것. [fps] ≤ 0 이거나 고를 것이 없으면 null(제한 없음 = 예전처럼 초당 30장).
    @OptIn(ExperimentalCamera2Interop::class)
    private fun pickFpsRange(p: ProcessCameraProvider, fps: Int): Range<Int>? {
        if (fps <= 0) return null
        return try {
            val info = CameraSelector.DEFAULT_BACK_CAMERA.filter(p.availableCameraInfos).firstOrNull() ?: return null
            val ranges = Camera2CameraInfo.from(info)
                .getCameraCharacteristic(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES) ?: return null
            ranges.filter { it.lower == it.upper && it.upper >= fps }.minByOrNull { it.upper }
                ?: ranges.filter { it.upper >= fps }.minByOrNull { it.upper }
        } catch (_: Exception) {
            null
        }
    }

    @OptIn(ExperimentalCamera2Interop::class)
    private fun limitFps(b: ImageAnalysis.Builder, r: Range<Int>) {
        Camera2Interop.Extender(b).setCaptureRequestOption(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, r)
    }

    fun setZoom(zoom: Double): Double {
        val cam = camera ?: return 1.0
        val maxZoom = cam.cameraInfo.zoomState.value?.maxZoomRatio ?: 1f
        val z = zoom.toFloat().coerceIn(1f, maxZoom)
        cam.cameraControl.setZoomRatio(z)
        return z.toDouble()
    }

    fun stop() {
        recordStop(STOP_CAMERA)
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
        streamFirstAt = 0L
        streamLastAt = 0L
        streamFrames = 0L
        streamFpsRecent = 0.0
    }

    /// 최신 프레임 → JPEG. [longSide] 가 프레임보다 작으면 건너뛰어 줄인다. [fresh] 면 이 호출 뒤 들어온 프레임을 기다리고(최대 3초), 안 오면 실패.
    /// 결과: bytes·width·height(JPEG 크기)·frameWidth·frameHeight(스트림 프레임 크기).
    fun jpeg(longSide: Int?, quality: Int, fresh: Boolean, cb: (Result<Map<String, Any?>>) -> Unit) {
        jpegExecutor.execute {
            try {
                val (buf, w, h) = synchronized(lock) {
                    val seq0 = frameSeq
                    if (fresh) {
                        wantFresh = true
                        val deadline = System.currentTimeMillis() + FRESH_WAIT_MS
                        while (frameSeq == seq0 && System.currentTimeMillis() < deadline) {
                            lock.wait(100)
                        }
                        // 2026-10-30 점검: 새 프레임이 안 오면(헤드 앱이 뒤로 감·카메라 멈춤) 묵은 프레임을 성공으로 돌려주지 않는다.
                        // 전엔 손패를 공개하기 전 프레임으로 판독할 수 있었다.
                        if (frameSeq == seq0) {
                            wantFresh = false
                            throw IllegalStateException("새 카메라 프레임이 오지 않습니다. 헤드 화면이 켜져 있는지 확인하세요")
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

    // ======================================================================================================
    // 녹화 모드(시험용, docs/tedashi_video_plan_1112.md 0단계). 스트림 프레임을 초당 [RecordSession.fps] 장까지
    // 2×2 평균으로 반 크기로 줄여 JPEG 로 앱 전용 외부 저장소(getExternalFilesDir/rec/rec_<시각>/f_<밀리초>.jpg)에 쓴다.
    //
    // 나눔: 분석 콜백은 고른 프레임을 원본 크기 NV21 로 **복사만** 한다(maybeCopy 와 같은 평면 복사, 12MP 수 ms).
    // 2×2 평균·JPEG·파일 쓰기는 세션마다 하나인 저장 스레드에서. 콜백이 ImageProxy 를 오래 붙잡으면 다음 프레임(판독용
    // maybeCopy 포함)이 밀리므로, 콜백 안 일은 판독 복사와 같은 크기의 memcpy 한 번으로 묶었다. 버퍼는 원본 크기 3개
    // (저장 중 1 + 대기 2)를 돌려 쓰고, 빈 버퍼가 없으면 = 대기가 2장 찼으면 새 프레임을 버리고 센다(판독이 먼저).
    // ======================================================================================================

    /// 분석 콜백마다 부른다: 스트림이 초당 몇 장 오는지(최근 [STREAM_WINDOW_MS] 창, 전체 평균).
    private fun noteStreamFrame(now: Long) {
        if (streamFirstAt == 0L) {
            streamFirstAt = now
            streamLastAt = now
            streamFrames = 1
            streamWinAt = now
            streamWinCount = 0
            return
        }
        streamFrames++
        streamLastAt = now
        streamWinCount++
        val span = now - streamWinAt
        if (span >= STREAM_WINDOW_MS) {
            // 창 첫 프레임에서 지금까지 들어온 장수 = 간격 수 → 장/초.
            streamFpsRecent = streamWinCount * 1000.0 / span
            streamWinAt = now
            streamWinCount = 0
        }
    }

    /// 최근 스트림 속도. 2초 넘게 프레임이 없으면(앱이 뒤로 감·카메라 멈춤) 0.
    private fun streamFpsNow(now: Long): Double =
        if (streamLastAt == 0L || now - streamLastAt > STREAM_STALE_MS) 0.0 else streamFpsRecent

    private fun streamFpsAverage(): Double = rate(streamFrames - 1, streamLastAt - streamFirstAt)

    /// 녹화를 시작한다. 카메라가 안 돌거나 남은 용량이 [MIN_FREE_BYTES] 아래면 실패(예외). 이미 녹화 중이면 지금 상태를 준다.
    fun recordStart(fps: Int = 10, quality: Int = 85): Map<String, Any?> {
        synchronized(recLock) {
            if (rec != null) return recordStatus()
            if (!isRunning) throw IllegalStateException("카메라가 돌고 있지 않아 녹화를 시작할 수 없습니다")
            val base = activity.getExternalFilesDir(null) ?: throw IllegalStateException("앱 저장소를 쓸 수 없습니다")
            val free = base.usableSpace
            if (free < MIN_FREE_BYTES) {
                throw IllegalStateException("남은 용량이 ${gb(free)}GB 라 녹화를 시작하지 않습니다(2GB 이상 필요)")
            }
            val now = System.currentTimeMillis()
            val stamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date(now))
            val root = File(base, "rec")
            var dir = File(root, "rec_$stamp")
            var n = 2
            while (dir.exists()) dir = File(root, "rec_${stamp}_${n++}")
            if (!dir.mkdirs()) throw IllegalStateException("녹화 폴더를 만들 수 없습니다: $dir")
            val s = RecordSession(dir, fps.coerceIn(1, MAX_RECORD_FPS), quality.coerceIn(30, 100), now)
            rec = s
            lastRec = s
        }
        return recordStatus()
    }

    /// 녹화를 끝낸다(녹화 중이 아니면 아무것도 안 함). 대기 중인 프레임은 마저 쓰고 record.json 을 쓴다(저장 스레드에서).
    fun recordStop(reason: String = STOP_USER): Map<String, Any?> {
        rec?.let { finishRecord(it, reason, null) }
        return recordStatus()
    }

    /// 녹화 상태. 녹화 중이 아니어도 streamFps·freeBytes 는 준다. 끝난 세션이 있으면 그 장수·까닭도.
    fun recordStatus(): Map<String, Any?> {
        val now = System.currentTimeMillis()
        val m = HashMap<String, Any?>()
        val s = lastRec
        m["recording"] = s?.active == true
        m["streamFps"] = round2(streamFpsNow(now))
        m["streamFpsAvg"] = round2(streamFpsAverage())
        m["freeBytes"] = try {
            activity.getExternalFilesDir(null)?.usableSpace ?: -1L
        } catch (_: Exception) {
            -1L
        }
        if (s != null) {
            m["dir"] = s.dir.absolutePath
            m["fps"] = s.fps
            m["quality"] = s.quality
            m["saved"] = s.saved
            m["dropped"] = s.dropped
            m["bytes"] = s.bytes
            m["savedFps"] = round2(savedFpsRecent(s, now))
            m["startedAt"] = s.startedAt
            m["endedAt"] = if (s.endedAt != 0L) s.endedAt else null
            m["frameWidth"] = s.frameW
            m["frameHeight"] = s.frameH
            m["savedWidth"] = s.outW
            m["savedHeight"] = s.outH
            m["stopReason"] = s.stopReason
            m["stopDetail"] = s.stopDetail
        }
        return m
    }

    /// 태블릿 이어 받기: 마지막(또는 지금) 녹화에서 [after] ms 보다 늦게 다 쓴 프레임 시각을 오름차순으로 [max] 개까지.
    /// 파일은 `dir/f_<ms>.jpg`. 이 앱을 켠 뒤 녹화한 세션만 안다(그 전 폴더는 adb 로).
    fun recordFrames(after: Long, max: Int): Map<String, Any?> {
        val m = HashMap<String, Any?>()
        val s = lastRec
        m["recording"] = s?.active == true
        if (s == null) {
            m["ms"] = emptyList<Long>()
            return m
        }
        m["dir"] = s.dir.absolutePath
        val out = ArrayList<Long>()
        synchronized(s.savedLock) {
            val n = s.savedCount
            m["savedCount"] = n
            m["latest"] = if (n > 0) s.savedMs[n - 1] else null
            // after 보다 큰 첫 자리(이분 탐색).
            var lo = 0
            var hi = n
            while (lo < hi) {
                val mid = (lo + hi) ushr 1
                if (s.savedMs[mid] <= after) lo = mid + 1 else hi = mid
            }
            var i = lo
            while (i < n && out.size < max) out.add(s.savedMs[i++])
            m["remaining"] = n - i
        }
        m["ms"] = out
        return m
    }

    /// 분석 콜백: 녹화 중이고 다음 차례면 원본 크기 NV21 로 복사해 저장 스레드에 넘긴다.
    private fun maybeRecord(image: ImageProxy, now: Long) {
        val s = rec ?: return
        if (!s.active) return
        if (s.streamFrames == 0L) s.firstStreamAt = now
        s.streamFrames++
        s.lastStreamAt = now
        if (now < s.nextAt) return
        // 목표 간격의 격자를 따라간다(스트림 간격이 들쭉날쭉해도 평균이 fps 가 되게).
        // "마지막 저장에서 간격이 지났으면" 으로 하면 30fps 스트림에서 99ms 프레임을 놓쳐 133ms 마다(7.5장/초)가 된다.
        // 한 간격 넘게 밀렸으면(스트림 멈춤 등) 지금부터 다시 센다.
        s.nextAt = if (s.nextAt == 0L || now - s.nextAt >= s.intervalMs) now + s.intervalMs else s.nextAt + s.intervalMs
        val f = s.free.poll()
        if (f == null) {
            s.dropped++
            return
        }
        try {
            val w = image.width
            val h = image.height
            val size = w * h * 3 / 2
            val t0 = System.nanoTime()
            if (f.data.size != size) f.data = ByteArray(size) // 버퍼마다 처음 한 번(프레임 크기는 안 바뀐다)
            copyNv21(image, f.data)
            s.copyNs += System.nanoTime() - t0
            s.copies++
            s.frameW = w
            s.frameH = h
            f.w = w
            f.h = h
            f.t = now
        } catch (e: Throwable) {
            // 메모리 부족 등: 판독을 해치지 않게 녹화만 끝낸다.
            finishRecord(s, STOP_ERROR, e.toString())
            return
        }
        try {
            s.writer.execute { saveFrame(s, f) }
        } catch (_: RejectedExecutionException) {
            // 그 사이 녹화가 끝났다 → 이 프레임은 버린다(버퍼도 돌려놓지 않는다 — 끝난 세션의 버퍼는 놓는다).
        }
    }

    /// 저장 스레드: 2×2 평균 → JPEG → 파일. 그 뒤 남은 용량(1초마다)·record.json(60초마다).
    private fun saveFrame(s: RecordSession, f: Frame) {
        // 끝낸 뒤 들어온 프레임(record.json 마무리 뒤)이면 그냥 버린다.
        val jpeg = s.jpegOut ?: return
        try {
            val ow = (f.w / 2) and 1.inv()
            val oh = (f.h / 2) and 1.inv()
            val need = ow * oh * 3 / 2
            val small = s.small?.takeIf { it.size == need } ?: ByteArray(need).also { s.small = it }
            val t0 = System.nanoTime()
            average2x2(f.data, f.w, f.h, small)
            val t1 = System.nanoTime()
            jpeg.reset()
            YuvImage(small, ImageFormat.NV21, ow, oh, null).compressToJpeg(Rect(0, 0, ow, oh), s.quality, jpeg)
            val t2 = System.nanoTime()
            FileOutputStream(File(s.dir, "f_${f.t}.jpg")).use { jpeg.writeTo(it) }
            val t3 = System.nanoTime()
            s.avgNs += t1 - t0
            s.jpegNs += t2 - t1
            s.writeNs += t3 - t2
            s.bytes += jpeg.size()
            s.saved++
            s.outW = ow
            s.outH = oh
            synchronized(s.saveTimes) {
                s.saveTimes[s.saveIdx % s.saveTimes.size] = f.t
                s.saveIdx++
            }
            // 파일을 다 쓴 뒤에만 목록에 넣는다 → 태블릿이 반쯤 쓴 파일을 읽지 않는다.
            synchronized(s.savedLock) {
                if (s.savedCount == s.savedMs.size) s.savedMs = s.savedMs.copyOf(s.savedMs.size * 2)
                s.savedMs[s.savedCount++] = f.t
            }
        } catch (e: Throwable) {
            finishRecord(s, STOP_ERROR, e.toString())
            return
        } finally {
            s.free.offer(f)
        }
        val now = System.currentTimeMillis()
        if (s.active && now - s.lastSpaceAt >= SPACE_CHECK_MS) {
            s.lastSpaceAt = now
            val free = s.dir.usableSpace
            if (free < MIN_FREE_BYTES) finishRecord(s, STOP_LOW_STORAGE, "남은 용량 ${gb(free)}GB")
        }
        if (s.active && now - s.lastJsonAt >= JSON_EVERY_MS) {
            s.lastJsonAt = now
            writeRecordJson(s)
        }
    }

    /// 세션을 한 번만 끝낸다(어느 스레드에서든). 마무리(record.json·버퍼 놓기)는 저장 스레드 큐 맨 뒤에 넣는다.
    private fun finishRecord(s: RecordSession, reason: String, detail: String?) {
        synchronized(recLock) {
            if (!s.active) return
            s.active = false
            s.stopReason = reason
            s.stopDetail = detail
            s.endedAt = System.currentTimeMillis()
            if (rec === s) rec = null
        }
        try {
            s.writer.execute {
                writeRecordJson(s)
                // lastRec 가 세션을 붙잡고 있어도 큰 버퍼(원본 3장 ≈ 56MB)는 놓는다.
                s.free.clear()
                s.small = null
                s.jpegOut = null
            }
        } catch (_: RejectedExecutionException) {
        }
        s.writer.shutdown()
    }

    /// 저장 스레드에서만 부른다. 임시 파일에 쓰고 이름을 바꿔 반쯤 쓴 record.json 이 남지 않게.
    private fun writeRecordJson(s: RecordSession) {
        try {
            val now = System.currentTimeMillis()
            val end = if (s.endedAt != 0L) s.endedAt else now
            val iso = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSZ", Locale.US)
            val saved = s.saved
            val j = JSONObject()
            j.put("startedAt", iso.format(Date(s.startedAt)))
            j.put("startedAtMs", s.startedAt)
            j.put("endedAt", if (s.endedAt != 0L) iso.format(Date(s.endedAt)) else JSONObject.NULL)
            j.put("endedAtMs", if (s.endedAt != 0L) s.endedAt else JSONObject.NULL)
            j.put("final", s.endedAt != 0L)
            j.put("writtenAtMs", now)
            j.put("durationSec", round2((end - s.startedAt) / 1000.0))
            j.put("requestedFps", s.fps)
            j.put("jpegQuality", s.quality)
            j.put("downscale", "2x2 average")
            j.put("saved", saved)
            j.put("dropped", s.dropped)
            j.put("bytes", s.bytes)
            j.put("savedFpsAvg", round2(rate(saved, end - s.startedAt)))
            j.put("savedFpsRecent5s", round2(savedFpsRecent(s, now)))
            j.put("frameWidth", s.frameW)
            j.put("frameHeight", s.frameH)
            j.put("savedWidth", s.outW)
            j.put("savedHeight", s.outH)
            j.put("avgMs", JSONObject().apply {
                put("copyInCallback", round2(msPer(s.copyNs, s.copies)))
                put("average2x2", round2(msPer(s.avgNs, saved)))
                put("jpeg", round2(msPer(s.jpegNs, saved)))
                put("fileWrite", round2(msPer(s.writeNs, saved)))
            })
            j.put("streamFps", JSONObject().apply {
                put("recent", round2(streamFpsNow(now)))
                put("averageWhileRecording", round2(rate(s.streamFrames - 1, s.lastStreamAt - s.firstStreamAt)))
                put("framesWhileRecording", s.streamFrames)
            })
            j.put("freeBytes", s.dir.usableSpace)
            j.put("stopReason", s.stopReason ?: JSONObject.NULL)
            j.put("stopDetail", s.stopDetail ?: JSONObject.NULL)
            j.put("device", Build.MODEL)
            val tmp = File(s.dir, "record.json.tmp")
            tmp.writeText(j.toString(2))
            val dst = File(s.dir, "record.json")
            if (!tmp.renameTo(dst)) {
                dst.delete()
                tmp.renameTo(dst)
            }
        } catch (_: Exception) {
            // record.json 은 보조 기록 — 못 써도 녹화는 계속한다.
        }
    }

    /// 최근 5초 저장 속도(녹화가 5초 안 됐으면 지난 시간으로 나눈다). 끝난 세션은 끝난 시각 기준.
    private fun savedFpsRecent(s: RecordSession, now: Long): Double {
        val ref = if (s.endedAt != 0L) s.endedAt else now
        val window = min(SAVED_FPS_WINDOW_MS, ref - s.startedAt)
        if (window <= 0) return 0.0
        var count = 0
        synchronized(s.saveTimes) {
            val n = min(s.saveIdx, s.saveTimes.size)
            for (k in 0 until n) {
                val t = s.saveTimes[k]
                if (t > ref - window && t <= ref) count++
            }
        }
        return count * 1000.0 / window
    }

    /// maybeCopy 와 같은 평면 → NV21 복사(rowStride·pixelStride 두 경우 모두). maybeCopy 는 판독 경로라 손대지 않고 따로 둔다.
    private fun copyNv21(image: ImageProxy, out: ByteArray) {
        val w = image.width
        val h = image.height
        val planes = image.planes
        val y = planes[0].buffer
        val yRs = planes[0].rowStride
        for (row in 0 until h) {
            y.position(row * yRs)
            y.get(out, row * w, w)
        }
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
    }

    /// 원본 크기 NV21 한 장(버퍼 고리의 한 칸).
    private class Frame {
        var data = ByteArray(0)
        var w = 0
        var h = 0
        var t = 0L
    }

    /// 녹화 한 번. 값마다 쓰는 스레드가 하나뿐이라(주석에 표시) @Volatile 로 충분하다 — 읽기는 어느 스레드에서나.
    private class RecordSession(val dir: File, val fps: Int, val quality: Int, val startedAt: Long) {
        val intervalMs = 1000L / fps
        /// 줄이기·JPEG·쓰기 전용. 판독보다 낮은 우선순위.
        val writer: ExecutorService = Executors.newSingleThreadExecutor { r ->
            Thread(r, "head-rec").apply { priority = Thread.NORM_PRIORITY - 1 }
        }
        /// 빈 버퍼. 분석 스레드가 꺼내 채우고 저장 스레드가 다 쓰면 돌려놓는다.
        val free = ArrayBlockingQueue<Frame>(RECORD_BUFFERS).apply { repeat(RECORD_BUFFERS) { add(Frame()) } }

        // recLock 아래에서 바뀐다(끝낼 때 한 번).
        @Volatile var active = true
        @Volatile var endedAt = 0L
        @Volatile var stopReason: String? = null
        @Volatile var stopDetail: String? = null

        // 분석 스레드만 쓴다.
        var nextAt = 0L
        @Volatile var dropped = 0L
        @Volatile var streamFrames = 0L
        @Volatile var firstStreamAt = 0L
        @Volatile var lastStreamAt = 0L
        @Volatile var copyNs = 0L
        @Volatile var copies = 0L
        @Volatile var frameW = 0
        @Volatile var frameH = 0

        // 저장 스레드만 쓴다.
        @Volatile var saved = 0L
        @Volatile var bytes = 0L
        @Volatile var avgNs = 0L
        @Volatile var jpegNs = 0L
        @Volatile var writeNs = 0L
        @Volatile var outW = 0
        @Volatile var outH = 0
        var small: ByteArray? = null
        @Volatile var jpegOut: ByteArrayOutputStream? = ByteArrayOutputStream(1 shl 20)
        var lastJsonAt = startedAt
        var lastSpaceAt = 0L
        /// 최근 저장 시각 고리(이 배열로 잠금). 15장/초 × 5초 = 75 < 128.
        val saveTimes = LongArray(128)
        var saveIdx = 0
        /// 다 쓴 프레임 시각(파일 이름 f_<ms>.jpg), 오름차순. 태블릿 이어 받기(`recordFrames`)용. [savedLock] 으로 잠금.
        /// 저장 스레드 하나가 순서대로 쓰므로 늘 오름차순이다. 한 시간 3.6만 장 ≈ 290KB.
        val savedLock = Object()
        var savedMs = LongArray(4096)
        var savedCount = 0
    }

    companion object {
        const val PERMISSION_REQUEST = 7311
        const val COPY_INTERVAL_MS = 300L
        const val FRESH_WAIT_MS = 3000L
        const val STREAM_FPS = 15

        // 녹화
        const val MAX_RECORD_FPS = 15
        /// 원본 크기 버퍼 수 = 저장 중 1 + 대기 2. 대기가 2장 넘게 쌓이면 새 프레임을 버린다.
        const val RECORD_BUFFERS = 3
        const val MIN_FREE_BYTES = 2L shl 30 // 2GB
        const val SPACE_CHECK_MS = 1000L
        const val JSON_EVERY_MS = 60_000L
        const val SAVED_FPS_WINDOW_MS = 5000L
        const val STREAM_WINDOW_MS = 1000L
        const val STREAM_STALE_MS = 2000L
        const val STOP_USER = "user"
        const val STOP_CAMERA = "camera_stop"
        const val STOP_LOW_STORAGE = "low_storage"
        const val STOP_ERROR = "error"

        /// 장/초. 시간이 0 이하면 0(JSON 에 NaN 이 들어가지 않게).
        private fun rate(count: Long, ms: Long): Double = if (ms <= 0 || count <= 0) 0.0 else count * 1000.0 / ms

        private fun msPer(ns: Long, n: Long): Double = if (n <= 0) 0.0 else ns / 1e6 / n

        private fun round2(x: Double): Double = if (x.isNaN() || x.isInfinite()) 0.0 else Math.round(x * 100) / 100.0

        private fun gb(bytes: Long): String = String.format(Locale.US, "%.1f", bytes / (1L shl 30).toDouble())

        /// NV21(w×h) 를 2×2 평균으로 반 크기 NV21(ow×oh)로. ow = w/2, oh = h/2 를 각각 짝수로 내린다(NV21 은 색차가 2×2 마다
        /// 한 쌍이라 짝수여야 한다). [out] 을 주면 거기에 쓴다(프레임마다 새로 할당하지 않게).
        ///
        /// - Y: 출력 (i, j) = 원본 (2i, 2j)·(2i+1, 2j)·(2i, 2j+1)·(2i+1, 2j+1) 네 픽셀 평균(반올림).
        /// - VU: 원본 색차는 (w/2)×(h/2) 쌍 격자이고 줄마다 w 바이트(V,U,V,U…). 출력 색차 쌍 (i, j) =
        ///   원본 쌍 (2i, 2j)·(2i+1, 2j)·(2i, 2j+1)·(2i+1, 2j+1) 의 V 끼리·U 끼리 평균. 즉 출력 Y 와 같은 자리(원본 4×4 Y 블록)를 덮는다.
        /// - 바이트는 부호 없이(`and 0xFF`) 더한다. 짝수로 내렸으므로 읽는 원본 열·줄은 늘 범위 안이고, 홀수 끝 열·줄(Y 한 줄,
        ///   ow 를 내릴 때 남는 Y 두 열·색차 한 쌍)은 버린다. 4080×3060 → 2040×1530 은 버리는 것이 없다.
        fun average2x2(src: ByteArray, w: Int, h: Int, out: ByteArray? = null): ByteArray {
            val ow = (w / 2) and 1.inv()
            val oh = (h / 2) and 1.inv()
            val need = ow * oh * 3 / 2
            require(src.size >= w * h + (h / 2) * w) { "NV21 크기가 모자랍니다: ${src.size} < ${w}x$h" }
            val dst = out ?: ByteArray(need)
            require(dst.size >= need) { "출력 버퍼가 작습니다: ${dst.size} < $need" }
            for (j in 0 until oh) {
                var a = 2 * j * w // 원본 Y 줄 2j
                var b = a + w // 원본 Y 줄 2j+1
                var o = j * ow
                for (i in 0 until ow) {
                    val sum = (src[a].toInt() and 0xFF) + (src[a + 1].toInt() and 0xFF) +
                        (src[b].toInt() and 0xFF) + (src[b + 1].toInt() and 0xFF)
                    dst[o] = ((sum + 2) shr 2).toByte()
                    a += 2
                    b += 2
                    o++
                }
            }
            val sbase = w * h
            val obase = ow * oh
            for (j in 0 until oh / 2) {
                var a = sbase + 2 * j * w // 원본 색차 줄 2j
                var b = a + w // 원본 색차 줄 2j+1
                var o = obase + j * ow
                for (i in 0 until ow / 2) {
                    // 원본 쌍 2i → 바이트 a(V), a+1(U); 쌍 2i+1 → a+2(V), a+3(U).
                    val v = (src[a].toInt() and 0xFF) + (src[a + 2].toInt() and 0xFF) +
                        (src[b].toInt() and 0xFF) + (src[b + 2].toInt() and 0xFF)
                    val u = (src[a + 1].toInt() and 0xFF) + (src[a + 3].toInt() and 0xFF) +
                        (src[b + 1].toInt() and 0xFF) + (src[b + 3].toInt() and 0xFF)
                    dst[o] = ((v + 2) shr 2).toByte()
                    dst[o + 1] = ((u + 2) shr 2).toByte()
                    a += 4
                    b += 4
                    o += 2
                }
            }
            return dst
        }

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
