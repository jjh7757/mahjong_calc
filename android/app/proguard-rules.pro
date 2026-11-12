# 기기 판독 실험(exp/on-device-read): Python(Chaquopy)이 이름으로만 부르는 클래스는 R8 이 지우거나 이름을 바꾸지 않게.
-keep class dev.jjh.mahjong_calc.OrtBridge { *; }
-keep class dev.jjh.mahjong_calc.OrtBridge$Request { *; }
-keep class ai.onnxruntime.** { *; }
