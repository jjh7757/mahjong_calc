"""overlay_score 두 결과(원본 / --scale) 나란히 비교(2026-11-12)."""
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
R = "experiments/ondevice/results/overlay_score_prod_{}.json"
A, B = sys.argv[1], sys.argv[2]
ds = {t: json.load(open(R.format(t), encoding="utf-8")) for t in (A, B)}
for t, d in ds.items():
    a = d["summary"]["all"]
    print(t, d["_meta"]["recognizer"], {k: a[k] for k in ("scenes", "ok", "hand_ok", "meld_ok", "hit", "want", "other_hand_scenes", "box_scenes", "box_n", "box_found", "box_own_ok", "box_extra")})
    print("  틀린 역할", dict(list(a["conf_wrong"].items())[:8]))
    for k in ("bcd", "visit", "visit1107"):
        if k in d["summary"]:
            b = d["summary"][k]; print("  ", k, b["scenes"], "ok", b["ok"], "hit", b["hit"], "/", b["want"])
    secs = sorted(r["secs"] for r in d["scenes"].values()); print("  secs med", secs[len(secs) // 2], "max", secs[-1])
f, s = ds[A]["scenes"], ds[B]["scenes"]
for k in f:
    if f[k]["ok"] != s[k]["ok"] or f[k]["hit"] != s[k]["hit"] or f[k]["other_hand"] != s[k]["other_hand"]:
        print(k, f"{A} ok={f[k]['ok']} {f[k]['hit']}/{f[k]['want']} 헛손패 {f[k]['other_hand']}", "|", f"{B} ok={s[k]['ok']} {s[k]['hit']} 헛손패 {s[k]['other_hand']}")
        if not s[k]["ok"]:
            print("    ", B, "손패", " ".join(sorted(s[k]["hand"] + s[k]["loose"])), "| 정답", " ".join(sorted(s[k]["want_hand"])), "| 울기", " ".join(sorted(s[k]["meld"])), "정답", " ".join(sorted(s[k]["want_meld"])))
