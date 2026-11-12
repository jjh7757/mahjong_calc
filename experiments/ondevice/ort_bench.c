// 태블릿 ONNX 시험: 모델 하나를 입력 텐서 하나로 여러 번 돌려 시간(첫 회·중앙·p90·최대)과 기대값과의 최대 차이를 찍는다.
// 앱과 무관하게 /data/local/tmp 에서 adb shell 로 돈다. 빌드는 build.sh.
//   ./ort_bench <model.onnx> <input.bin> <input_name> <ref.bin> <threads> <runs> <d0> <d1> ...
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "onnxruntime_c_api.h"

static const OrtApi *g;

static void check(OrtStatus *s) {
  if (s) {
    fprintf(stderr, "ORT 오류: %s\n", g->GetErrorMessage(s));
    exit(1);
  }
}

static double now(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec + t.tv_nsec * 1e-9;
}

static float *load(const char *path, size_t *n) {
  FILE *f = fopen(path, "rb");
  if (!f) { perror(path); exit(1); }
  fseek(f, 0, SEEK_END);
  long sz = ftell(f);
  fseek(f, 0, SEEK_SET);
  float *b = malloc(sz);
  if (fread(b, 1, sz, f) != (size_t)sz) { perror("read"); exit(1); }
  fclose(f);
  *n = sz / sizeof(float);
  return b;
}

static int cmp(const void *a, const void *b) {
  double x = *(const double *)a, y = *(const double *)b;
  return x < y ? -1 : x > y;
}

int main(int argc, char **argv) {
  if (argc < 8) {
    fprintf(stderr, "쓰는 법: %s model input.bin input_name ref.bin threads runs d0 [d1 ...]\n", argv[0]);
    return 2;
  }
  const char *model = argv[1], *inpath = argv[2], *inname = argv[3], *refpath = argv[4];
  int threads = atoi(argv[5]), runs = atoi(argv[6]);
  int nd = argc - 7;
  int64_t dims[8];
  size_t want = 1;
  for (int i = 0; i < nd; i++) { dims[i] = atoll(argv[7 + i]); want *= dims[i]; }

  g = OrtGetApiBase()->GetApi(ORT_API_VERSION);
  OrtEnv *env;
  check(g->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "bench", &env));
  OrtSessionOptions *so;
  check(g->CreateSessionOptions(&so));
  check(g->SetIntraOpNumThreads(so, threads));
  check(g->SetSessionGraphOptimizationLevel(so, ORT_ENABLE_ALL));

  double t0 = now();
  OrtSession *sess;
  check(g->CreateSession(env, model, so, &sess));
  double load_s = now() - t0;

  size_t n, nref;
  float *x = load(inpath, &n);
  float *ref = load(refpath, &nref);
  if (n != want) { fprintf(stderr, "입력 크기 %zu != 차원 곱 %zu\n", n, want); return 1; }

  OrtMemoryInfo *mi;
  check(g->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &mi));
  OrtValue *in = NULL;
  check(g->CreateTensorWithDataAsOrtValue(mi, x, n * sizeof(float), dims, nd, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &in));

  OrtAllocator *alloc;
  check(g->GetAllocatorWithDefaultOptions(&alloc));
  char *outname;
  check(g->SessionGetOutputName(sess, 0, alloc, &outname));
  const char *inn[] = {inname};
  const char *outn[] = {outname};

  double *t = calloc(runs, sizeof(double));
  double maxdiff = 0, first = 0;
  for (int r = 0; r < runs; r++) {
    OrtValue *out = NULL;
    double a = now();
    check(g->Run(sess, NULL, inn, (const OrtValue *const *)&in, 1, outn, 1, &out));
    t[r] = now() - a;
    if (r == 0) {
      first = t[0];
      float *y;
      check(g->GetTensorMutableData(out, (void **)&y));
      OrtTensorTypeAndShapeInfo *info;
      check(g->GetTensorTypeAndShape(out, &info));
      size_t cnt;
      check(g->GetTensorShapeElementCount(info, &cnt));
      g->ReleaseTensorTypeAndShapeInfo(info);
      if (cnt != nref) { fprintf(stderr, "출력 크기 %zu != 기대값 %zu\n", cnt, nref); return 1; }
      for (size_t i = 0; i < cnt; i++) {
        double d = fabs((double)y[i] - ref[i]);
        if (d > maxdiff) maxdiff = d;
      }
    }
    g->ReleaseValue(out);
  }
  // 첫 회는 따로(예열), 중앙·p90·최대는 2회째부터.
  int m = runs > 1 ? runs - 1 : 1;
  double *s = runs > 1 ? t + 1 : t;
  qsort(s, m, sizeof(double), cmp);
  printf("RESULT model=%s threads=%d runs=%d load=%.3f first=%.3f median=%.3f p90=%.3f max=%.3f maxdiff=%.3g\n",
         model, threads, runs, load_s, first, s[m / 2], s[(int)ceil(m * 0.9) - 1], s[m - 1], maxdiff);
  return 0;
}
