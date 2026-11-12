package dev.jjh.mahjong_calc

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import ai.onnxruntime.TensorInfo
import java.nio.ByteBuffer
import java.nio.ByteOrder

/// 기기 판독 실험(exp/on-device-read): Chaquopy 안의 서버 판독 코드가 부르는 onnxruntime 흉내
/// (`android/app/src/main/python/onnxruntime`)의 실제 계산. float32 텐서만, 바이트(리틀 엔디언)로 주고받는다.
object OrtBridge {
    private val env: OrtEnvironment by lazy { OrtEnvironment.getEnvironment() }
    private val sessions = mutableListOf<OrtSession>()

    @JvmStatic
    @Synchronized
    fun load(path: String, threads: Int): Int {
        val opts = OrtSession.SessionOptions().apply {
            setIntraOpNumThreads(threads)
            setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        }
        sessions.add(env.createSession(path, opts))
        return sessions.size - 1
    }

    @JvmStatic
    fun inputNames(h: Int): Array<String> = sessions[h].inputNames.toTypedArray()

    @JvmStatic
    fun outputNames(h: Int): Array<String> = sessions[h].outputNames.toTypedArray()

    @JvmStatic
    fun inputShape(h: Int, i: Int): LongArray {
        val s = sessions[h]
        return (s.inputInfo[s.inputNames.elementAt(i)]!!.info as TensorInfo).shape
    }

    @JvmStatic
    fun request(h: Int): Request = Request(sessions[h])

    class Request(private val session: OrtSession) {
        private val inputs = LinkedHashMap<String, OnnxTensor>()
        private var outData: List<ByteArray> = emptyList()
        private var outShape: List<LongArray> = emptyList()

        fun add(name: String, data: ByteArray, shape: LongArray) {
            val buf = ByteBuffer.allocateDirect(data.size).order(ByteOrder.LITTLE_ENDIAN)
            buf.put(data).flip()
            inputs[name] = OnnxTensor.createTensor(env, buf.asFloatBuffer(), shape)
        }

        fun run(names: Array<String>) {
            try {
                session.run(inputs, names.toSet()).use { res ->
                    val d = ArrayList<ByteArray>()
                    val s = ArrayList<LongArray>()
                    for (n in names) {
                        val t = res.get(n).get() as OnnxTensor
                        val fb = t.floatBuffer
                        val bb = ByteBuffer.allocate(fb.remaining() * 4).order(ByteOrder.LITTLE_ENDIAN)
                        bb.asFloatBuffer().put(fb)
                        d.add(bb.array())
                        s.add(t.info.shape)
                    }
                    outData = d
                    outShape = s
                }
            } finally {
                inputs.values.forEach { it.close() }
                inputs.clear()
            }
        }

        fun data(i: Int): ByteArray = outData[i]
        fun shape(i: Int): LongArray = outShape[i]
    }
}
