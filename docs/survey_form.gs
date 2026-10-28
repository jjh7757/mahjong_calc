// 매장 손님 설문 구글 폼 만들기 (질문 원본: docs/survey_questions.md)
// 쓰는 법: script.google.com → 새 프로젝트 → 이 파일 내용 붙여넣기 → createSurveyForm 실행 → 권한 허용
// 실행 로그에 응답 링크·편집 링크·응답 시트 링크가 찍힌다.

function createSurveyForm() {
  var form = FormApp.create('마작 매장 이용 설문');
  form.setDescription(
    '오프라인 마작 매장에서 점수 계산·정산·기록이 얼마나 불편한지 알아보는 설문입니다. 3분 정도 걸립니다.\n' +
    '연락처(마지막 문항)는 선택이며 시험판 안내 외에는 쓰지 않습니다.'
  );
  form.setProgressBar(true);
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage('응답해 주셔서 감사합니다!');

  // A. 응답자
  form.addSectionHeaderItem().setTitle('A. 응답자');
  choice(form, '1. 마작 한 지 얼마나 됐나요?',
    ['6개월 미만', '6개월~2년', '2~5년', '5년 이상']);
  choice(form, '2. 이 매장(또는 오프라인 매장)에 얼마나 자주 오세요?',
    ['오늘 처음', '한 달에 1번 미만', '한 달에 1~3번', '주 1번 이상']);
  choice(form, '3. 주로 어떤 룰로 치세요?',
    ['4인 반장전', '4인 동풍전', '3인'], true);
  choice(form, '4. 화료했을 때 점수 계산을 직접 하실 수 있나요?',
    ['부수까지 다 한다', '판수는 되는데 부수는 막힌다', '주로 남이 해 준다', '거의 못 한다']);

  // B. 지금 겪는 불편 (데모 전)
  form.addPageBreakItem().setTitle('B. 지금 겪는 불편')
    .setHelpText('오늘 또는 최근 오프라인 대국을 떠올리며 답해 주세요.');
  choice(form, '5. 오늘(또는 지난번) 대국에서 화료 뒤 점수 정하느라 판이 멈추거나 의견이 갈린 적이 있었나요?',
    ['거의 매 국', '반장에 몇 번', '거의 없음']);
  checks(form, '6. 점수 계산이 막히면 보통 어떻게 하세요? (여러 개 선택)',
    ['잘 아는 사람에게 물어봄', '점수표·앱 검색', '사장님께 물어봄', '대충 정하고 넘어감']);
  choice(form, '7. 점봉 주고받기나 마지막 정산(우마·오카)에서 틀리거나 다시 센 적이 있나요?',
    ['자주', '가끔', '없음']);
  choice(form, '8. 대국 결과(국별 점수, 최종 순위)를 기록으로 남기세요?',
    ['안 남김', '메모·점수판 사진', '앱·스프레드시트'], true);
  choice(form, '9. 오프라인 대국에서 가장 귀찮은 걸 하나만 고르면?',
    ['부수·점수 계산', '점봉 주고받기', '최종 정산', '기록 남기기', '딱히 없음']);

  // C. 데모 뒤
  form.addPageBreakItem().setTitle('C. 데모를 본 뒤')
    .setHelpText('진행자가 데모를 보여 드린 뒤 답해 주세요.\n' +
      '테이블 위 카메라가 화료 때 판을 찍고, 옆 태블릿이 손패를 읽어 점수를 계산해 점수판에 바로 반영합니다. 틀리면 화면에서 고칩니다.');
  choice(form, '10. 이런 게 테이블에 있으면 쓰시겠어요?',
    ['꼭 쓰겠다', '있으면 쓴다', '상관없다', '안 쓴다']);
  form.addParagraphTextItem().setTitle('10-1. "안 쓴다"를 고르셨다면 이유는?');
  choice(form, '11. 화료 뒤 결과가 나오기까지 몇 초면 기다릴 만한가요?',
    ['5초', '10초', '20초', '30초 넘어도 괜찮다']);
  choice(form, '12. 결과가 가끔 틀려서 손으로 고쳐야 한다면?',
    ['그래도 쓴다', '열 번에 한 번 정도면 괜찮다', '한 번이라도 틀리면 안 쓴다']);
  choice(form, '13. 카메라가 테이블을 찍는 것에 거부감이 있나요?',
    ['전혀 없다', '손패만 아니면 괜찮다', '녹화·저장되면 싫다', '싫다']);
  var q14 = checks(form, '14. 가장 갖고 싶은 기능 두 개만 고르면?',
    ['점수 자동 계산', '점수판·최종 정산 자동', '대국 기록·개인 통계', '버림패 복기(기보)', '초보 도움(대기패·역 설명)']);
  q14.setValidation(FormApp.createCheckboxValidation()
    .setHelpText('두 개까지 골라 주세요.').requireSelectAtMost(2).build());
  choice(form, '15. 이 기능이 있는 테이블(매장)이라면 추가 요금을 얼마까지 내시겠어요?',
    ['안 낸다', '시간당 500원', '시간당 1,000원', '시간당 2,000원 이상']);
  form.addParagraphTextItem().setTitle('16. 오히려 이게 있으면 불편하거나 싫을 점은?');

  // D. 마무리
  form.addPageBreakItem().setTitle('D. 마무리');
  form.addTextItem()
    .setTitle('17. 나중에 시험판을 써 볼 의향이 있으면 연락처(카톡 ID 등)를 남겨 주세요.')
    .setHelpText('선택 사항입니다. 시험판 안내 외에는 쓰지 않습니다.');

  var sheet = SpreadsheetApp.create('마작 매장 이용 설문 (응답)');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());

  Logger.log('응답 링크: ' + form.getPublishedUrl());
  Logger.log('편집 링크: ' + form.getEditUrl());
  Logger.log('응답 시트: ' + sheet.getUrl());
}

function choice(form, title, options, other) {
  var item = form.addMultipleChoiceItem().setTitle(title).setChoiceValues(options).setRequired(true);
  if (other) item.showOtherOption(true);
  return item;
}

function checks(form, title, options) {
  return form.addCheckboxItem().setTitle(title).setChoiceValues(options).setRequired(true);
}
