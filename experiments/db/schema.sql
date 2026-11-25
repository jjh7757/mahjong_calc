-- mahjong_calc 자료 적재용 스키마 (PostgreSQL 16)
-- 전체 재적재 방식: 매번 지우고 처음부터 다시 만든다. build_sql.py 가 이 파일을 load.sql 앞에 붙인다.

DROP VIEW IF EXISTS v_discard CASCADE;
DROP VIEW IF EXISTS v_accuracy CASCADE;
DROP VIEW IF EXISTS v_timing CASCADE;
DROP TABLE IF EXISTS round_result CASCADE;
DROP TABLE IF EXISTS round_event CASCADE;
DROP TABLE IF EXISTS round CASCADE;
DROP TABLE IF EXISTS hanchan CASCADE;
DROP TABLE IF EXISTS metrics_cell CASCADE;
DROP TABLE IF EXISTS metrics_row CASCADE;
DROP TABLE IF EXISTS metrics_part CASCADE;
DROP TABLE IF EXISTS metrics_table CASCADE;
DROP TABLE IF EXISTS metrics_section CASCADE;

-- ===================== 자료 1: 패보 =====================

-- 반장(제목의 날짜 + "N반장")
CREATE TABLE hanchan (
    id          text PRIMARY KEY,          -- 예 '2026-11-14_h3'
    played_on   date NOT NULL,
    hanchan_no  int  NOT NULL
);

-- 판(패보 JSON 파일 하나)
CREATE TABLE round (
    id              text PRIMARY KEY,      -- JSON 의 id (예 'h3_143158')
    hanchan_id      text NOT NULL REFERENCES hanchan(id),
    title           text NOT NULL,
    round_name      text NOT NULL,         -- '동1국'
    wind            text NOT NULL,         -- '동' / '남' ...
    kyoku_no        int,                   -- 1 ~ 4
    honba           int NOT NULL,
    dealer          int NOT NULL,          -- 자리 번호 0 ~ 3
    hero            int NOT NULL,          -- 손패를 아는 자리
    names           text[] NOT NULL,
    kyotaku         int,                   -- 없는 파일은 null
    start_scores    int[],                 -- 없는 파일은 null
    dora_indicators text[] NOT NULL,
    ura_indicators  text[] NOT NULL,
    source          text,                  -- 없는 파일은 null
    note            text NOT NULL,
    version         int,
    event_count     int NOT NULL,
    file_path       text NOT NULL          -- 저장소 기준 경로
);
CREATE INDEX round_hanchan_idx ON round(hanchan_id);

-- 판 안 사건(뽑기 · 버림 · 울기), events 배열 순서 그대로
CREATE TABLE round_event (
    round_id    text NOT NULL REFERENCES round(id) ON DELETE CASCADE,
    seq         int  NOT NULL,             -- events 안 순서(0부터)
    type        text NOT NULL,             -- draw / discard / call
    seat        int,
    tile        text,                      -- draw · discard 의 패
    tsumogiri   boolean,                   -- discard 만, 모르면 null
    riichi      boolean,                   -- discard 만
    at_ms       bigint,                    -- discard 의 at(ms epoch), 없으면 null
    call_kind   text,                      -- call 만: pon / chi / kan ...
    call_from   int,                       -- call 만: 울어 온 자리
    call_tiles  text[],                    -- call 만
    hand        text[],                    -- 사건 뒤 손패(아는 자리만), 없으면 null
    guess       boolean,                   -- 손패를 추정으로 채웠으면 true, 키 없으면 null
    raw         jsonb NOT NULL,            -- 원본 사건 그대로
    PRIMARY KEY (round_id, seq)
);
CREATE INDEX round_event_type_idx ON round_event(type, seat);

-- 판 결과(result 키가 없는 판은 행 없음)
CREATE TABLE round_result (
    round_id    text PRIMARY KEY REFERENCES round(id) ON DELETE CASCADE,
    type        text NOT NULL,             -- ron / tsumo / draw
    winner      int,
    loser       int,
    win_tile    text,
    hand        text[],
    melds       jsonb,
    flags       jsonb
);

-- 버림만, 자리별 몇 번째 버림인지 붙임
CREATE VIEW v_discard AS
SELECT e.round_id,
       r.hanchan_id,
       r.round_name,
       e.seq,
       e.seat,
       e.tile,
       e.tsumogiri,
       e.riichi,
       e.at_ms,
       row_number() OVER (PARTITION BY e.round_id, e.seat ORDER BY e.seq) AS seat_discard_no,
       row_number() OVER (PARTITION BY e.round_id ORDER BY e.seq)         AS round_discard_no
FROM round_event e
JOIN round r ON r.id = e.round_id
WHERE e.type = 'discard';

-- ===================== 자료 2: docs/metrics.md =====================

