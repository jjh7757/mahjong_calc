"""gemini-3.8-flash 가 response_logprobs 를 주는지, 패 토큰 확률이 쓸 만한지 한 번 본다 (B k28_1, v3a_now 입력 그대로)."""
import sys, time, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import bench as b
from google.genai import types

c = {**b.BASE, **b.CONDS["v3a_now"]}
s, p = sys.argv[1], sys.argv[2]
path = b.G / s / p / b.TRUTH[s][0]
data = b.load(path, c["max_side"], c["crop"])
prompt, schema = b.SEAT_PROMPT_V3A, b.SEAT_SCHEMA_V3A
extra = [b.image_part(z, c.get("zoom_res")) for z in b.zoom_strips(path, c["zoom"], c.get("width", 0.4))]
prompt += b.ZOOM_NOTE.format(n=c["zoom"])
extra.append(b.image_part(b.ref_sheet_set2(), c.get("ref_res")))
prompt += b.REF_NOTE
part = b.image_part(data, c["res"])
cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema,
                                  thinking_config=b.thinking_config(c["thinking"]),
                                  response_logprobs=True, logprobs=5)
t0 = time.perf_counter()
try:
    r = b.client().models.generate_content(model=c["model"], contents=[part, *extra, prompt], config=cfg)
except Exception as e:
    print("ERROR", type(e).__name__, str(e)[:500]); sys.exit(1)
print("secs", round(time.perf_counter() - t0, 1), "think", r.usage_metadata.thoughts_token_count)
print(r.text)
cand = r.candidates[0]
print("avg_logprobs", cand.avg_logprobs)
lp = cand.logprobs_result
if not lp:
    print("NO logprobs_result"); sys.exit(0)
for ch, top in zip(lp.chosen_candidates, lp.top_candidates):
    alts = " | ".join(f"{t.token!r}:{t.log_probability:.2f}" for t in top.candidates[1:4])
    print(f"{ch.token!r:12} {ch.log_probability:7.3f}   {alts}")
