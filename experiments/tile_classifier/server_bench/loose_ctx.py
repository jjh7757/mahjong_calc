"""자리 크롭 밖의 떼어 둔 화료패를 역할 모델 판단으로 쓰기(2026-11-05, 사용자 "우리 모델로 전체 사진에서 역할 나누지 않았나"·"재봐", 노트북, API 없음).

app.roles.read_roles 는 사진 전체 상자로 역할을 나누지만 손패·화료패는 자리 크롭 안 상자로만 고른다. 143104 는 화료패 7삭을
손패 줄 위로 떼어 놓아 크롭 밖이었고(역할 모델은 loose 0.85 로 맞게 짚음) 13장 텐파이로 틀린 채 자동 반영됐다.
고친 것: 크롭 안에서 떼어 둔 패를 못 찾았고 손패 + 울기 × 3 = 13 이면, 크롭 밖 상자 중 역할이 loose 이고 화료자 손패에서
(가장 가까운 손패 중심까지) 패 높이 3배 안에 있는 것이 **딱 하나**면 그것을 떼어 둔 화료패로 원본 사진에서 읽는다.
  install(roles)  — app.roles.read_roles 를 감싼다
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

REACH = 3.0  # 손패 패 높이의 몇 배 안


def install(roles) -> None:
    old = roles.read_roles
    lr = roles.lr

    def read_roles(reader, jpeg, side, grid, mode="hybrid", net=None):
        out = old(reader, jpeg, side, grid, mode, net)
        if not out.get("framed") or out.get("separate_tile") or len(out["tiles"]) + 3 * len(out["melds"]) != 13:
            return out
        hand = [x["box"] for x in out["roles"] if x["in_seat"] and x["role"] == "hand"]
        if not hand:
            return out
        th = float(np.median([max(b[2], b[3]) for b in hand]))
        cen = lambda b: np.array([b[0] + b[2] / 2, b[1] + b[3] / 2], float)
        near = [x for x in out["roles"] if not x["in_seat"] and x["role"] == "loose"
                and min(np.linalg.norm(cen(x["box"]) - cen(h)) for h in hand) <= REACH * th]
        if len(near) != 1:
            return out
        full = np.asarray(Image.open(io.BytesIO(jpeg)).convert("RGB"))
        tile, conf = reader.read_any(full, tuple(near[0]["box"]))
        out["separate_tile"] = {"tile": tile, "conf": conf, "box": near[0]["box"], "from": "loose_ctx"}
        return out

    roles.read_roles = read_roles
