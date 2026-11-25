-- mahjong_calc 예시 질문 (load.sql 적재 뒤)

-- 1. 날짜별 측정 표 수(달력처럼: 달 · 날 · 표 수, 제목에 날짜가 있는 표만)
SELECT to_char(measured_on, 'YYYY-MM') AS month,
       to_char(measured_on, 'DD (Dy)') AS day,
       count(*) AS tables,
       count(*) FILTER (WHERE out_of_eval) AS out_of_eval_tables
FROM metrics_table
WHERE measured_on IS NOT NULL
GROUP BY measured_on
ORDER BY measured_on;

-- 2. 평가 밖이 아닌 표에서 정확도 칸이 가장 많은 표 상위 10
SELECT label, left(title, 70) AS title, measured_on, count(*) AS acc_cells,
       round(avg(ratio), 3) AS mean_ratio
FROM v_accuracy
WHERE NOT out_of_eval
GROUP BY table_id, label, title, measured_on
ORDER BY acc_cells DESC, label
LIMIT 10;

-- 3. '채택' 열이 ✗ 인 행이 있는 표 목록(굵게 표기 · 뒤 설명은 무시하고 ✗ 로 시작하는 값)
SELECT t.label, left(t.title, 70) AS title, t.measured_on, t.title_verdict,
       count(*) AS rejected_rows
FROM metrics_row r
JOIN metrics_table t ON t.id = r.table_id
WHERE regexp_replace(r.adopted, '[*\s]', '', 'g') LIKE '✗%'
GROUP BY t.id, t.label, t.title, t.measured_on, t.title_verdict
ORDER BY t.measured_on NULLS LAST, t.line_no;

-- 4. 중앙 시간이 가장 긴 측정 상위 10(표 label, 머리, 값)
SELECT label, left(header, 40) AS header, left(value, 50) AS value,
       t_median, t_p90, t_max, measured_on
FROM v_timing
ORDER BY t_median DESC
LIMIT 10;

-- 5. 판(round)별 버림 수 · 울기 수 · 결과 type
SELECT r.id, r.title, r.source,
       count(*) FILTER (WHERE e.type = 'discard') AS discards,
       count(*) FILTER (WHERE e.type = 'call')    AS calls,
       count(*) FILTER (WHERE e.type = 'draw')    AS draws,
       coalesce(res.type, '(결과 없음)')          AS result_type
FROM round r
LEFT JOIN round_event e ON e.round_id = r.id
LEFT JOIN round_result res ON res.round_id = r.id
GROUP BY r.id, r.title, r.source, res.type
ORDER BY r.hanchan_id, r.id;

-- 6. 자리별 쯔모기리 비율(tsumogiri 가 null 이 아닌 버림만)
SELECT seat,
       count(*) AS known_discards,
       count(*) FILTER (WHERE tsumogiri) AS tsumogiri,
       round(avg(tsumogiri::int), 3) AS tsumogiri_ratio
FROM v_discard
WHERE tsumogiri IS NOT NULL
GROUP BY seat
ORDER BY seat;

-- 7. 반장별 화료 종류 집계(결과 없는 판은 '(결과 없음)')
SELECT h.id AS hanchan, h.played_on,
       coalesce(res.type, '(결과 없음)') AS result_type,
       count(*) AS rounds
FROM hanchan h
JOIN round r ON r.hanchan_id = h.id
LEFT JOIN round_result res ON res.round_id = r.id
GROUP BY h.id, h.played_on, res.type
ORDER BY h.id, rounds DESC;

-- 8. 같은 번호가 두 번 나온 표(번호를 pk 로 쓰면 안 되는 이유)
SELECT label, count(*) AS n, array_agg(line_no ORDER BY line_no) AS lines
FROM metrics_table
WHERE label IS NOT NULL
GROUP BY label
HAVING count(*) > 1;
