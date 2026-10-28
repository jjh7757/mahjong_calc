import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../services/camera_head.dart';

/// 카메라 헤드 화면의 QR 을 스캔해 [CameraHeadLink](주소 + 토큰)를 돌려준다.
/// 카메라 헤드 QR 이 보이면 바로 닫히므로 비추기만 하면 된다.
class QrScanScreen extends StatefulWidget {
  const QrScanScreen({super.key});

  @override
  State<QrScanScreen> createState() => _QrScanScreenState();
}

class _QrScanScreenState extends State<QrScanScreen> {
  final MobileScannerController _ctl = MobileScannerController(
    formats: const [BarcodeFormat.qrCode],
    detectionSpeed: DetectionSpeed.noDuplicates,
  );
  bool _done = false;
  String? _hint;

  @override
  void dispose() {
    _ctl.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (_done) return;
    for (final b in capture.barcodes) {
      final raw = b.rawValue;
      if (raw == null) continue;
      final link = CameraHeadLink.fromQr(raw);
      if (link != null) {
        _done = true;
        Navigator.pop(context, link);
        return;
      }
    }
    if (mounted) setState(() => _hint = '카메라 헤드 QR 이 아닙니다');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(title: const Text('카메라 헤드 QR 스캔')),
      body: Stack(
        fit: StackFit.expand,
        children: [
          MobileScanner(
            controller: _ctl,
            onDetect: _onDetect,
            errorBuilder: (context, error) => Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  '카메라를 열 수 없습니다: ${error.errorDetails?.message ?? error.errorCode.name}\n'
                  '카메라 권한을 확인하거나, 더보기 "원격 카메라 주소" 에 직접 적으세요.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white70),
                ),
              ),
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: SafeArea(
              child: Container(
                color: Colors.black.withValues(alpha: 0.55),
                padding: const EdgeInsets.all(12),
                child: Text(
                  _hint ?? '카메라 헤드 기기 화면의 QR 을 비추세요. 인식되면 바로 연결됩니다.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
