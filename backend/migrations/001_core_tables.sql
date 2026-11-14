-- 核心表结构参考（PostgreSQL，运行时不执行；建表由 SQLAlchemy create_all 完成）

CREATE TABLE skus (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(20)  NOT NULL UNIQUE,     -- A2 / B1 …
    name        VARCHAR(120) NOT NULL,
    category    VARCHAR(40)  NOT NULL,
    spec        VARCHAR(40),
    channel     VARCHAR(24)  NOT NULL,            -- 共享枚举 Channel
    cost        DOUBLE PRECISION NOT NULL,        -- 成本，ROI 的分子
    list_price  DOUBLE PRECISION NOT NULL,        -- 牌价，让利的分母
    enabled     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP    NOT NULL,
    updated_at  TIMESTAMP    NOT NULL
);

CREATE TABLE price_events (
    id           SERIAL PRIMARY KEY,
    event_no     VARCHAR(24)  NOT NULL UNIQUE,
    sku_id       INTEGER      NOT NULL REFERENCES skus(id) ON DELETE CASCADE,
    channel      VARCHAR(24)  NOT NULL,
    base_price   DOUBLE PRECISION NOT NULL,
    promo_price  DOUBLE PRECISION NOT NULL,
    discount     DOUBLE PRECISION NOT NULL,
    start_on     DATE         NOT NULL,
    end_on       DATE         NOT NULL,
    kind         VARCHAR(20)  NOT NULL,           -- 共享枚举 EventKind
    note         VARCHAR(200),
    seed_key     VARCHAR(120) UNIQUE,
    created_at   TIMESTAMP    NOT NULL
);

CREATE TABLE sales_daily (
    id        SERIAL PRIMARY KEY,
    sku_id    INTEGER   NOT NULL REFERENCES skus(id) ON DELETE CASCADE,
    channel   VARCHAR(24) NOT NULL,
    sold_on   DATE      NOT NULL,
    qty       INTEGER   NOT NULL,
    revenue   DOUBLE PRECISION NOT NULL,
    price     DOUBLE PRECISION NOT NULL,
    is_promo  BOOLEAN   NOT NULL DEFAULT FALSE,
    event_id  INTEGER   REFERENCES price_events(id) ON DELETE SET NULL,
    CONSTRAINT uq_sales_sku_day UNIQUE (sku_id, sold_on)
);

CREATE TABLE lift_runs (
    id             SERIAL PRIMARY KEY,
    run_no         VARCHAR(32) NOT NULL UNIQUE,
    trigger        VARCHAR(20) NOT NULL,
    status         VARCHAR(20) NOT NULL,
    operator_email VARCHAR(160) NOT NULL,
    window_days    INTEGER NOT NULL DEFAULT 90,
    pre_days       INTEGER NOT NULL DEFAULT 14,
    post_days      INTEGER NOT NULL DEFAULT 7,
    event_count    INTEGER NOT NULL DEFAULT 0,
    report_count   INTEGER NOT NULL DEFAULT 0,
    metrics        JSON,
    log_text       TEXT,
    seed_key       VARCHAR(120) UNIQUE,
    started_at     TIMESTAMP NOT NULL,
    finished_at    TIMESTAMP
);

CREATE TABLE lift_reports (
    id             SERIAL PRIMARY KEY,
    run_id         INTEGER NOT NULL REFERENCES lift_runs(id) ON DELETE CASCADE,
    event_id       INTEGER NOT NULL REFERENCES price_events(id) ON DELETE CASCADE,
    sku_id         INTEGER NOT NULL REFERENCES skus(id) ON DELETE CASCADE,
    baseline_qty   DOUBLE PRECISION NOT NULL DEFAULT 0,
    actual_qty     DOUBLE PRECISION NOT NULL DEFAULT 0,
    incremental_qty INTEGER NOT NULL DEFAULT 0,
    lift_pct       DOUBLE PRECISION NOT NULL DEFAULT 0,
    elasticity     DOUBLE PRECISION,
    p_value        DOUBLE PRECISION,
    t_value        DOUBLE PRECISION,
    r2             DOUBLE PRECISION,
    roi            DOUBLE PRECISION,
    roi_band       VARCHAR(12) NOT NULL,          -- 共享枚举 RoiBand
    parallel_ok    BOOLEAN NOT NULL DEFAULT TRUE,
    trend_gap      DOUBLE PRECISION NOT NULL DEFAULT 0,
    control_skus   JSON,
    sample_days    INTEGER NOT NULL DEFAULT 0,
    status         VARCHAR(16) NOT NULL DEFAULT 'pending',
    note           TEXT,
    reviewer       VARCHAR(160),
    review_note    TEXT,
    created_at     TIMESTAMP NOT NULL,
    updated_at     TIMESTAMP NOT NULL,
    CONSTRAINT uq_lift_reports_run_event UNIQUE (run_id, event_id)
);

CREATE TABLE audit_logs (
    id          SERIAL PRIMARY KEY,
    actor_email VARCHAR(160) NOT NULL,
    actor_role  VARCHAR(20)  NOT NULL,
    action      VARCHAR(64)  NOT NULL,
    entity      VARCHAR(40)  NOT NULL,
    entity_id   VARCHAR(64),
    detail      JSON,
    layer       VARCHAR(16)  NOT NULL,
    ip          VARCHAR(64),
    seed_key    VARCHAR(120) UNIQUE,
    created_at  TIMESTAMP    NOT NULL
);
