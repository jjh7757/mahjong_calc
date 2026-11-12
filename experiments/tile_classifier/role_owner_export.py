"""역할 모델 D(역할 + 주인 자리, role_owner_train_d.SetNetOwner)를 겹쳐 보기용 ONNX 로(2026-11-12, `docs/role_owner_plan_1111.md` 5단계 5a).

  입력 x[1, n, 11](사진 기준 = roles.tokens(..., side "bottom", 11) 토큰, n 가변)
  출력 role[1, n, 6]  = 씨드 3 역할 softmax 평균(순서 roles.ROLES = hand·meld·river·wall·pair·loose)
       owner[1, n, 4] = 씨드 3 주인 softmax 평균(순서 roles.SIDES = bottom·right·top·left, 사진 기준)
지금 역할 ONNX(role_export.py)와 같은 방식: nn.TransformerEncoder 를 평범한 행렬곱으로 옮긴 manual_forward(그 함수를 그대로 부르고
머리만 바꿔 끼움) → 씨드 softmax 평균, opset 17, dynamo=False, 길이 n 은 dynamic_axes. 패딩 없음(한 장면씩).

검사 (5a-1): torch(role_D_all.pt, role_owner_train_d.probs_d — 학습·채점 때와 같은 nn 모듈 경로)와 ONNX 를 라벨 토큰 전부에 돌려 비교
  - 화료 41장: labels_v2_owner.json(role_owner_eval.e1_scenes(all_scenes=True)), 사진 기준 토큰 x0
  - 프레임 84장: role_owner_eval.e3_scenes("test")·("dev")(frames_rects.json 캐시)
  기준: 모든 상자(앞면·뒷면 토큰 전부)에서 역할 argmax·주인 argmax 같음, 확률 최대 차 ≤ 1e-4. 전부 학습 가중치라 정확도는 내지 않는다(일치만).

  python -I -X utf8 experiments/tile_classifier/role_owner_export.py
결과 server_bench/models/tile-roles-owner-d.onnx, 검사 data/role/owner/export_d_check.json.
"""
from __future__ import annotations

import json
import sys
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_owner_eval as roe  # noqa: E402  (v3r15d 환경 변수 · e1_scenes · e3_scenes)

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch import nn  # noqa: E402

import role_export as rex  # noqa: E402  (manual_forward — 지금 역할 ONNX 와 같은 계산)
import role_owner_train_d as rtd  # noqa: E402  (load_nets_d · probs_d)

SRC = HERE / "data" / "role" / "owner" / "role_D_all.pt"
DST = HERE / "server_bench" / "models" / "tile-roles-owner-d.onnx"
CHECK = HERE / "data" / "role" / "owner" / "export_d_check.json"
TOL = 1e-4


def hidden(net: rtd.SetNetOwner, x: torch.Tensor) -> torch.Tensor:
    """role_export.manual_forward 를 그대로 부르되 head 를 항등으로 바꿔 끼워 마지막 은닉 h 를 받는다(역할·주인 머리가 같은 h 를 씀)."""
    shim = types.SimpleNamespace(inp=net.inp, enc=net.enc, head=lambda h: h, relbias=False)
    return rex.manual_forward(shim, x)


class EnsembleD(nn.Module):
    def __init__(self, nets: list[nn.Module]):
        super().__init__()
        self.nets = nn.ModuleList(nets)

    def forward(self, x):
        rs_, os_ = [], []
        for n in self.nets:
            h = hidden(n, x)
            rs_.append(torch.softmax(n.head(h), -1))
            os_.append(torch.softmax(n.owner(h), -1))
        return torch.stack(rs_).mean(0), torch.stack(os_).mean(0)


