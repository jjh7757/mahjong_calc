// 매장 손님 설문 구글 폼 만들기 (질문 원본: docs/survey_questions.md)
// 쓰는 법: script.google.com → 새 프로젝트 → 이 파일 내용 붙여넣기 → createSurveyForm 실행 → 권한 허용
// 실행 로그에 응답 링크·편집 링크·응답 시트 링크가 찍힌다.

var DESCRIPTION =
  '오프라인 마작 매장에서 점수 계산·정산·기록을 돕는 기능에 대한 설문입니다. 3분 정도 걸립니다.';
var Q_CALC = '3. 화료했을 때 점수 계산을 직접 하실 수 있나요?';
var Q_SAT = '4. 오늘 보시거나 써 보신 기능은 얼마나 만족스러우셨나요?';
var Q_USE = '5. 이런 게 테이블에 있으면 쓰시겠어요?';
var Q_USE_WHY = '5-1. "안 쓴다"를 고르셨다면 이유는?';
var Q_WAIT = '6. 화료 뒤 결과가 나오기까지 몇 초면 기다릴 만한가요?';
var Q_WRONG = '7. 결과가 가끔 틀려서 손으로 고쳐야 한다면?';
var Q_CAMERA = '8. 카메라가 테이블을 찍는 것에 거부감이 있나요?';
var Q_MOUNT = '9. 테이블 위 카메라는 어떻게 다는 게 좋을까요?';
var Q_MOUNT_HELP = '바닥 거치대: 테이블 옆 바닥에 세운 스탠드가 위에서 내려다봅니다(지금 방식). 천장 카메라: 테이블 위 천장에 붙여 둡니다.';
var Q_MOUNT_OPTIONS = ['바닥 거치대가 낫다', '천장 카메라가 낫다', '상관없다', '둘 다 거슬린다'];
var Q_PHONE = '10. 카메라는 매장에 그대로 두고, 점수를 보여 주고 고치는 화면을 태블릿 대신 손님 휴대폰에 앱을 깔아 쓴다면 어떠세요?';
var Q_PHONE_OPTIONS = ['좋다, 내 폰에 깔아 쓰겠다', '테이블에 한 명만 깔면 된다면 괜찮다', '매장에 태블릿이 있는 게 낫다', '앱을 깔아야 하면 안 쓴다'];
var Q_WANT = '11. 가장 갖고 싶은 기능 두 개만 고르면?';
var Q_HAIFU = '12. (선택 기능) 패보(기보)를 남기려면 국이 끝날 때마다 4명 모두 손패를 펼쳐 카메라에 보여야 한다면, 이 기능을 쓰시겠어요?';
var Q_HAIFU_HELP = '패보는 원하는 국만 골라 남길 수 있습니다. 남기고 싶은 국에서만 4명이 손패를 펼치면 됩니다.';
var Q_HAIFU_OPTIONS = ['매 국 펼쳐서라도 쓰겠다', '남기고 싶은 국만 골라 쓰겠다', '리그전·중요한 대국에서만 쓰겠다',
  '번거로워서 안 쓴다', '손패를 보여 주기 싫어서 안 쓴다'];
var Q_PAY = '13. 이 기능이 있는 테이블(매장)이라면 추가 요금을 얼마까지 내시겠어요?';
var Q_PLAN = '14. 매장 태블릿을 쓰고 매장에 추가 요금을 내는 방식과, 내 휴대폰으로 정해진 횟수까지 무료로 쓰고 그 이상은 결제하는 방식 중 어느 쪽이 나은가요?';
var Q_PLAN_HELP = '점수 판독마다 AI 서버 비용이 들어서, 어느 방식이든 일정 이상은 요금이 필요합니다.';
var Q_PLAN_OPTIONS = ['매장 태블릿 + 매장 추가 요금', '내 휴대폰 + 무료 횟수 넘으면 결제', '둘 다 괜찮다', '돈을 내야 하면 둘 다 안 쓴다'];
var FEEDBACK_TITLE = '15. 이 밖에 있었으면 하는 기능이나 고쳤으면 하는 점이 있으면 자유롭게 적어 주세요.';

function createSurveyForm() {
  var form = FormApp.create('마작 매장 이용 설문');
  form.setDescription(DESCRIPTION);
  form.setProgressBar(true);
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage('응답해 주셔서 감사합니다!');

  // A. 응답자
  form.addSectionHeaderItem().setTitle('A. 응답자');
  choice(form, '1. 마작 한 지 얼마나 됐나요?',
    ['6개월 미만', '6개월~2년', '2~5년', '5년 이상']);
  choice(form, '2. 이 매장(또는 오프라인 매장)에 얼마나 자주 오세요?',
    ['오늘 처음', '한 달에 1번 미만', '한 달에 1~3번', '주 1번 이상']);
  choice(form, Q_CALC,
    ['부수까지 다 한다', '판수는 되는데 부수는 막힌다', '주로 남이 해 준다', '거의 못 한다']);

  // C. 데모 뒤
  form.addPageBreakItem().setTitle('C. 데모를 본 뒤')
    .setHelpText('진행자가 데모를 보여 드린 뒤 답해 주세요.\n' +
      '테이블 위 카메라가 화료 때 판을 찍고, 옆 태블릿이 손패를 읽어 점수를 계산해 점수판에 바로 반영합니다. 틀리면 화면에서 고칩니다.');
  form.addScaleItem().setTitle(Q_SAT).setBounds(1, 5).setLabels('매우 불만족', '매우 만족').setRequired(true);
  choice(form, Q_USE, ['꼭 쓰겠다', '있으면 쓴다', '상관없다', '안 쓴다']);
  form.addParagraphTextItem().setTitle(Q_USE_WHY);
  choice(form, Q_WAIT, ['5초', '10초', '20초', '30초 넘어도 괜찮다']);
  choice(form, Q_WRONG, ['그래도 쓴다', '열 번에 한 번 정도면 괜찮다', '한 번이라도 틀리면 안 쓴다']);
  choice(form, Q_CAMERA, ['전혀 없다', '손패만 아니면 괜찮다', '녹화·저장되면 싫다', '싫다']);
  choice(form, Q_MOUNT, Q_MOUNT_OPTIONS).setHelpText(Q_MOUNT_HELP);
  choice(form, Q_PHONE, Q_PHONE_OPTIONS);
  var want = checks(form, Q_WANT,
    ['점수 자동 계산', '점수판·최종 정산 자동', '대국 기록·개인 통계', '버림패 복기(기보)', '초보 도움(대기패·역 설명)']);
  want.setValidation(FormApp.createCheckboxValidation()
    .setHelpText('두 개까지 골라 주세요.').requireSelectAtMost(2).build());
  choice(form, Q_HAIFU, Q_HAIFU_OPTIONS).setHelpText(Q_HAIFU_HELP);
  choice(form, Q_PAY, ['안 낸다', '시간당 500원', '시간당 1,000원', '시간당 2,000원 이상']);
  choice(form, Q_PLAN, Q_PLAN_OPTIONS).setHelpText(Q_PLAN_HELP);

  // D. 마무리
  form.addPageBreakItem().setTitle('D. 마무리');
  form.addParagraphTextItem().setTitle(FEEDBACK_TITLE).setHelpText('선택 사항입니다.');

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
