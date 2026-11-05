"""역할 모델을 서버용 ONNX 로(2026-11-04). 입력 x[1, N, 9](role_set.scene_tokens 벡터), 출력 logits[1, N, 6]. 패딩 없음(한 장면씩).
3씨드 가중치를 하나의 그래프로 합친다(세 인코더의 softmax 평균 → 투표 대신 평균, 결과는 거의 같다).
  python -I -X utf8 experiments/tile_classifier/role_export.py data/role/role_nb_all.pt <출력.onnx>
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
    for layer in net.enc.layers:
        a = layer.self_attn
        B, N, D = h.shape
        H = a.num_heads
        y = layer.norm1(h)
        qkv = torch.nn.functional.linear(y, a.in_proj_weight, a.in_proj_bias)
        q, k, v = qkv.split(D, dim=-1)
        q = q.reshape(B, -1, H, D // H).transpose(1, 2)
        k = k.reshape(B, -1, H, D // H).transpose(1, 2)
        v = v.reshape(B, -1, H, D // H).transpose(1, 2)
        att = torch.softmax(q @ k.transpose(-1, -2) / (D // H) ** 0.5, -1)
        o = (att @ v).transpose(1, 2).reshape(B, -1, D)
        h = h + a.out_proj(o)
        y = layer.norm2(h)
        h = h + layer.linear2(torch.relu(layer.linear1(y)))
    return net.head(h)


class Ensemble(nn.Module):
    def __init__(self, nets: list[nn.Module]):
        super().__init__()
        self.nets = nn.ModuleList(nets)

    def forward(self, x):
        return torch.stack([torch.softmax(manual_forward(n, x), -1) for n in self.nets]).mean(0)


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.is_absolute():
        src = HERE / src
    nets = []
    for sd in torch.load(src):
        n = rs.SetNet()
        n.load_state_dict(sd)
        nets.append(n.eval())
    ens = Ensemble(nets).eval()
    x = torch.randn(1, 37, rs.FEAT)
    with torch.no_grad():  # 수동 계산이 원래 모듈과 같은지
        pad = torch.zeros(1, 37, dtype=torch.bool)
        ref = torch.stack([torch.softmax(n(x, pad), -1) for n in nets]).mean(0)
        print("수동 계산 대 원래", float((ens(x) - ref).abs().max()))
    torch.onnx.export(ens, (x,), str(dst), input_names=["x"], output_names=["probs"], dynamic_axes={"x": {1: "n"}, "probs": {1: "n"}}, opset_version=17, dynamo=False)
    import onnxruntime as ort

    sess = ort.InferenceSession(str(dst), providers=["CPUExecutionProvider"])
    for n in (5, 37, 120):
        x = torch.randn(1, n, rs.FEAT)
        a = ens(x).detach().numpy()
        b = sess.run(None, {"x": x.numpy()})[0]
        print(n, "최대 차", float(np.abs(a - b).max()))
    print("저장", dst, dst.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
