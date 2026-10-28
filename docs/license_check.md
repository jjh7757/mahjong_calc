# YOLO26(HaseLab) 라이선스 확인 (2026-10-26)

법률 자문이 아니라 공개 자료를 정리한 것이다.

## 확인한 것

### HaseLab/mahjong-models
- 만든 곳: 후쿠이대학 공학부 長谷川研究室(하세가와 다쓰히토 長谷川 達人 준교수). GitHub `haselab-dev`, 연구실 사이트 http://haselab.fuis.u-fukui.ac.jp/
- 연락처(연구실 사이트에 공개): **t-hase@u-fukui.ac.jp**
- Hugging Face 저장소에 **라이선스 표기 없음**(지금 판). 처음 올린 판(커밋 3735654)의 카드에는 `license: other` 만 있었다. 학습 코드 `haselab-dev/mahjong-cg` 는 비공개(404). 같은 조직의 다른 공개 저장소는 MIT 2개·없음 4개.
- 표기가 없으면 보통 "저작권자가 모든 권리를 가짐"으로 본다 → 실험(내려받아 돌려 보기)과 서비스에 쓰는 것은 별개. 서비스에 쓰려면 허락이 필요.
- 참고: 시장 조사(`market_research.md`)의 후쿠이대 Projection Mahjong 연구와 같은 대학이다(같은 연구실인지는 미확인).

### Ultralytics(YOLO26 을 학습한 도구)
https://www.ultralytics.com/license 의 입장:
- "All Ultralytics YOLO trained models fall under the AGPL-3.0 License by default." — 학습 코드와 그 코드로 만든 모델 모두 AGPL-3.0.
- AGPL 을 지키려면 파생 작업 전체(스크립트·설정·해당하면 모델 가중치 포함)의 소스를 공개해야 한다.
- Enterprise 라이선스가 필요한 경우: 상용 제품·서비스, 비공개 소프트웨어, **SaaS·API·클라우드에서 YOLO 를 쓰는 경우**, 기기 내장, 상용으로 쓰는 맞춤 학습 모델 등.
- ONNX 로 바꿔 onnxruntime 으로만 돌리는 경우(ultralytics 코드 미실행)를 따로 다루지는 않는다. 하지만 "모델 자체가 AGPL" 이라는 입장이라, 바꿔도 벗어난다고 보기 어렵다.

### 우리 쪽 상태
- 인식 서버 `jjh7757/mahjong-recognizer`: **공개 저장소, 라이선스 파일 없음**.
- YOLO26 은 지금 로컬 실험(`experiments/yolo/`)에서만 쓰고, 앱·운영 서버에는 없다. 모델 파일은 저장소 밖(`C:/Users/jjh7757/dev/_downloads/`).

## 그래서 달라지는 것

| 쓰임 | HaseLab 허락 | Ultralytics(AGPL) | 할 일 |
| --- | --- | --- | --- |
| 로컬 실험·이력서 기록 | 공개 모델을 내려받아 실험 — 문제 소지 작음(출처 표시) | 배포·서비스가 아니면 의무 없음 | 지금처럼 |
| 개인용·비상업 서비스(우리 서버에서 추론) | **필요** | 서버 코드를 AGPL 로 공개(이미 공개 저장소 → LICENSE 추가) | HaseLab 회신 받기 |
| 매장 대상 유료 서비스 | **상업 이용 허락 필요** | Enterprise 라이선스 또는 AGPL 아닌 도구로 만든 우리 모델 | 우리 사진으로 직접 학습(Apache·BSD 계열 검출기)이 가장 깔끔 |
| 폰에 모델 넣기 | 필요 | 앱도 AGPL 대상이 될 수 있음 | 하지 않는다(원래 원칙과도 같음) |

## 문의 메일 초안(보내는 것은 사용자가 확인 후 직접)

받는 사람: t-hase@u-fukui.ac.jp
제목: Hugging Face「HaseLab/mahjong-models」の利用条件についてのお問い合わせ

