import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

/// 매장 손님 설문(구글 폼 응답 링크, docs/survey_questions.md).
const surveyUrl =
    'https://docs.google.com/forms/d/e/1FAIpQLSedm1H2rNsRlGejkKA_Bk18hDHIxRO82WP8VZUOYLn2saN4Mw/viewform';

/// 설문 QR 을 크게 띄운다. 손님이 자기 폰으로 찍어 들어간다.
Future<void> showSurveyQr(BuildContext context) {
  return showDialog<void>(
    context: context,
    builder: (context) => AlertDialog(
      key: const ValueKey('survey-qr'),
      title: const Text('설문 참여', textAlign: TextAlign.center),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('휴대폰 카메라로 찍어 주세요 (3분)', textAlign: TextAlign.center),
          const SizedBox(height: 16),
          // AlertDialog 는 내용 크기를 미리 재는데 QrImageView(LayoutBuilder)는 못 잰다 → 크기를 고정.
          Container(
            padding: const EdgeInsets.all(12),
            color: Colors.white,
            child: SizedBox.square(
              dimension: 260,
              child: QrImageView(
                data: surveyUrl,
                padding: EdgeInsets.zero,
                backgroundColor: Colors.white,
              ),
            ),
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('닫기')),
      ],
    ),
  );
}
