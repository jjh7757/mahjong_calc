"""리치 화료 짝 합성 2차(2026-11-09 사용자): 125839 를 '패산 옆 뒷도라 뒤집기' 에서 '화료자 쪽 짝' 으로 다시,
165614·181209(리치 + 깡 1개 → 보이는 표시패 4장인데 패산에 2장뿐)는 뒷도라 2장을 더해 표시패 2 + 뒷도라 2 = 4장을 화료자 쪽 짝 둘로.
방식은 role_v2_pair_synth.py 와 같다: 패산 표시패 자리는 바로 옆 뒷면 패 윗면으로 덮고, 표시패 조각 + 뒷도라(같은 사진 강의 패) 조각을
화료자 손패 안쪽 펠트(화료자 오른손 쪽 끝 가까이, 124654 짝 위치를 본뜸)에 [표시패, 뒷도라] 짝으로 나란히 놓는다.
  python -X utf8 experiments/tile_classifier/role_v2_pair_synth2.py → data/role/v2/images/<시각>_after.jpg
"""
from pathlib import Path
import cv2, numpy as np
HERE = Path(__file__).resolve().parent
CAP = HERE.parent / "visit_20261031" / "captures"
OUT = HERE / "data" / "role" / "v2" / "images"
# 이름: 표시패 [(상자, 덮을 뒷면 좌상단)], 뒷도라 출처 강 상자 [..], 표시패 회전, 뒷도라 회전, 짝 상자 [표시1, 뒷1, 표시2, 뒷2]
JOBS = {
    "20261031_125839": dict(ind=[([1091, 1016, 122, 89], (1091, 927))], ura=["river:25"], rot_ind="ccw", rot_ura=None,
                            pairs=[[1480, 560, 88, 116], [1570, 560, 88, 116]]),
    "20261031_165614": dict(ind=[([2728, 1312, 131, 104], (2728, 1208)), ([2748, 1400, 124, 97], (2748, 1497))], inset=(8, 6, 6, 6), ura=["river:45", "river:34"],
                            rot_ind="cw", rot_ura=None, pairs=[[1450, 610, 88, 116], [1540, 610, 88, 116], [1675, 610, 88, 116], [1765, 610, 88, 116]]),
    "20261031_181209": dict(ind=[([1266, 1735, 125, 95], (1266, 1640)), ([1272, 1822, 124, 96], (1272, 1918))], inset=(4, 12, 4, 4), ura=["river:11", "river:32"],
                            rot_ind=None, rot_ura=None, pairs=[[1545, 1900, 116, 88], [1545, 1990, 116, 88], [1545, 2115, 116, 88], [1545, 2205, 116, 88]]),
}
ROTF = {None: lambda c: c, "ccw": lambda c: cv2.rotate(c, cv2.ROTATE_90_COUNTERCLOCKWISE), "cw": lambda c: cv2.rotate(c, cv2.ROTATE_90_CLOCKWISE),
        "180": lambda c: cv2.rotate(c, cv2.ROTATE_180)}


def paste(dst, src, x, y, feather=1.2):
    h, w = src.shape[:2]
    m = np.zeros((h, w), np.float32); m[2:-2, 2:-2] = 1; m = cv2.GaussianBlur(m, (0, 0), feather)[..., None]
    reg = dst[y:y + h, x:x + w].astype(np.float32)
    dst[y:y + h, x:x + w] = (src.astype(np.float32) * m + reg * (1 - m)).astype(np.uint8)


def main(labels):
    for name, j in JOBS.items():
        im = cv2.imread(str(CAP / name / "original.jpg")); o = im.copy()
        crops = []
        for (x, y, w, h), (bx, by) in j["ind"]:
            l, t, r, b = j.get("inset", (0, 0, 0, 0))  # 표시패 상자에 옆 뒷면 테두리가 묻은 만큼 안쪽으로
            crops.append(ROTF[j["rot_ind"]](im[y + t:y + h - b, x + l:x + w - r].copy()))
            paste(o, im[by:by + h, bx:bx + w].copy(), x, y)  # 표시패 자리 → 옆 뒷면 패 윗면
        uras = []
        for ref in j["ura"]:
            x, y, w, h = labels[name]["items"][int(ref.split(":")[1])]["box"]
            uras.append(ROTF[j["rot_ura"]](im[y:y + h, x:x + w].copy()))
        seq = [c for pair in zip(crops, uras) for c in pair]
        for c, (px, py, pw, ph) in zip(seq, j["pairs"]):
            c = cv2.resize(c, (pw, ph), interpolation=cv2.INTER_AREA)
            sh = o[py + 4:py + ph + 6, px + 3:px + pw + 5].astype(np.float32) * 0.75  # 펠트 위 낱장 그림자
            o[py + 4:py + ph + 6, px + 3:px + pw + 5] = sh.astype(np.uint8)
            paste(o, c, px, py)
        cv2.imwrite(str(OUT / f"{name[-6:]}_after.jpg"), o, [cv2.IMWRITE_JPEG_QUALITY, 95])
        print(name, "표시패", len(crops), "뒷도라", len(uras), "→ 짝", j["pairs"])


if __name__ == "__main__":
    import json
    main(json.loads((HERE / "data/role/v2/labels_v2.json").read_text(encoding="utf-8")))
