"""역할 모델을 서버용 ONNX 로(2026-11-04). 입력 x[1, N, 9](role_set.scene_tokens 벡터), 출력 logits[1, N, 6]. 패딩 없음(한 장면씩).
3씨드 가중치를 하나의 그래프로 합친다(세 인코더의 softmax 평균 → 투표 대신 평균, 결과는 거의 같다).
  python -I -X utf8 experiments/tile_classifier/role_export.py data/role/role_nb_all.pt <출력.onnx> [--seeds-out]
--seeds-out(개선 계획 5단계 S4, 2026-11-05): 출력을 둘로 — probs(평균, 예전과 같음) + seeds[S, 1, N, 6](씨드별 softmax). 서버는 첫 출력으로
답을 내고 둘째 출력으로 씨드 투표 불일치를 센다. 같은 가중치면 probs 가 예전 ONNX 와 같다(--check <예전.onnx> 로 확인).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_set as rs  # noqa: E402


def manual_forward(net: rs.SetNet, x: torch.Tensor) -> torch.Tensor:
    """nn.TransformerEncoder 와 같은 계산을 평범한 행렬곱으로(ONNX 가 길이 N 을 고정해 버리는 빠른 경로를 피한다). norm_first·relu·패딩 없음."""
    h = net.inp(x)
    bias = net.rel(rs.rel_feats(x)).permute(0, 3, 1, 2) if getattr(net, "relbias", False) else None  # [B, 층×머리, N, N] (2026-11-08 --relbias)
    for li, layer in enumerate(net.enc.layers):
        a = layer.self_attn
        B, N, D = h.shape
        H = a.num_heads
        y = layer.norm1(h)
        qkv = torch.nn.functional.linear(y, a.in_proj_weight, a.in_proj_bias)
        q, k, v = qkv.split(D, dim=-1)
        q = q.reshape(B, -1, H, D // H).transpose(1, 2)
        k = k.reshape(B, -1, H, D // H).transpose(1, 2)
        v = v.reshape(B, -1, H, D // H).transpose(1, 2)
        logit = q @ k.transpose(-1, -2) / (D // H) ** 0.5
        if bias is not None:
            logit = logit + bias[:, li * H:(li + 1) * H]
        att = torch.softmax(logit, -1)
        o = (att @ v).transpose(1, 2).reshape(B, -1, D)
        h = h + a.out_proj(o)
        y = layer.norm2(h)
        h = h + layer.linear2(torch.relu(layer.linear1(y)))
    return net.head(h)


class Ensemble(nn.Module):
    def __init__(self, nets: list[nn.Module], seeds_out: bool = False):
        super().__init__()
        self.nets = nn.ModuleList(nets)
        self.seeds_out = seeds_out

    def forward(self, x):
        each = torch.stack([torch.softmax(manual_forward(n, x), -1) for n in self.nets])
        return (each.mean(0), each) if self.seeds_out else each.mean(0)


def main() -> None:
    args = [v for v in sys.argv[1:] if not v.startswith("--")]
    seeds_out = "--seeds-out" in sys.argv
    check = sys.argv[sys.argv.index("--check") + 1] if "--check" in sys.argv else None
    src, dst = Path(args[0]), Path(args[1])
    if not src.is_absolute():
        src = HERE / src
    nets = rs.load_nets(src)
    feat = nets[0].feat
    print("특징", feat, "칸(9 = 예전 축 상자, 11 = 회전 상자 특징 — 서버 roles.py 가 ONNX 입력 모양에서 읽는다)")
    ens = Ensemble(nets, seeds_out).eval()
    mean = lambda x: ens(x)[0] if seeds_out else ens(x)
    x = torch.randn(1, 37, feat)
    with torch.no_grad():  # 수동 계산이 원래 모듈과 같은지
        pad = torch.zeros(1, 37, dtype=torch.bool)
        ref = torch.stack([torch.softmax(n(x, pad), -1) for n in nets]).mean(0)
        print("수동 계산 대 원래", float((mean(x) - ref).abs().max()))
    names = ["probs", "seeds"] if seeds_out else ["probs"]
    axes = {"x": {1: "n"}, "probs": {1: "n"}, **({"seeds": {2: "n"}} if seeds_out else {})}
    torch.onnx.export(ens, (x,), str(dst), input_names=["x"], output_names=names, dynamic_axes=axes, opset_version=17, dynamo=False)
    import onnxruntime as ort

    sess = ort.InferenceSession(str(dst), providers=["CPUExecutionProvider"])
    old = ort.InferenceSession(str(check), providers=["CPUExecutionProvider"]) if check else None
    for n in (5, 37, 120):
        x = torch.randn(1, n, feat)
        a = mean(x).detach().numpy()
        out = sess.run(None, {"x": x.numpy()})
        print(n, "최대 차", float(np.abs(a - out[0]).max()), *(["씨드 출력", out[1].shape, "평균 대 probs", float(np.abs(out[1].mean(0) - out[0]).max())] if seeds_out else []))
        if old is not None:
            o = old.run(None, {"x": x.numpy()})[0]
            print("   예전 ONNX 대 probs 최대 차", float(np.abs(o - out[0]).max()), "argmax 다름", int((o.argmax(-1) != out[0].argmax(-1)).sum()))
    print("저장", dst, dst.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
