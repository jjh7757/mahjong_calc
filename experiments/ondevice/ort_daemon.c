// 태블릿 ONNX 추론 데몬: TCP 로 (모델 이름, float32 입력들)을 받아 돌리고 출력과 실행 시간을 돌려준다.
// PC 쪽 ort_proxy.py 가 서버 코드의 onnxruntime.InferenceSession 을 이것으로 바꿔 끼워, 서버 판독 흐름 전체를
// "추론만 태블릿" 으로 돌린다(adb forward tcp:9555 tcp:9555). 모델은 이 실행 파일과 같은 폴더에서 찾고 처음 쓸 때 올린다.
//   ./ort_daemon <port> <threads>
// 요청: u32 이름길이, 이름, u32 입력수, [u32 이름길이, 이름, u32 차원수, i64 차원…, float 데이터] …, u32 출력수, [u32 이름길이, 이름] …
// 응답: u32 상태(0 성공), f64 실행초, u32 출력수, [u32 차원수, i64 차원…, float 데이터] …   (실패면 상태 1 + u32 길이 + 메시지)
#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include "onnxruntime_c_api.h"

static const OrtApi *g;
static OrtEnv *env;
static OrtSessionOptions *so;
static OrtMemoryInfo *mi;

#define MAXM 16
static char *mname[MAXM];
static OrtSession *msess[MAXM];
static int nm;

static double now(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec + t.tv_nsec * 1e-9;
}

static int rd(int fd, void *b, size_t n) {
  char *p = b;
  while (n) {
    ssize_t k = read(fd, p, n);
    if (k <= 0) return -1;
    p += k; n -= k;
  }
  return 0;
}

static int wr(int fd, const void *b, size_t n) {
  const char *p = b;
  while (n) {
    ssize_t k = write(fd, p, n);
    if (k <= 0) return -1;
    p += k; n -= k;
  }
  return 0;
}

static char *rdstr(int fd) {
  uint32_t n;
  if (rd(fd, &n, 4)) return NULL;
  char *s = malloc(n + 1);
  if (rd(fd, s, n)) { free(s); return NULL; }
  s[n] = 0;
  return s;
}

static int fail(int fd, const char *msg) {
  uint32_t st = 1, n = strlen(msg);
  fprintf(stderr, "실패: %s\n", msg);
  wr(fd, &st, 4); wr(fd, &n, 4); wr(fd, msg, n);
  return 0;
}

static OrtSession *session(const char *name, char *err, size_t errn) {
  for (int i = 0; i < nm; i++) if (!strcmp(mname[i], name)) return msess[i];
  if (nm >= MAXM) { snprintf(err, errn, "모델이 너무 많음"); return NULL; }
  OrtSession *s;
  double a = now();
  OrtStatus *st = g->CreateSession(env, name, so, &s);
  if (st) { snprintf(err, errn, "%s", g->GetErrorMessage(st)); g->ReleaseStatus(st); return NULL; }
  fprintf(stderr, "모델 올림 %s %.3fs\n", name, now() - a);
  mname[nm] = strdup(name); msess[nm] = s; nm++;
  return s;
}

// 한 요청 처리. 연결이 끊기면 -1.
static int serve_one(int fd) {
  char err[512];
  char *model = rdstr(fd);
  if (!model) return -1;
  uint32_t nin;
  if (rd(fd, &nin, 4) || nin > 8) return -1;
  char *inn[8]; float *ind[8]; OrtValue *inv[8]; int64_t dims[8][8];
  for (uint32_t i = 0; i < nin; i++) {
    inn[i] = rdstr(fd);
    uint32_t nd;
    if (!inn[i] || rd(fd, &nd, 4) || nd > 8 || rd(fd, dims[i], nd * 8)) return -1;
    size_t cnt = 1;
    for (uint32_t d = 0; d < nd; d++) cnt *= dims[i][d];
    ind[i] = malloc(cnt * 4 + 4);
    if (rd(fd, ind[i], cnt * 4)) return -1;
    inv[i] = NULL;
    OrtStatus *st = g->CreateTensorWithDataAsOrtValue(mi, ind[i], cnt * 4, dims[i], nd, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &inv[i]);
    if (st) { g->ReleaseStatus(st); return -1; }
  }
  uint32_t nout;
  if (rd(fd, &nout, 4) || nout > 8) return -1;
  char *outn[8];
  for (uint32_t i = 0; i < nout; i++) if (!(outn[i] = rdstr(fd))) return -1;

  OrtSession *s = session(model, err, sizeof err);
  if (!s) { fail(fd, err); goto done; }
  OrtValue *outv[8] = {0};
  double a = now();
  OrtStatus *st = g->Run(s, NULL, (const char *const *)inn, (const OrtValue *const *)inv, nin, (const char *const *)outn, nout, outv);
  double secs = now() - a;
  if (st) { snprintf(err, sizeof err, "%s", g->GetErrorMessage(st)); g->ReleaseStatus(st); fail(fd, err); goto done; }
  uint32_t ok = 0;
  wr(fd, &ok, 4); wr(fd, &secs, 8); wr(fd, &nout, 4);
  for (uint32_t i = 0; i < nout; i++) {
    OrtTensorTypeAndShapeInfo *info;
    g->GetTensorTypeAndShape(outv[i], &info);
    size_t nd; g->GetDimensionsCount(info, &nd);
    int64_t od[8]; g->GetDimensions(info, od, nd);
    size_t cnt; g->GetTensorShapeElementCount(info, &cnt);
    g->ReleaseTensorTypeAndShapeInfo(info);
    float *y; g->GetTensorMutableData(outv[i], (void **)&y);
    uint32_t nd32 = nd;
    wr(fd, &nd32, 4); wr(fd, od, nd * 8); wr(fd, y, cnt * 4);
    g->ReleaseValue(outv[i]);
  }
done:
  for (uint32_t i = 0; i < nin; i++) { g->ReleaseValue(inv[i]); free(ind[i]); free(inn[i]); }
  for (uint32_t i = 0; i < nout; i++) free(outn[i]);
  free(model);
  return 0;
}

int main(int argc, char **argv) {
  int port = argc > 1 ? atoi(argv[1]) : 9555, threads = argc > 2 ? atoi(argv[2]) : 4;
  g = OrtGetApiBase()->GetApi(ORT_API_VERSION);
  g->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "daemon", &env);
  g->CreateSessionOptions(&so);
  g->SetIntraOpNumThreads(so, threads);
  g->SetSessionGraphOptimizationLevel(so, ORT_ENABLE_ALL);
  g->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &mi);

  int ls = socket(AF_INET, SOCK_STREAM, 0), one = 1;
  setsockopt(ls, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
  struct sockaddr_in ad = {0};
  ad.sin_family = AF_INET; ad.sin_port = htons(port); ad.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (bind(ls, (struct sockaddr *)&ad, sizeof ad) || listen(ls, 4)) { perror("bind"); return 1; }
  fprintf(stderr, "대기 127.0.0.1:%d 스레드 %d\n", port, threads);
  for (;;) {
    int fd = accept(ls, NULL, NULL);
    if (fd < 0) continue;
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    while (serve_one(fd) == 0) {}
    close(fd);
  }
}