-- '## ' 절
CREATE TABLE metrics_section (
    id       serial PRIMARY KEY,
    label    text,                         -- '## 표 1.' 이면 '1', 번호 없는 절은 null
    title    text NOT NULL,                -- 머리줄 원문('## ' 뺀 것)
    line_no  int  NOT NULL                 -- metrics.md 줄 번호(1부터)
);

-- '### ' 측정 표(절 머리 바로 아래, '### ' 전에 나온 마크다운 표는 절 자신을 표 하나로 넣음)
CREATE TABLE metrics_table (
    id             serial PRIMARY KEY,
    section_id     int  NOT NULL REFERENCES metrics_section(id),
    label          text,                   -- '1-3', '12-3a'. 같은 번호가 두 번 나올 수 있어 pk 아님
    title          text NOT NULL,          -- 머리줄 원문
    line_no        int  NOT NULL,
    is_section_own boolean NOT NULL,       -- '##' 절 자체(### 아님)면 true
    measured_on    date,                   -- 제목에서 처음 나온 YYYY-MM-DD
    out_of_eval    boolean NOT NULL,       -- 제목에 '평가 밖'
    eval_mixed     boolean NOT NULL,       -- 제목에 '평가 밖 포함'(평가 세트와 평가 밖이 섞임)
    title_verdict  text                    -- 제목에 나온 ❌ / 미채택 / 🗑 를 공백으로 이어 그대로
);
CREATE INDEX metrics_table_label_idx ON metrics_table(label);

-- 한 측정 표 안의 마크다운 표 하나(part)
CREATE TABLE metrics_part (
    table_id   int NOT NULL REFERENCES metrics_table(id) ON DELETE CASCADE,
    part       int NOT NULL,               -- 1부터
    line_no    int NOT NULL,               -- 머리줄 줄 번호
    headers    text[] NOT NULL,            -- 머리 원문
    row_count  int NOT NULL,
    PRIMARY KEY (table_id, part)
);

-- 데이터 줄
CREATE TABLE metrics_row (
    table_id  int NOT NULL,
    part      int NOT NULL,
    row_no    int NOT NULL,                -- 1부터
    line_no   int NOT NULL,
    cells     jsonb NOT NULL,              -- {머리: 값} 원문. 머리가 겹치면 '머리 (2)', 머리 없는 칸은 '_col<N>'
    adopted   text,                        -- '채택' 열 값(원문), 없으면 null
    raw_line  text NOT NULL,
    PRIMARY KEY (table_id, part, row_no),
    FOREIGN KEY (table_id, part) REFERENCES metrics_part(table_id, part) ON DELETE CASCADE
);

-- 칸 하나
CREATE TABLE metrics_cell (
    table_id  int NOT NULL,
    part      int NOT NULL,
    row_no    int NOT NULL,
    col_no    int NOT NULL,                -- 1부터
    header    text,                        -- 머리 원문(머리 수보다 칸이 많으면 null)
    value     text NOT NULL,               -- 원문(굵게 표기 그대로)
    frac_num  int,                         -- 'a/b' 정확도 꼴이면
    frac_den  int,
    t_median  numeric,                     -- '중앙 / p90 / 최대' 초 꼴이면
    t_p90     numeric,
    t_max     numeric,
    PRIMARY KEY (table_id, part, row_no, col_no),
    FOREIGN KEY (table_id, part, row_no) REFERENCES metrics_row(table_id, part, row_no) ON DELETE CASCADE
);
CREATE INDEX metrics_cell_frac_idx ON metrics_cell(table_id) WHERE frac_den IS NOT NULL;
CREATE INDEX metrics_cell_time_idx ON metrics_cell(table_id) WHERE t_median IS NOT NULL;

-- 정확도 칸 + 표 정보
CREATE VIEW v_accuracy AS
SELECT t.id AS table_id, t.label, t.title, t.measured_on, t.out_of_eval, t.eval_mixed,
       c.part, c.row_no, c.col_no, c.header, c.value,
       c.frac_num, c.frac_den,
       round(c.frac_num::numeric / c.frac_den, 4) AS ratio,
       r.adopted
FROM metrics_cell c
JOIN metrics_table t ON t.id = c.table_id
JOIN metrics_row r ON r.table_id = c.table_id AND r.part = c.part AND r.row_no = c.row_no
WHERE c.frac_den IS NOT NULL;

-- 시간 칸 + 표 정보
CREATE VIEW v_timing AS
SELECT t.id AS table_id, t.label, t.title, t.measured_on, t.out_of_eval, t.eval_mixed,
       c.part, c.row_no, c.col_no, c.header, c.value,
       c.t_median, c.t_p90, c.t_max,
       r.adopted
FROM metrics_cell c
JOIN metrics_table t ON t.id = c.table_id
JOIN metrics_row r ON r.table_id = c.table_id AND r.part = c.part AND r.row_no = c.row_no
WHERE c.t_median IS NOT NULL;