```
長谷川 達人 先生

突然のご連絡失礼いたします。韓国で個人開発をしております、[お名前]と申します。

Hugging Face で公開されている「HaseLab/mahjong-models」（regions-yolo-26n、tile-yolo-26n、classifier-resnet50）を拝見し、
自作の麻雀点数計算アプリの研究目的の実験で試用させていただきました。
卓を上から撮影した写真から和了者の手牌・副露・河・ドラを読み取り、点数を自動計算するアプリです
（点数計算は端末内、画像の読み取りは自前のサーバーで行っています）。
手元の写真での評価では、領域分割と牌種分類の精度が非常に高く、大変参考になりました。

つきましては、以下の点についてご教示いただけますと幸いです。

1. 本モデルのライセンス（利用条件）はどのようになっていますでしょうか。
   モデルカードにライセンスの記載が見当たらなかったため、お伺いいたします。
2. 非商用の個人プロジェクトとして、本モデル（ONNX 形式に変換・int8 量子化したもの）を
   自前のサーバー上で推論に使用させていただくことは可能でしょうか。
   その場合、クレジット表記の方法にご希望があればお教えください。
3. 将来、麻雀店向けのサービスとして商用利用を検討する場合、利用は可能でしょうか。
   可能な場合の条件（Ultralytics のライセンスとの関係を含め）をお教えいただけますと幸いです。

評価結果（写真・手順・精度）は、ご希望でしたら共有いたします。
ご多忙のところ恐縮ですが、ご検討のほどよろしくお願いいたします。

[お名前]
[メールアドレス]
[GitHub など（任意）]
```

한국어 요지: Hugging Face 의 HaseLab/mahjong-models 를 마작 점수 계산 앱 실험에 써 봤고 정확도가 좋았다. (1) 모델 라이선스는 무엇인지(카드에 표기가 없어서), (2) 비상업 개인 프로젝트로 ONNX·int8 로 바꿔 우리 서버에서 추론에 써도 되는지와 출처 표기 방법, (3) 나중에 마작방 대상 상업 서비스로 쓸 수 있는지와 조건(Ultralytics 라이선스와의 관계 포함)을 묻는다. 원하면 평가 결과를 공유하겠다고 덧붙임.

## 결정(2026-10-26 사용자): YOLO11(nikmomo/Mahjong-YOLO)만 쓰고, 상업적으로 쓰지 않는다

확인한 사슬:
- 모델 저장소 `github.com/nikmomo/Mahjong-YOLO`: README 에 "licensed under the MIT License". 가중치가 MIT 에 포함되는지는 따로 적혀 있지 않음.
- 학습 데이터 Kaggle `shinz114514/mahjong-hand-photos-taken-with-mobile-camera`: Kaggle API 메타데이터 `licenseName: MIT`(2026-10-26 조회).
- 학습 도구 Ultralytics YOLO11: 학습한 모델은 기본 AGPL-3.0(위 Ultralytics 입장).

비상업으로 쓸 때 할 일(이 셋을 하면 공개 자료 기준으로 걸리는 것이 없다):
1. **인식 서버 `jjh7757/mahjong-recognizer` 에 AGPL-3.0 LICENSE 추가** — 서버가 네트워크로 서비스하므로 소스 공개 의무. 저장소는 이미 공개.
2. **출처 표기**(서버 README·NOTICE): nikmomo/Mahjong-YOLO(MIT, 저작권 문구·라이선스 전문), Kaggle 데이터셋 shinz114514(MIT), Ultralytics YOLO11(AGPL-3.0).
3. **모델은 서버에서만 돌린다** — 앱에 넣으면 앱도 AGPL 파생물로 볼 여지가 생긴다. 앱은 서버와 HTTP 로만 통신.
4. HaseLab YOLO26 은 운영에 쓰지 않는다(로컬 실험 기록만).
나중에 상업으로 바꾸면 Ultralytics Enterprise 또는 Ultralytics 를 안 쓰는 검출기로 다시 학습해야 한다.
