"""SAMURAI 방식(칼만 움직임 예측으로 마스크 후보 · 기억 고르기)을 SAM 2 손패 추적에 붙여 보기(2026-11-20).

사용자 지시: 위에서 찍은 손패 줄의 똑같이 생긴 패 13 ~ 14장을 SAM 2 가 번호로 따라가는데, 손이 덮었다 걷히면 번호가 이웃 패로 넘어간다
→ SAMURAI(Apache-2.0, arXiv 2411.11922 — 학습 없는 SAM 2 변형)를 붙여 번호 넘어감이 줄어드는지 본다.
SAMURAI 코드는 내려받지 않고(물체 1개 가정) 규칙을 직접 다시 구현했다 — 칼만 상태 · 기억 목록 모두 물체마다 따로.

설치된 sam2(venvs/sam2_xpu, facebookresearch/sam2 커밋 2b90b9f, 설정 sam2.1 tiny)의 propagate_in_video 는 이미 물체마다
batch 1 로 _run_single_frame_inference 를 부른다(이미지 특징만 프레임마다 한 번 계산해 나눠 씀). 그래서 v1(sam2track.py)이 곧
"물체별 batch 1" 구조이고, 대조판(perobj)은 원숭이 패치 없이 같은 코드로 다시 돈 것 = v1 재현 확인이다.

원숭이 패치(SAMURAI 판만, 설치 파일은 안 고침 — 클래스 속성만 바꿈):
  _run_single_frame_inference : 부르기 전에 "지금 물체" 문맥(output_dict 로 물체를 찾음 → 그 물체의 칼만 상태)을 모델에 걸고,
                                끝나면 그 프레임 출력(compact)에 best_iou_score · kf_score 를 붙임(track_step 대신 여기서 — 압축 출력에 남기려고).
  _forward_sam_heads          : 원래 함수를 옮겨 쓰고 (1) is_obj_appearing 문턱 −1 (2) multimask 일 때 후보 고르기를 SAMURAI 규칙 A/B/C 로.
  _prepare_memory_conditioned_features : 원래 함수를 옮겨 쓰고 추적 프레임의 공간 기억 고르기만 SAMURAI 규칙으로(obj_ptr 은 원래대로).
  _use_multimask              : 바꿀 필요 없음 — tiny 설정이 이미 multimask_output_for_tracking=True · min 0 · max 1(실행 때 assert).
SAMURAI 원본과 다른 점(지킴 하나): 후보 마스크가 비면(화소 0 — 물체 점수가 문턱 밑이라 셋 다 비는 때) 상자 [0,0,0,0] 의 a = w/h 가 0/0 이 되어
  원본이면 칼만이 NaN 이 된다 → A 는 칼만 시작 안 함(stable 0 유지), B · C 는 갱신 대신 stable = 0. 셀 수 있게 로그에 "empty" 로 남김.
  D 추적(뽑은 패 — 중간 프레임에서 시작)은 원본처럼 프레임 2 까지 훑다가 없는 프레임(프롬프트 전)을 건너뜀(원본은 0 프레임 시작 가정이라 KeyError).

  <sam2_xpu>/python -X utf8 sam2samurai.py run --mode samurai --ids r16_d03,r16_d13,r17_d11     # → sam2_1118/<id>_t_xpu_samurai/
  <sam2_xpu>/python -X utf8 sam2samurai.py run --mode perobj  --ids r16_d03                     # → sam2_1118/<id>_t_xpu_perobj/
  <sam2_xpu>/python -X utf8 sam2samurai.py run --mode samurai-mem+obj --ids r17_d11 --d-only   # 떼어 보기(pick · mem · obj 중 켠 것만) — D 만
  python -X utf8 sam2samurai.py score [--ids …] [--modes v1,perobj,samurai]                   # judge · idsolve · 번호 넘어감 지표 → _work/sam2samurai_1120/score.json
  python -X utf8 sam2samurai.py xray r16_d03 --png 68,72 [--mode samurai]                       # sam2xray 영상 · 확인 png → _work/sam2samurai_1120/
출력 꼴은 v1 과 같음(track.json · masks.npz, D 는 dtrack.json · dmasks.npz) + samurai_log.json(프레임 · 물체마다 고른 후보 · 경우 · stable).
frames/ 는 v1 폴더 것을 경로로 읽는다(track.json 의 frames_dir). 같은 프레임 · 같은 첫 프레임 상자(v1 plan.a_boxes) · 같은 D 프롬프트(v1 dtrack.json) · 같은 tiny.

가려진 동안 칼만을 다시 시작하지 않고 예측만 잇기(hold, 같은 날 사용자 — 규칙은 결과 보기 전에 고정):
  <sam2_xpu>/python -X utf8 sam2samurai.py run --mode samurai-hold        --ids r16_d13   # 1a
  <sam2_xpu>/python -X utf8 sam2samurai.py run --mode samurai-hold-refuse --ids r16_d13   # 1b
  13장 줄 패 물체에만(D 는 돌리지 않고 같은 차례 samurai 판의 dtrack.json · dmasks.npz · 로그 D 를 복사). 경우 C(stable ≥ 15)에서만:
  가림 = (i) 칼만 예측 상자 가로의 HOLD_OCC 이상이 det 캐시 가림 열(idsolve.Turn.occ 와 같은 계산)에 덮임 또는 (ii) 고른 후보가 비었거나
  SAM IoU < 0.3, 또는 (iii) 들어가기 직전 막기 — 고른 후보 상자 가운데가 예측 가운데에서 HOLD_JUMP 장폭(첫 프레임 a_box 너비) 넘게 떨어짐.
  hold 동안: stable 그대로(0 으로 안 만듦), 칼만은 속도(vx, vy, va, vh) 0 으로 predict 만, update 안 함, 상한 없음. 고르기는 원래 가중합.
  나옴: (i) 이 풀리고 고른 후보 kf_iou ≥ HOLD_EXIT_KF → update 하고 정상 C. 들어가는 프레임의 predict 는 원래 속도 그대로(들어갈지 정하려고 먼저 함).
  1b(refuse): hold 인 프레임(들어가는 프레임 포함, 나오는 프레임 제외)에서 고른 후보 kf_iou < REFUSE_KF 면 그 프레임 출력 마스크 · 물체 점수를
  NO_OBJ_SCORE 로(물체 포인터도 "물체 없음" 쪽 — 원래 lam 식에 그 점수를 넣은 것) → 기억 고르기(obj > 0)에서 빠짐.
  로그: samurai_log.json 의 pick 마다 "hold"(enter/stay/exit) · "hold_why" · "occ"(가림 몫) · "refuse".
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2track as s1  # noqa: E402

V1 = argparse.Namespace(model="t", device="xpu")
WORK = hc.WORK / "sam2samurai_1120"
IDS = ["r16_d03", "r16_d13", "r17_d11"]

# SAMURAI 수치(원본 설정 그대로 — 결과 보고 바꾸지 않음)
KF_SCORE_WEIGHT = 0.25
STABLE_IOU = 0.3
STABLE_FRAMES = 15
MEM_IOU = 0.5
MEM_OBJ = 0.0
MEM_KF = 0.0
MIN_OBJ_SCORE_LOGITS = -1.0

# hold 수치(사용자 지시대로 결과 보기 전에 고정)
HOLD_OCC = 0.3       # (i) 예측 상자 가로 가림 몫
HOLD_JUMP = 0.5      # 들어가기 직전: 고른 후보 가운데 ↔ 예측 가운데 거리(장폭 배)
HOLD_EXIT_KF = 0.3   # 나옴: 고른 후보 kf_iou
REFUSE_KF = 0.1      # 1b: hold 중 고른 후보 kf_iou 이 미만이면 출력 비움
HOLD_MODES = {"samurai-hold": "hold", "samurai-hold-refuse": "refuse"}
HOLD = None          # None | "hold" | "refuse"
HOLD_GEO: dict = {}  # occ[fi] = 가림 열(영상 x) · objw[oid] = 첫 프레임 상자 너비(영상 px) · sx · sy = 영상 px / SAM 그림 px


def run_dir(tid: str, mode: str) -> Path:
    """v1 = sam2track 결과 폴더 그대로, 나머지는 같은 부모에 <id>_t_xpu_<mode>."""
    d = s1.run_dir(tid, V1)
    return d if mode == "v1" else d.parent / f"{d.name}_{mode}"


# ------------------------------------------------------------------ 칼만 필터(SAMURAI kalman_filter.py 규칙 — numpy 로 다시 씀)
class KF:
    W_POS, W_VEL = 1.0 / 20, 1.0 / 160

    def __init__(self):
        self.F = np.eye(8)
        for i in range(4):
            self.F[i, 4 + i] = 1.0
        self.H = np.eye(4, 8)

    def initiate(self, z):
        h = z[3]
        mean = np.r_[z, np.zeros(4)]
        std = [2 * self.W_POS * h, 2 * self.W_POS * h, 1e-2, 2 * self.W_POS * h,
               10 * self.W_VEL * h, 10 * self.W_VEL * h, 1e-5, 10 * self.W_VEL * h]
        return mean, np.diag(np.square(std))

    def predict(self, mean, cov):
        h = mean[3]
        std = [self.W_POS * h, self.W_POS * h, 1e-2, self.W_POS * h, self.W_VEL * h, self.W_VEL * h, 1e-5, self.W_VEL * h]
        Q = np.diag(np.square(std))
        return self.F @ mean, self.F @ cov @ self.F.T + Q

    def project(self, mean, cov):
        h = mean[3]
        R = np.diag(np.square([self.W_POS * h, self.W_POS * h, 1e-1, self.W_POS * h]))
        return self.H @ mean, self.H @ cov @ self.H.T + R

    def update(self, mean, cov, z):
        pm, pc = self.project(mean, cov)
        K = np.linalg.solve(pc, (cov @ self.H.T).T).T      # = cov Hᵀ S⁻¹ (S 대칭)
        return mean + K @ (np.asarray(z, float) - pm), cov - K @ pc @ K.T

    @staticmethod
    def xyxy_to_xyah(b):
        x1, y1, x2, y2 = (float(v) for v in b)
        w, h = x2 - x1, y2 - y1
        return np.array([x1 + w / 2, y1 + h / 2, w / h, h])

    @staticmethod
    def xyah_to_xyxy(m):
        xc, yc, a, h = (float(v) for v in m[:4])
        w = a * h
        return [xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2]

    def iou(self, xyah, boxes):
        a = self.xyah_to_xyxy(xyah)
        aa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
        out = []
        for b in boxes:
            iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
            ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
            inter = iw * ih
            ba = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
            u = aa + ba - inter
            out.append(inter / u if u > 0 else 0.0)
        return np.array(out)


def empty_box(b) -> bool:
    return b[2] - b[0] <= 0 or b[3] - b[1] <= 0


def pick(ctx: dict, boxes: list, ious: np.ndarray) -> tuple:
    """SAMURAI 후보 고르기(물체 하나의 칼만 상태 ctx) → (고른 후보, SAM IoU, kf_score|None, 로그)."""
    kf = ctx["kf_obj"]
    am = int(np.argmax(ious))
    log = {"fi": ctx["fi"], "ious": [round(float(v), 3) for v in ious], "argmax": am}
    kf_ious = None
    if ctx["mean"] is None or ctx["stable"] == 0:                       # A
        best = am
        log["case"] = "A"
        if empty_box(boxes[best]):
            ctx["mean"], ctx["stable"] = None, 0
            log["empty"] = True
        else:
            ctx["mean"], ctx["cov"] = kf.initiate(kf.xyxy_to_xyah(boxes[best]))
            ctx["stable"] = 1
    elif ctx["stable"] < STABLE_FRAMES:                                 # B
        log["case"] = "B"
        ctx["mean"], ctx["cov"] = kf.predict(ctx["mean"], ctx["cov"])
        best = am
        if ious[best] > STABLE_IOU and not empty_box(boxes[best]):
            ctx["mean"], ctx["cov"] = kf.update(ctx["mean"], ctx["cov"], kf.xyxy_to_xyah(boxes[best]))
            ctx["stable"] += 1
        else:
            log["empty"] = bool(empty_box(boxes[best]))
            ctx["stable"] = 0
    else:                                                               # C
        log["case"] = "C"
        hold_on = HOLD is not None and ctx["obj"] in HOLD_GEO.get("objw", {})
        if hold_on and ctx.get("hold"):                                 # hold: 줄 위 패는 멈춰 있음 → 속도 0 으로 predict
            ctx["mean"] = ctx["mean"].copy()
            ctx["mean"][4:] = 0.0
        ctx["mean"], ctx["cov"] = kf.predict(ctx["mean"], ctx["cov"])
        kf_ious = kf.iou(ctx["mean"][:4], boxes)
        w = KF_SCORE_WEIGHT * kf_ious + (1 - KF_SCORE_WEIGHT) * ious
        best = int(np.argmax(w))
        log["kf_ious"] = [round(float(v), 3) for v in kf_ious]
        bad = bool(ious[best] < STABLE_IOU or empty_box(boxes[best]))
        if not hold_on:
            if bad:
                log["empty"] = bool(empty_box(boxes[best]))
                ctx["stable"] = 0
            else:
                ctx["mean"], ctx["cov"] = kf.update(ctx["mean"], ctx["cov"], kf.xyxy_to_xyah(boxes[best]))
        else:
            hold_step(ctx, kf, boxes, best, kf_ious, bad, log)
    log["best"], log["stable"] = best, ctx["stable"]
    if ctx["mean"] is not None:
        log["pred"] = [round(v, 1) for v in kf.xyah_to_xyxy(ctx["mean"])]
    kfs = None if kf_ious is None else float(kf_ious[best])
    return best, float(ious[best]), kfs, log


def occ_share(fi: int, box_sam) -> float:
    """SAM 그림 좌표 상자의 가로 중 가림 열에 덮인 몫(idsolve.iv_overlap 과 같은 식, 영상 x 로 바꿔서)."""
    occ = HOLD_GEO["occ"][fi] if fi < len(HOLD_GEO["occ"]) else []
    a0, a1 = box_sam[0] * HOLD_GEO["sx"], box_sam[2] * HOLD_GEO["sx"]
    w = max(1e-6, a1 - a0)
    return sum(max(0.0, min(a1, b1) - max(a0, b0)) for b0, b1 in occ) / w


def hold_step(ctx: dict, kf: KF, boxes: list, best: int, kf_ious: np.ndarray, bad: bool, log: dict) -> None:
    """경우 C 에서 hold 규칙(이미 predict 함). 로그에 hold · hold_why · occ · refuse."""
    pb = kf.xyah_to_xyxy(ctx["mean"])
    occ = occ_share(ctx["fi"], pb)
    covered = occ >= HOLD_OCC
    log["occ"] = round(occ, 3)
    if bad:
        log["empty"] = bool(empty_box(boxes[best]))
    if ctx.get("hold"):
        if not covered and kf_ious[best] >= HOLD_EXIT_KF:
            ctx["mean"], ctx["cov"] = kf.update(ctx["mean"], ctx["cov"], kf.xyxy_to_xyah(boxes[best]))
            ctx["hold"] = False
            log["hold"] = "exit"
        else:
            log["hold"] = "stay"
    else:
        why = []
        if covered:
            why.append("occ")
        if bad:
            why.append("empty" if empty_box(boxes[best]) else "sam")
        else:
            b = boxes[best]
            dx = ((b[0] + b[2]) / 2 - (pb[0] + pb[2]) / 2) * HOLD_GEO["sx"]
            dy = ((b[1] + b[3]) / 2 - (pb[1] + pb[3]) / 2) * HOLD_GEO["sy"]
            if (dx * dx + dy * dy) ** 0.5 > HOLD_JUMP * HOLD_GEO["objw"][ctx["obj"]]:
                why.append("jump")
        if why:
            ctx["hold"] = True
            ctx["mean"] = ctx["mean"].copy()
            ctx["mean"][4:] = 0.0
            log["hold"], log["hold_why"] = "enter", why
        else:
            ctx["mean"], ctx["cov"] = kf.update(ctx["mean"], ctx["cov"], kf.xyxy_to_xyah(boxes[best]))
    if ctx.get("hold") and HOLD == "refuse" and kf_ious[best] < REFUSE_KF:
        log["refuse"] = True


# ------------------------------------------------------------------ 원숭이 패치
def install(pred_cls, base_cls):
    """SAMURAI 판 패치를 클래스에 건다(이 프로세스 안에서만)."""
    import torch
    import torch.nn.functional as F
    from sam2.modeling.sam2_base import NO_OBJ_SCORE
    from sam2.modeling.sam2_utils import get_1d_sine_pe, select_closest_cond_frames

    orig_rsfi = pred_cls._run_single_frame_inference
    KFO = KF()

    def rsfi(self, inference_state, output_dict, frame_idx, batch_size, *args, **kw):
        assert batch_size == 1, "SAMURAI 규칙은 물체마다 batch 1 이어야 함"
        key = id(output_dict)
        ctx = CTX.get(key)
        if ctx is None:
            oidx = next((i for i, d in inference_state["output_dict_per_obj"].items() if d is output_dict), None)
            oid = inference_state["obj_idx_to_id"].get(oidx) if oidx is not None else None
            ctx = CTX[key] = {"ref": output_dict, "obj": oid, "mean": None, "cov": None, "stable": 0, "kf_obj": KFO, "log": []}
        ctx["fi"], ctx["last"] = frame_idx, None
        self._sam_ctx = ctx
        try:
            out, pm = orig_rsfi(self, inference_state, output_dict, frame_idx, batch_size, *args, **kw)
        finally:
            self._sam_ctx = None
        if ctx["last"] is not None:
            out["best_iou_score"], out["kf_score"] = ctx["last"]
        return out, pm

    def fsh(self, backbone_features, point_inputs=None, mask_inputs=None, high_res_features=None, multimask_output=False):
        # sam2_base.SAM2Base._forward_sam_heads 를 옮겨 씀 — 바뀐 곳은 "SAMURAI" 표시 두 군데
        B = backbone_features.size(0)
        device = backbone_features.device
        if point_inputs is not None:
            sam_point_coords = point_inputs["point_coords"]
            sam_point_labels = point_inputs["point_labels"]
        else:
            sam_point_coords = torch.zeros(B, 1, 2, device=device)
            sam_point_labels = -torch.ones(B, 1, dtype=torch.int32, device=device)
        if mask_inputs is not None:
            if mask_inputs.shape[-2:] != self.sam_prompt_encoder.mask_input_size:
                sam_mask_prompt = F.interpolate(mask_inputs.float(), size=self.sam_prompt_encoder.mask_input_size,
                                                align_corners=False, mode="bilinear", antialias=True)
            else:
                sam_mask_prompt = mask_inputs
        else:
            sam_mask_prompt = None
        sparse_embeddings, dense_embeddings = self.sam_prompt_encoder(points=(sam_point_coords, sam_point_labels), boxes=None, masks=sam_mask_prompt)
        low_res_multimasks, ious, sam_output_tokens, object_score_logits = self.sam_mask_decoder(
            image_embeddings=backbone_features, image_pe=self.sam_prompt_encoder.get_dense_pe(),
            sparse_prompt_embeddings=sparse_embeddings, dense_prompt_embeddings=dense_embeddings,
            multimask_output=multimask_output, repeat_image=False, high_res_features=high_res_features)
        if self.pred_obj_scores:
            is_obj_appearing = object_score_logits > (MIN_OBJ_SCORE_LOGITS if "obj" in PARTS else 0.0)   # SAMURAI: 문턱 0 → −1
            low_res_multimasks = torch.where(is_obj_appearing[:, None, None], low_res_multimasks, NO_OBJ_SCORE)
        low_res_multimasks = low_res_multimasks.float()
        high_res_multimasks = F.interpolate(low_res_multimasks, size=(self.image_size, self.image_size), mode="bilinear", align_corners=False)
        sam_output_token = sam_output_tokens[:, 0]
        refuse = False
        if multimask_output:
            ctx = getattr(self, "_sam_ctx", None)
            if ctx is not None:                                                   # SAMURAI: 후보 고르기
                assert B == 1
                m = high_res_multimasks[0] > 0                                    # [3, H, W]
                rows = m.any(dim=2).cpu().numpy()
                cols = m.any(dim=1).cpu().numpy()
                boxes = []
                for r, c in zip(rows, cols):
                    ys, xs = np.nonzero(r)[0], np.nonzero(c)[0]
                    boxes.append([0, 0, 0, 0] if len(xs) == 0 else [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())])
                iv = ious[0].float().cpu().numpy()
                if "pick" in PARTS:
                    best, siou, kfs, log = pick(ctx, boxes, iv)
                else:   # 떼어 보기: 원래 SAM 2 고르기(점수만 기억 고르기에 넘김)
                    best = int(np.argmax(iv))
                    siou, kfs = float(iv[best]), None
                    log = {"fi": ctx["fi"], "ious": [round(float(v), 3) for v in iv], "argmax": best, "best": best, "case": "-", "stable": 0}
                log["boxes"] = boxes
                log["obj_logit"] = round(float(object_score_logits[0, 0]), 3)
                ctx["log"].append(log)
                ctx["last"] = (siou, kfs)
                refuse = bool(log.get("refuse"))
                best_iou_inds = torch.tensor([best], device=device)
            else:
                best_iou_inds = torch.argmax(ious, dim=-1)
            batch_inds = torch.arange(B, device=device)
            low_res_masks = low_res_multimasks[batch_inds, best_iou_inds].unsqueeze(1)
            high_res_masks = high_res_multimasks[batch_inds, best_iou_inds].unsqueeze(1)
            if sam_output_tokens.size(1) > 1:
                sam_output_token = sam_output_tokens[batch_inds, best_iou_inds]
        else:
            low_res_masks, high_res_masks = low_res_multimasks, high_res_multimasks
        if refuse:   # hold 1b: 예측 자리에 없으면 잡지 않음 — 출력 마스크 · 물체 점수를 "물체 없음" 으로
            low_res_masks = torch.full_like(low_res_masks, NO_OBJ_SCORE)
            high_res_masks = torch.full_like(high_res_masks, NO_OBJ_SCORE)
            object_score_logits = torch.full_like(object_score_logits, NO_OBJ_SCORE)
            is_obj_appearing = torch.zeros_like(is_obj_appearing)
        obj_ptr = self.obj_ptr_proj(sam_output_token)
        if self.pred_obj_scores:
            lam = object_score_logits.sigmoid() if self.soft_no_obj_ptr else is_obj_appearing.float()
            if self.fixed_no_obj_ptr:
                obj_ptr = lam * obj_ptr
            obj_ptr = obj_ptr + (1 - lam) * self.no_obj_ptr
        return low_res_multimasks, high_res_multimasks, ious, low_res_masks, high_res_masks, obj_ptr, object_score_logits

    def pmcf(self, frame_idx, is_init_cond_frame, current_vision_feats, current_vision_pos_embeds, feat_sizes, output_dict,
             num_frames, track_in_reverse=False):
        # sam2_base.SAM2Base._prepare_memory_conditioned_features 를 옮겨 씀 — 바뀐 곳은 공간 기억 고르기(SAMURAI)뿐
        B = current_vision_feats[-1].size(1)
        C = self.hidden_dim
        H, W = feat_sizes[-1]
        device = current_vision_feats[-1].device
        if self.num_maskmem == 0:
            return current_vision_feats[-1].permute(1, 2, 0).view(B, C, H, W)
        num_obj_ptr_tokens = 0
        tpos_sign_mul = -1 if track_in_reverse else 1
        if not is_init_cond_frame:
            assert not track_in_reverse, "SAMURAI 기억 고르기는 앞으로 추적만"
            to_cat_memory, to_cat_memory_pos_embed = [], []
            cond_outputs = output_dict["cond_frame_outputs"]
            selected_cond_outputs, unselected_cond_outputs = select_closest_cond_frames(frame_idx, cond_outputs, self.max_cond_frames_in_attn)
            t_pos_and_prevs = [(0, out) for out in selected_cond_outputs.values()]
            # SAMURAI: 직전부터 거꾸로 프레임 2 까지, 점수 좋은 프레임(15개까지) + 직전 프레임 → 마지막 6개
            nc = output_dict["non_cond_frame_outputs"]
            valid = []
            if "mem" not in PARTS:   # 떼어 보기: 원래 SAM 2(보폭 1) = 직전 6프레임
                valid = list(range(frame_idx - (self.num_maskmem - 1), frame_idx - 1))
            elif frame_idx > 1:
                for i in range(frame_idx - 1, 1, -1):
                    o = nc.get(i)
                    if o is None or o.get("best_iou_score") is None:
                        continue
                    kfs = o.get("kf_score")
                    if (o["best_iou_score"] > MEM_IOU and float(o["object_score_logits"].reshape(-1)[0]) > MEM_OBJ
                            and (kfs is None or kfs > MEM_KF)):
                        valid.insert(0, i)
                    if len(valid) >= self.max_obj_ptrs_in_encoder - 1:
                        break
            if frame_idx - 1 not in valid:
                valid.append(frame_idx - 1)
            for t_pos in range(1, self.num_maskmem):
                idx = t_pos - self.num_maskmem
                if idx < -len(valid):
                    continue
                out = nc.get(valid[idx], None)
                if out is None:
                    out = unselected_cond_outputs.get(valid[idx], None)
                t_pos_and_prevs.append((t_pos, out))
            ctx = getattr(self, "_sam_ctx", None)
            if ctx is not None:
                ctx.setdefault("mem", []).append((frame_idx, [valid[i] for i in range(-min(6, len(valid)), 0)]))
            for t_pos, prev in t_pos_and_prevs:
                if prev is None:
                    continue
                feats = prev["maskmem_features"].to(device, non_blocking=True)
                to_cat_memory.append(feats.flatten(2).permute(2, 0, 1))
                maskmem_enc = prev["maskmem_pos_enc"][-1].to(device)
                maskmem_enc = maskmem_enc.flatten(2).permute(2, 0, 1)
                maskmem_enc = maskmem_enc + self.maskmem_tpos_enc[self.num_maskmem - t_pos - 1]
                to_cat_memory_pos_embed.append(maskmem_enc)
            if self.use_obj_ptrs_in_encoder:            # 물체 포인터: 원래 그대로
                max_obj_ptrs_in_encoder = min(num_frames, self.max_obj_ptrs_in_encoder)
                if not self.training and self.only_obj_ptrs_in_the_past_for_eval:
                    ptr_cond_outputs = {t: out for t, out in selected_cond_outputs.items() if (t >= frame_idx if track_in_reverse else t <= frame_idx)}
                else:
                    ptr_cond_outputs = selected_cond_outputs
                pos_and_ptrs = [(((frame_idx - t) * tpos_sign_mul if self.use_signed_tpos_enc_to_obj_ptrs else abs(frame_idx - t)), out["obj_ptr"])
                                for t, out in ptr_cond_outputs.items()]
                for t_diff in range(1, max_obj_ptrs_in_encoder):
                    t = frame_idx + t_diff if track_in_reverse else frame_idx - t_diff
                    if t < 0 or (num_frames is not None and t >= num_frames):
                        break
                    out = output_dict["non_cond_frame_outputs"].get(t, unselected_cond_outputs.get(t, None))
                    if out is not None:
                        pos_and_ptrs.append((t_diff, out["obj_ptr"]))
                if len(pos_and_ptrs) > 0:
                    pos_list, ptrs_list = zip(*pos_and_ptrs)
                    obj_ptrs = torch.stack(ptrs_list, dim=0)
                    if self.add_tpos_enc_to_obj_ptrs:
                        t_diff_max = max_obj_ptrs_in_encoder - 1
                        tpos_dim = C if self.proj_tpos_enc_in_obj_ptrs else self.mem_dim
                        obj_pos = torch.tensor(pos_list).to(device=device, non_blocking=True)
                        obj_pos = get_1d_sine_pe(obj_pos / t_diff_max, dim=tpos_dim)
                        obj_pos = self.obj_ptr_tpos_proj(obj_pos)
                        obj_pos = obj_pos.unsqueeze(1).expand(-1, B, self.mem_dim)
                    else:
                        obj_pos = obj_ptrs.new_zeros(len(pos_list), B, self.mem_dim)
                    if self.mem_dim < C:
                        obj_ptrs = obj_ptrs.reshape(-1, B, C // self.mem_dim, self.mem_dim)
                        obj_ptrs = obj_ptrs.permute(0, 2, 1, 3).flatten(0, 1)
                        obj_pos = obj_pos.repeat_interleave(C // self.mem_dim, dim=0)
                    to_cat_memory.append(obj_ptrs)
                    to_cat_memory_pos_embed.append(obj_pos)
                    num_obj_ptr_tokens = obj_ptrs.shape[0]
                else:
                    num_obj_ptr_tokens = 0
        else:
            if self.directly_add_no_mem_embed:
                pix_feat_with_mem = current_vision_feats[-1] + self.no_mem_embed
                return pix_feat_with_mem.permute(1, 2, 0).view(B, C, H, W)
            to_cat_memory = [self.no_mem_embed.expand(1, B, self.mem_dim)]
            to_cat_memory_pos_embed = [self.no_mem_pos_enc.expand(1, B, self.mem_dim)]
        memory = torch.cat(to_cat_memory, dim=0)
        memory_pos_embed = torch.cat(to_cat_memory_pos_embed, dim=0)
        pix_feat_with_mem = self.memory_attention(curr=current_vision_feats, curr_pos=current_vision_pos_embeds, memory=memory,
                                                  memory_pos=memory_pos_embed, num_obj_ptr_tokens=num_obj_ptr_tokens)
        return pix_feat_with_mem.permute(1, 2, 0).view(B, C, H, W)

    pred_cls._run_single_frame_inference = rsfi
    base_cls._forward_sam_heads = fsh
    base_cls._prepare_memory_conditioned_features = pmcf


CTX: dict = {}
PARTS = {"pick", "mem", "obj"}   # 켠 SAMURAI 부분(떼어 보기 때 바뀜)


def ctx_logs() -> dict:
    """물체 번호 → {"pick": [...], "mem": [...]}(지금 CTX 에서)."""
    out = {}
    for c in CTX.values():
        out[str(c["obj"])] = {"pick": c["log"], "mem": c.get("mem", [])}
    return out


def occ_of(tid: str, tr: dict) -> list:
    """프레임마다 가림 열(영상 x) — idsolve.Turn.__init__ 의 self.occ 계산을 그대로 옮김(sam2_xpu 에서 idsolve 를 안 불러오려고).
    det 캐시(slotgrid det_<판>.json)의 "o" = pixtrack.masks 살색 · 소매 열 범위, 넓힌 띠 시점으로 x 만 옮김."""
    import slotgrid as sg
    gid, _ = s1.turn_of(tid)
    p, ms_list = tr["plan"], tr["frames"]
    det = hc.jload(sg.OUT / f"det_{gid}.json")
    b0 = None
    for ms in ms_list:
        e = det.get(str(ms))
        if e and e["b"]:
            b0 = e["b"][0]
            break
    r0 = s1.remap_box(b0, p["band"], p["band2"], p["side"])
    ox = r0[0] - b0[0]
    out = []
    for ms in ms_list:
        e = det.get(str(ms))
        out.append([(o[0] + ox, o[1] + ox) for o in e["o"]] if e else [])
    return out


# ------------------------------------------------------------------ 실행(sam2_xpu)
def cmd_run(a):
    import torch
    from sam2.build_sam import build_sam2_video_predictor
    from sam2.modeling.sam2_base import SAM2Base
    from sam2.sam2_video_predictor import SAM2VideoPredictor
    torch.set_num_threads(16)
    assert torch.xpu.is_available(), "XPU 없음 — venvs/sam2_xpu 의 python 으로 돌릴 것"
    cfg, ck = s1.CFG["t"]
    pred = build_sam2_video_predictor(cfg, str(s1.CKPT / ck), device="xpu")
    assert type(pred) is SAM2VideoPredictor
    assert pred.multimask_output_in_sam and pred.multimask_output_for_tracking and pred.multimask_min_pt_num == 0 and pred.multimask_max_pt_num == 1
    assert pred.iou_prediction_use_sigmoid and pred.pred_obj_scores and pred.num_maskmem == 7 and pred.max_obj_ptrs_in_encoder == 16
    global PARTS, HOLD
    if a.mode in HOLD_MODES:
        PARTS, HOLD = {"pick", "mem", "obj"}, HOLD_MODES[a.mode]
        assert not a.d_only, "hold 판은 13장만(D 는 samurai 판 복사)"
        install(SAM2VideoPredictor, SAM2Base)
    elif a.mode.startswith("samurai"):
        # samurai = 셋 다, samurai-mem / samurai-obj / samurai-pick(+ 로 묶음) = 그 부분만 켠 떼어 보기
        PARTS = {"pick", "mem", "obj"} if a.mode == "samurai" else set(a.mode.split("-", 1)[1].split("+"))
        assert PARTS <= {"pick", "mem", "obj"}, PARTS
        install(SAM2VideoPredictor, SAM2Base)
    elif a.mode != "perobj":
        raise SystemExit("--mode samurai | samurai-<pick|mem|obj>[+…] | perobj")
    for tid in a.ids.split(","):
        v1 = run_dir(tid, "v1")
        od = run_dir(tid, a.mode)
        if (od / ("dtrack.json" if a.d_only else "track.json")).exists() and not a.force:
            print(tid, "있음 — 건너뜀", flush=True)
            continue
        od.mkdir(parents=True, exist_ok=True)
        tr1 = hc.jload(v1 / "track.json")
        p, fl = tr1["plan"], tr1["frames"]
        fd = v1 / "frames"
        q = hc.jload(v1 / "dtrack.json")["prompt"]
        t_all = time.time()
        sec13, log13 = None, None
        with torch.inference_mode():
            st = pred.init_state(video_path=str(fd), offload_video_to_cpu=True, offload_state_to_cpu=True)
            t_load = time.time() - t_all
            if not a.d_only:
                # 13개(첫 프레임 상자 — v1 과 같음)
                CTX.clear()
                HOLD_GEO.clear()
                if HOLD is not None:
                    H, W = tr1["shape"][:2]
                    assert (H, W) == (st["video_height"], st["video_width"]), (H, W)
                    HOLD_GEO.update({"occ": occ_of(tid, tr1), "objw": {oid: float(b[2] - b[0]) for oid, b in enumerate(p["a_boxes"], 1)},
                                     "sx": W / pred.image_size, "sy": H / pred.image_size})
                    assert len(HOLD_GEO["occ"]) == len(fl)
                t0 = time.time()
                for oid, b in enumerate(p["a_boxes"], 1):
                    pred.add_new_points_or_box(st, frame_idx=0, obj_id=oid, box=np.array(b, np.float32))
                rec, keep = {}, {}
                for fi, oids, logits in pred.propagate_in_video(st):
                    row = {}
                    for oid, lg in zip(oids, logits):
                        m = (lg[0] > 0).cpu().numpy()
                        ys, xs = np.nonzero(m)
                        row[int(oid)] = [int(m.sum()), float(xs.mean()) if len(xs) else None, float(ys.mean()) if len(ys) else None]
                        keep.setdefault(fi, {})[int(oid)] = np.packbits(m)
                    rec[int(fi)] = row
                    if fi % 20 == 0:
                        print(f"  {tid} {a.mode} {fi}/{len(fl)} {time.time() - t0:.0f}s", flush=True)
                sec13 = time.time() - t0
                log13 = ctx_logs()
                shape = list(tr1["shape"])
                np.savez_compressed(od / "masks.npz", **{f"{fi}_{oid}": v for fi, r in keep.items() for oid, v in r.items()})
                hc.jsave(od / "track.json", {"plan": p, "frames": fl, "shape": shape, "model": "t", "device": "xpu", "sec": round(sec13, 1),
                                             "rec": rec, "mode": a.mode, "frames_dir": fd.as_posix(), "v1_dir": v1.as_posix()}, indent=None)
                print(f"{tid} {a.mode} 13개 끝 {sec13:.0f}s ({len(fl)}프레임)", flush=True)
            # D(뽑은 패) — v1 dtrack 과 같은 프롬프트, 같은 그림(init_state 다시 안 함)
            pred.reset_state(st)
            CTX.clear()
            HOLD_GEO.clear()
            if HOLD is not None:   # hold 판: D 는 손에 들려 움직이는 게 정상 → 돌리지 않고 같은 차례 samurai 판 D 를 그대로 복사
                import shutil
                sd = run_dir(tid, "samurai")
                shutil.copyfile(sd / "dmasks.npz", od / "dmasks.npz")
                dj = hc.jload(sd / "dtrack.json")
                dj["mode"], dj["copied_from"] = a.mode, sd.as_posix()
                hc.jsave(od / "dtrack.json", dj, indent=None)
                secd = 0.0
                logd = {"1": hc.jload(sd / "samurai_log.json")["D"]}
            else:
                t0 = time.time()
                drec, dkeep = {}, {}
                pred.add_new_points_or_box(st, frame_idx=q["fi"], obj_id=1, box=np.array(q["box"], np.float32))
                for fi, oids, logits in pred.propagate_in_video(st, start_frame_idx=q["fi"]):
                    m = (logits[0][0] > 0).cpu().numpy()
                    ys, xs = np.nonzero(m)
                    drec[int(fi)] = [int(m.sum()), float(xs.mean()) if len(xs) else None, float(ys.mean()) if len(ys) else None]
                    dkeep[int(fi)] = np.packbits(m)
                secd = time.time() - t0
                logd = ctx_logs()
                np.savez_compressed(od / "dmasks.npz", **{str(fi): v for fi, v in dkeep.items()})
                hc.jsave(od / "dtrack.json", {"id": tid, "prompt": q, "frames": len(fl), "device": "xpu", "sec": round(secd, 1), "rec": drec,
                                              "mode": a.mode}, indent=None)
            pred.reset_state(st)
        if a.mode.startswith("samurai"):
            hc.jsave(od / ("samurai_log_d.json" if a.d_only else "samurai_log.json"), {"objs": log13, "D": logd.get("1")}, indent=None)
        hc.jsave(od / ("timing_d.json" if a.d_only else "timing.json"), {"load": round(t_load, 1), "sec13": None if sec13 is None else round(sec13, 1), "secD": round(secd, 1), "total": round(time.time() - t_all, 1)})
        print(f"{tid} {a.mode} D 끝 {secd:.0f}s · 전체 {time.time() - t_all:.0f}s", flush=True)
        del st


# ------------------------------------------------------------------ 채점(pyenv python — torch 없음)
def use_mode(mode: str):
    """relabel.Track · idsolve · sam2xray 가 이 판 폴더를 읽게(그림은 v1 frames/ 에서)."""
    import relabel as rl
    if not hasattr(s1, "_orig_run_dir"):
        s1._orig_run_dir = s1.run_dir
        rl._orig_raw = rl.Track.raw
    if mode == "v1":
        s1.run_dir = s1._orig_run_dir
        rl.Track.raw = rl._orig_raw
        return
    orig = s1._orig_run_dir

    def rd(tid, a):
        d = orig(tid, a)
        return d.parent / f"{d.name}_{mode}"

    def raw(self, fi):
        from PIL import Image
        fd = Path(self.tr.get("frames_dir") or (self.d / "frames"))
        return np.asarray(Image.open(fd / f"{fi:05d}.jpg").convert("RGB")).astype(np.float32)

    s1.run_dir = rd
    rl.Track.raw = raw


JUMP_PITCH = 1.0     # 한 번에 이 × 장 간격 넘게 뛴 번호
HOME_SHARE = 0.4     # 마스크 화소 중 이 몫 이상이 든 줄 상자 = 그 번호의 패
OCC_MAX = 0.3        # 번호 없는 줄 패: 상자 가로 가림 몫이 이 미만(손 밑 상자는 안 셈)
VALID_AREA = 0.5     # 뜀 셈: 첫 프레임(D 는 첫 추적 프레임) 넓이의 이 이상인 마스크만


def slip_metrics(tid: str) -> dict:
    """번호 넘어감 지표(정답 안 읽음): 겹침 프레임 · 번호 없는 줄 패 프레임 · 1칸 넘게 뛴 번호."""
    import idsolve as isv
    import relabel as rl
    U = isv.Turn(tid)
    T = U.T
    band = rl.row_band(T)
    ids = list(range(1, U.n + 1)) + (["D"] if U.DM is not None else [])
    ref = {}
    clash_f, nolab_f, clash_n, nolab_n = [], [], 0, 0
    last = {}
    jumps = {}
    for fi in range(U.F):
        mks = U.masks(fi)
        bs = T.boxes.get(fi)
        row = []
        if bs is not None:
            for b in bs:
                yc = (b[1] + b[3]) / 2
                if band[0] <= yc <= band[1]:
                    row.append([int(max(0, b[0])), int(max(0, b[1])), int(min(U.W, b[2])), int(min(U.H, b[3]))])
        home = {}
        for o, mk in mks.items():
            a = int(mk.sum())
            if o not in ref:
                ref[o] = a
            if row:
                sh = [mk[y0:y1, x0:x1].sum() / max(1, a) for x0, y0, x1, y1 in row]
                k = int(np.argmax(sh))
                if sh[k] >= HOME_SHARE:
                    home.setdefault(k, []).append(o)
            # 뜀
            if a >= VALID_AREA * ref[o]:
                cx = float(np.nonzero(mk)[1].mean())
                if o in last and abs(cx - last[o][1]) > JUMP_PITCH * U.pitch:
                    jumps.setdefault(str(o), []).append([last[o][0], fi, round((cx - last[o][1]) / U.pitch, 1)])
                last[o] = (fi, cx)
        c = [v for v in home.values() if len(v) > 1]
        if c:
            clash_f.append(fi)
            clash_n += len(c)
        if row:
            allm = np.zeros((U.H, U.W), bool)
            for mk in mks.values():
                allm |= mk
            k = 0
            for x0, y0, x1, y1 in row:
                if x1 <= x0 or y1 <= y0:
                    continue
                if allm[y0:y1, x0:x1].mean() < rl.BOX_COVER and isv.iv_overlap(x0, x1, U.occ[fi]) < OCC_MAX:
                    k += 1
            if k:
                nolab_f.append(fi)
                nolab_n += k
    return {"F": U.F, "clash_frames": len(clash_f), "clash_ranges": rl.si_ranges(clash_f), "clash_boxes": clash_n,
            "nolab_frames": len(nolab_f), "nolab_ranges": rl.si_ranges(nolab_f), "nolab_boxes": nolab_n,
            "jump_ids": len(jumps), "jump_events": sum(len(v) for v in jumps.values()), "jumps": jumps, "D_track": U.DM is not None}


def hold_stat(d: Path) -> dict | None:
    """samurai_log.json 의 hold 기록 → 물체별 들어간 횟수 · hold 프레임(들어감 + 머묾) · 나옴 · refuse 프레임 · 들어간 까닭."""
    f = d / "samurai_log.json"
    if not f.exists():
        return None
    L = hc.jload(f)
    objs = {}
    tot = {"enter": 0, "frames": 0, "exit": 0, "refuse": 0, "why": {"occ": 0, "sam": 0, "empty": 0, "jump": 0}, "never_c": 0}
    for o, lg in sorted(L["objs"].items(), key=lambda kv: int(kv[0])):
        s = {"enter": 0, "frames": 0, "exit": 0, "refuse": 0, "enter_fi": [], "refuse_fi": [], "c_frames": 0}
        for x in lg["pick"]:
            h = x.get("hold")
            s["c_frames"] += x["case"] == "C"
            if h == "enter":
                s["enter"] += 1
                s["enter_fi"].append([x["fi"]] + x.get("hold_why", []))
                for w in x.get("hold_why", []):
                    tot["why"][w] += 1
            if h in ("enter", "stay"):
                s["frames"] += 1
            if h == "exit":
                s["exit"] += 1
            if x.get("refuse"):
                s["refuse"] += 1
                s["refuse_fi"].append(x["fi"])
        for k in ("enter", "frames", "exit", "refuse"):
            tot[k] += s[k]
        tot["never_c"] += s["c_frames"] == 0
        objs[o] = s
    return {"total": tot, "objs": objs}


def cmd_score(a):
    import idsolve as isv
    truth = s1.truth_all()
    rows = []
    for mode in a.modes.split(","):
        use_mode(mode)
        for tid in a.ids.split(","):
            d = s1.run_dir(tid, V1)
            if not (d / "track.json").exists():
                print(tid, mode, "없음")
                continue
            tr = hc.jload(d / "track.json")
            u = truth[tid]
            jd = s1.judge(tr)
            b = isv.base_of(tr)
            bk, bj = isv.grade(b, u)
            r = isv.solve(tid)
            ik, ij = isv.grade(r, u)
            sm = slip_metrics(tid)
            tm = hc.jload(d / "timing.json") if (d / "timing.json").exists() else {"sec13": tr["sec"],
                                                                                    "secD": hc.jload(d / "dtrack.json")["sec"] if (d / "dtrack.json").exists() else None}
            row = {"mode": mode, "id": tid, "truth": [u["kind"], u.get("k_id"), u.get("j_closed")],
                   "judge": {k: jd[k] for k in ("k", "j", "gone", "free")} | {"clash": {str(k): v for k, v in jd["clash"].items()}},
                   "judge_ok": bk and bj, "idsolve": [r["kind"], r["k"], r["j"]], "idsolve_ok": ik and ij, "unsure": r["unsure"],
                   "unsure_why": r["unsure_why"], "end_order": r["end_order"], "metrics": sm, "timing": tm}
            hs = hold_stat(d) if mode in HOLD_MODES else None
            if hs is not None:
                row["hold"] = hs
            rows.append(row)
            mk = "✓" if ik and ij else ("?" if r["unsure"] else "✗")
            print(f"{mode:8s} {tid} 정답 {u['kind'][:4]} {u.get('k_id')}·{u.get('j_closed')} | judge k {jd['k']} j {jd['j']} (사라짐 {jd['gone']} 빈 {jd['free']}"
                  f"{' 겹침 ' + str(jd['clash']) if jd['clash'] else ''}) {'✓' if bk and bj else '✗'}"
                  f" | idsolve {r['kind'] and r['kind'][:4]} {r['k']}·{r['j']} {mk}"
                  f" | 겹침 {sm['clash_frames']}f · 번호없음 {sm['nolab_frames']}f · 뜀 {sm['jump_ids']}번호/{sm['jump_events']}번"
                  f" | {tm.get('sec13')}+{tm.get('secD')}s", flush=True)
            if r["unsure"]:
                print("    unsure:", " / ".join(r["unsure_why"])[:300])
            print("    뜀:", {k: v for k, v in sm["jumps"].items()}, "| 겹침", sm["clash_ranges"], "| 번호없음", sm["nolab_ranges"], flush=True)
            if hs is not None:
                t = hs["total"]
                print(f"    hold: 들어감 {t['enter']}번(가림 {t['why']['occ']} · SAM {t['why']['sam']} · 빔 {t['why']['empty']} · 뜀 {t['why']['jump']})"
                      f" · hold 프레임 {t['frames']} · 나옴 {t['exit']} · refuse {t['refuse']} · C 못 감(stable<15 만) {t['never_c']}", flush=True)
                print("    물체별(들어감/프레임/refuse):", {o: f"{v['enter']}/{v['frames']}/{v['refuse']}" for o, v in hs["objs"].items()}, flush=True)
    use_mode("v1")
    WORK.mkdir(parents=True, exist_ok=True)
    hc.jsave(WORK / "score.json", rows, indent=1)
    print(WORK / "score.json")


def cmd_pickstat(a):
    """SAMURAI 로그 요약: 경우 A/B/C 프레임 수 · 원래(argmax)와 다른 후보를 고른 프레임 · 빈 후보 · 기억이 '직전 6프레임' 과 달랐던 프레임."""
    for tid in a.ids.split(","):
        L = hc.jload(run_dir(tid, "samurai") / "samurai_log.json")
        tot = {"A": 0, "B": 0, "C": 0, "diff": 0, "empty": 0, "memskip": 0, "n": 0}
        diffs = []
        for name, lg in list(L["objs"].items()) + [("D", L["D"] or {"pick": [], "mem": []})]:
            for x in lg["pick"]:
                tot[x["case"]] += 1
                tot["n"] += 1
                tot["empty"] += bool(x.get("empty"))
                if x["best"] != x["argmax"]:
                    tot["diff"] += 1
                    diffs.append(f"{name}@{x['fi']}")
            nonc = {x["fi"] for x in lg["pick"]}
            for fi, mem in lg["mem"]:   # 원래 SAM 2 = 직전 6프레임(있는 것만)
                if [f for f in mem if f in nonc] != [f for f in range(fi - 6, fi) if f in nonc]:
                    tot["memskip"] += 1
        print(tid, tot, "다른 후보:", " ".join(diffs[:40]))


def cmd_xray(a):
    import imageio_ffmpeg
    import sam2xray as sx
    use_mode(a.mode)
    od = WORK if a.mode == "samurai" else (WORK / "hold" / a.mode if a.mode in HOLD_MODES else WORK / a.mode)
    sx.OUT = od
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    png = [int(x) for x in a.png.split(",")] if a.png else None
    r = sx.make(a.id, a.fps, a.width, png, ff)
    print({k: v for k, v in r.items() if k not in ("color", "events")}, flush=True)
    use_mode("v1")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("run")
    q.add_argument("--ids", default=",".join(IDS))
    q.add_argument("--mode", default="samurai")
    q.add_argument("--force", action="store_true")
    q.add_argument("--d-only", action="store_true", help="D(뽑은 패)만 — 떼어 보기용")
    q = sp.add_parser("score")
    q.add_argument("--ids", default=",".join(IDS))
    q.add_argument("--modes", default="v1,perobj,samurai,samurai-hold,samurai-hold-refuse")
    q = sp.add_parser("pickstat")
    q.add_argument("--ids", default=",".join(IDS))
    q = sp.add_parser("xray")
    q.add_argument("id")
    q.add_argument("--mode", default="samurai")
    q.add_argument("--png", default=None)
    q.add_argument("--fps", type=float, default=2.5)
    q.add_argument("--width", type=int, default=1280)
    a = ap.parse_args()
    {"run": cmd_run, "score": cmd_score, "pickstat": cmd_pickstat, "xray": cmd_xray}[a.cmd](a)


if __name__ == "__main__":
    main()