def compare(sess, nets, scenes: list[dict], key: str, set_name: str) -> dict:
    n_box = role_diff = owner_diff = 0
    worst_r = worst_o = 0.0
    bad = []
    for sc in scenes:
        x = np.asarray(sc[key], np.float32)
        pr_t, po_t = rtd.probs_d(nets, x)
        pr_o, po_o = sess.run(["role", "owner"], {"x": x[None]})
        pr_o, po_o = pr_o[0], po_o[0]
        assert pr_o.shape == pr_t.shape and po_o.shape == po_t.shape, (sc["name"], pr_o.shape, pr_t.shape)
        dr, do = float(np.abs(pr_o - pr_t).max()), float(np.abs(po_o - po_t).max())
        worst_r, worst_o = max(worst_r, dr), max(worst_o, do)
        ra, oa = pr_t.argmax(1) != pr_o.argmax(1), po_t.argmax(1) != po_o.argmax(1)
        n_box += len(x)
        role_diff += int(ra.sum())
        owner_diff += int(oa.sum())
        for i in np.where(ra | oa)[0]:
            bad.append({"scene": sc["name"], "row": int(i), "face": bool(i < sc["n_face"]), "torch": [int(pr_t[i].argmax()), int(po_t[i].argmax())],
                        "onnx": [int(pr_o[i].argmax()), int(po_o[i].argmax())]})
    ok = role_diff == 0 and owner_diff == 0 and worst_r <= TOL and worst_o <= TOL
    return {"set": set_name, "scenes": len(scenes), "boxes": n_box, "faces": sum(s["n_face"] for s in scenes), "role_argmax_diff": role_diff,
            "owner_argmax_diff": owner_diff, "role_prob_max_diff": worst_r, "owner_prob_max_diff": worst_o, "bad": bad[:20], "ok": ok}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(8)
    t0 = time.time()
    nets = rtd.load_nets_d(SRC)
    assert len(nets) == 3 and all(rtd.has_owner(n) and n.feat == 11 and not n.relbias for n in nets)
    ens = EnsembleD(nets).eval()
    # 수동 계산이 원래 모듈(nn.TransformerEncoder, probs_d)과 같은지(무작위 입력)
    with torch.no_grad():
        x = torch.randn(1, 37, 11)
        a, b = ens(x)
        pr, po = rtd.probs_d(nets, x[0].numpy())
        print("수동 계산 대 원래: 역할", float((a[0] - torch.tensor(pr)).abs().max()), "주인", float((b[0] - torch.tensor(po)).abs().max()))
    DST.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(ens, (x,), str(DST), input_names=["x"], output_names=["role", "owner"],
                      dynamic_axes={"x": {1: "n"}, "role": {1: "n"}, "owner": {1: "n"}}, opset_version=17, dynamo=False)
    size = DST.stat().st_size
    print("저장", DST, size, "바이트", size // 1024, "KB")

    import onnxruntime as ort

    sess = ort.InferenceSession(str(DST), providers=["CPUExecutionProvider"])
    io_ = {"inputs": [(i.name, i.shape, i.type) for i in sess.get_inputs()], "outputs": [(o.name, o.shape, o.type) for o in sess.get_outputs()]}
    print("ONNX 입출력", io_)
    rnd = []
    for n in (1, 5, 37, 120, 300):
        x = torch.randn(1, n, 11)
        with torch.no_grad():
            a, b = ens(x)
        o = sess.run(["role", "owner"], {"x": x.numpy()})
        rnd.append({"n": n, "role": float(np.abs(a.numpy() - o[0]).max()), "owner": float(np.abs(b.numpy() - o[1]).max()),
                    "role_sum_err": float(np.abs(o[0].sum(-1) - 1).max()), "owner_sum_err": float(np.abs(o[1].sum(-1) - 1).max())})
    print("무작위 입력 ONNX 대 수동", rnd)

    # 5a-1: 라벨 토큰 전부
    s1, info1 = roe.e1_scenes(all_scenes=True)
    rects_all = json.loads(roe.RECTS_CACHE.read_text(encoding="utf-8"))
    s3t, _ = roe.e3_scenes("test", rects_all)
    s3d, _ = roe.e3_scenes("dev", rects_all)
    res = [compare(sess, nets, s1, "x0", "화료 41장(labels_v2_owner.json, 사진 기준 x0)"),
           compare(sess, nets, s3t, "x0", "프레임-시험 49장(e3 test)"),
           compare(sess, nets, s3d, "x0", "프레임-개발 35장(e3 dev)")]
    for r in res:
        print({k: v for k, v in r.items() if k != "bad"}, r["bad"][:5])
    tot = {"scenes": sum(r["scenes"] for r in res), "boxes": sum(r["boxes"] for r in res), "faces": sum(r["faces"] for r in res),
           "role_argmax_diff": sum(r["role_argmax_diff"] for r in res), "owner_argmax_diff": sum(r["owner_argmax_diff"] for r in res),
           "role_prob_max_diff": max(r["role_prob_max_diff"] for r in res), "owner_prob_max_diff": max(r["owner_prob_max_diff"] for r in res)}
    tot["ok"] = all(r["ok"] for r in res)
    print("5a-1 전체", tot, "→", "통과" if tot["ok"] else "실패")
    out = {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "src": str(SRC.relative_to(HERE)), "dst": str(DST.relative_to(HERE)), "size_bytes": size,
           "opset": 17, "io": io_, "random_vs_manual": rnd, "criterion": f"모든 상자 역할·주인 argmax 같음, 확률 최대 차 ≤ {TOL}",
           "e1_info": info1, "sets": res, "total": tot, "torch": torch.__version__, "onnxruntime": ort.__version__,
           "cmd": "python -I -X utf8 experiments/tile_classifier/role_owner_export.py", "secs": round(time.time() - t0, 1)}
    CHECK.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("→", CHECK, f"{out['secs']}초")


if __name__ == "__main__":
    main()
