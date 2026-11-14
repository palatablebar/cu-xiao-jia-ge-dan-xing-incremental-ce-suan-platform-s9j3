# pricelift · 促销价格弹性与增量测算台

牧原乳品区域销售部（8 人 / 300 个 SKU 口径）的促销复盘工作台。
POS 与渠道回传的「日销量 + 成交价」进系统，先估价格弹性，再用 DID 扣掉自然增长，
最后按边际让利算 ROI —— 结论由后端算出，前端只负责展示。

- 短名：`pricelift`｜前端 18208｜后端 19208｜DB 17708（PostgreSQL 16）
- 演示账号（密码均为 `Demo@2026`）：`admin@pricelift.io` / `analyst@pricelift.io` / `viewer@pricelift.io`
- 5 服务：`frontend`(Nginx 静态站) / `backend`(FastAPI) / `worker`(Celery) / `db` / `redis`

## 1. 业务场景

现状：促销前后销量一对比，看起来都「有效」，没有复盘。
三个痛点决定了这个系统的形状：

1. **自然增长混进促销** —— 所以用同品类、窗口内没做活动的 SKU 做对照组（DID）；
2. **弹性未知** —— 所以先用 log-log OLS 估出「价格每降 1% 销量涨多少」；
3. **折扣越做越亏** —— 所以 ROI 按「增量毛利 / 增量单元的让利」算，`ROI<1` 直接标成亏损。

## 2. 实体（5）

| 实体 | 表 | 关键字段 | 说明 |
|---|---|---|---|
| `Sku` | `skus` | code、name、category、spec、channel、cost、list_price | 成本与牌价是 ROI 的分子/分母 |
| `PriceEvent` | `price_events` | event_no、sku_id、channel、base_price、promo_price、discount、start_on、end_on、kind | 一次促销的价格与窗口 |
| `SalesDaily` | `sales_daily` | sku_id、channel、sold_on、qty、revenue、price、is_promo、event_id | 日销量事实表，`(sku_id, sold_on)` 唯一 |
| `LiftRun` | `lift_runs` | run_no、status、window_days、pre_days、metrics、seed_key | 一次测算批次 |
| `LiftReport` | `lift_reports` | run_id、event_id、baseline_qty、actual_qty、lift_pct、elasticity、p_value、roi、roi_band、status | 一场活动一条复盘，`(run_id, event_id)` 唯一 |

链路：`SKU/活动` → `销量曲线` → `发起测算(LiftRun)` → `LiftReport` → `复盘(confirmed/dismissed)` → `CSV 导出`。

## 3. 算法口径（后端真算）

### 算法 A｜log-log 弹性 OLS —— `backend/src/services/elasticity.py`

```
ln(qty_t) = b0 + b1·ln(price_t) + Σ_w γ_w·weekday_w + b2·promo_t + ε_t
```

- 90 天日数据；`b1` 就是价格弹性；6 个星期哑变量（周一为基准）+ 促销哑变量；
- 正规方程 `(X'X)β = X'y` 自己写高斯消元（部分选主元），再求 `(X'X)⁻¹` 得标准误；
- `t = β/se(β)`，双侧 p 值用 t 分布（不完全 Beta 连分式），`R² = 1 − RSS/TSS`；
- 边界：有效样本 < 30 → `unknown`（"样本不足"）；`ln(price)` 方差 ≈ 0 → `unknown`（"价格无变化"）；
  整段没有促销日时自动去掉 promo 列（否则 `X'X` 奇异）；价格与活动标记完全共线 → `unknown`。

### 算法 B｜DID 增量 + ROI —— `backend/src/services/did.py` / `measure.py`

```
对照组 = 同品类、窗口内无活动、按活动前 14 天日均销量匹配的 3 个 SKU
baseline = pre_treat × (post_ctrl / pre_ctrl)      # 反事实日销量
lift     = post_treat / baseline − 1               # DID 口径增量率
平行趋势：前 14 天按自身均值归一后的日斜率差 < 0.1 视为通过
ROI      = 增量毛利 / 增量单元让利 = (promo_price − cost) / (base_price − promo_price)
```

ROI 采用**边际让利口径**：让利只算在增量单元上（等价于「单件促销毛利 / 单件让利率」）。
若按全量让利（让利额 × 实际销量）计算，ROI 会被 `1+lift` 稀释，本项目不用该口径，页面上也写明了。

## 4. 页面（6）

| hash | 页面 | 内容 |
|---|---|---|
| `#/login` | 登录 | 方格纸实验记录页 + 促销窗口示意图 + 贴胶带登录卡 |
| `#/overview` | 总览 | 活动数 / 平均弹性 / 亏损活动 / 待复盘；90 天全品类销量指数曲线（促销窗口阴影）；手写批注；亏损清单 |
| `#/catalog` | SKU 与活动 | SKU 主数据（筛选 + 抽屉：弹性/活动/销量摘要）、价格活动表；admin 可登记 SKU 与活动 |
| `#/series` | 销量曲线 | 单 SKU 日销量曲线（促销窗口阴影、均值虚线）+ 成交价阶梯 + 弹性口径卡 |
| `#/lift` | 弹性测算与复盘 | 发起测算、批次表、复盘清单（按状态/ROI 分档筛选）、抽屉内提交复盘、导出 |
| `#/export` | 导出与口径 | 两份 CSV 下载 + 算法口径 + 导出自检（只读角色看不到本页） |
| `#/audit` | 审计日志 | 仅 admin：domain/http/worker/seed 四层留痕 |

`#/catalog` 与 `#/lift` 共用 `table` / `drawer` / `filter` 组件（`frontend/site/js/ui.js`）；
`#/overview` 与 `#/series` 共用同一个 SVG 曲线函数 `lineChart()`。

## 5. 共享枚举（2 组以上）

后端唯一定义：`backend/src/constants/enums.py`；前端副本：`frontend/site/js/config.js` 的 `ENUMS`。

| 枚举 | 值 | 出现位置 |
|---|---|---|
| `Channel` 渠道 | hypermarket / convenience / groupbuy / distributor | `models/sku.py`、`schemas/price_event.py`、`services/*_service.py`、`routes/skus.py` 过滤、`pages/catalog.js`、`pages/series.js` |
| `EventKind` 玩法 | discount / threshold / second_half / member_day | `models/price_event.py`、`services/price_event_service.py`、`pages/catalog.js`、`pages/lift.js` |
| `RunStatus` 批次状态 | queued / running / success / partial / failed | `models/lift_run.py`、`services/lift_service.py`、`pages/lift.js` |
| `ReportStatus` 复盘状态 | pending / confirmed / dismissed | `models/lift_report.py`、`schemas/lift.py`、`routes/lift_reports.py`、`pages/lift.js`、`constants/roles.py` |
| `RoiBand` ROI 分档 | profit / breakeven / loss | `constants/enums.py::roi_band()`、`services/did.py`、`services/auth` 之外的导出、`pages/overview.js`、`pages/lift.js` |
| `TriggerKind` 触发方式 | manual / schedule / seed | `models/lift_run.py`、`services/tasks`、`pages/lift.js` |
| `ElasticityState` | ok / unknown | `services/elasticity.py`、`pages/series.js`、`pages/catalog.js` |

角色：`backend/src/constants/roles.py` ↔ 前端 `PERMISSIONS`。

## 6. API

| 方法 | 路径 | 权限 |
|---|---|---|
| POST | `/api/auth/login` / GET `/api/auth/me` | 公开 / 登录 |
| GET | `/api/overview` | 三角色 |
| GET/POST | `/api/skus`、GET/PATCH `/api/skus/{id}` | 读三角色 / 写仅 admin |
| GET/POST | `/api/price-events`、GET/PATCH `/api/price-events/{id}` | 读三角色 / 写仅 admin |
| GET | `/api/sales?sku_id=&days=90` | 三角色 |
| GET/POST | `/api/lift-runs`、GET `/api/lift-runs/{id}` | 读三角色 / 发起 admin+analyst |
| GET | `/api/lift-reports`、`/api/lift-reports/{id}` | 三角色 |
| PATCH | `/api/lift-reports/{id}/review` | admin + analyst（viewer 403） |
| GET | `/api/exports/reports.csv`、`/api/exports/runs.csv` | admin + analyst（viewer 403） |
| GET | `/api/audit` | 仅 admin |
| GET | `/api/health` | 公开 |

错误约定：无 token 401 / 角色不足 403 / 参数非法 422 / 自然键重复 409 / 限流 429。
限流：Redis 固定窗口，读 300/min、写 60/min（写路径前缀 `/skus`、`/price-events`、`/lift-runs`、`/lift-reports`、`/exports`）。

## 7. seed 与数据

`backend/scripts/seed_demo.py` + `backend/scripts/demo_config.py`（纯数据与纯生成函数，可单独导入调参）：

- 3 账号；48 个 SKU（6 品类 × 8 单品，每 SKU 一个渠道）；90 天 × 48 = **4,320 行日销量**；
- 20 场价格活动；1 个测算批次 → **20 条 LiftReport**（其中 3 条 ROI<1）；
- 数据窗口固定截止 `2026-11-12`（写死在 `demo_config.ANCHOR_DATE`），保证两次 seed 逐字一致；
- 促销价由「目标 ROI」反推：`discount = (1 − cost/price) / (1 + target_roi)`，于是折扣深度与毛利结构自洽；
- 幂等自然键：`users.email` / `skus.code` / `price_events.event_no` / `sales_daily(sku_id, sold_on)` /
  `lift_runs.seed_key` / `lift_reports(run_id, event_id)` / `audit_logs.seed_key`；**不覆盖**已提交的复盘状态。

`SEED_SUMMARY` 行（键名与顺序按 batch-plan 固定，本项目映射如下）：

```
SEED_SUMMARY brand=pricelift users=3 sources=48 runs=1 findings=20 pending=20
```

| 契约键 | 本项目含义 |
|---|---|
| `users` | 账号数 |
| `sources` | SKU 数（模板的「接入源」在这里对应单品主数据） |
| `runs` | 测算批次数 |
| `findings` | 复盘条目数（`lift_reports`） |
| `pending` | 待复盘条数 |

演示验收口径（seed 后实际计算值，允许 ±0.02 的浮点差）：
A2 酸奶 950ml 弹性 **−1.80**（p<0.001）、DID 增量 **+17.2%**、ROI **1.24**；
B1 纯奶 250ml×12 增量 +26% 但 ROI **0.70**（亏损）；亏损活动共 3 场（B6 / C2 / B1）。

## 8. 本地运行与测试

```bash
cd projects/gb-609
docker compose config --quiet
docker compose up -d --build                     # 5/5 healthy
docker compose exec -T backend python -m scripts.seed_demo   # 连跑两次，SEED_SUMMARY 一致
docker compose exec -T backend python -m pytest tests -q     # 25 passed
BASE_URL=http://localhost:18208 node ../../test-artifacts/gb-609/tests/smoke.mjs
BASE_URL=http://localhost:18208 node ../../test-artifacts/gb-609/tests/screenshots.cjs
docker compose down -v --remove-orphans
```

`backend/tests` 覆盖：弹性估计（识别精度 / p 值 / 促销日 / 样本不足 / 价格无变化 / 脏行丢弃 / 确定性 / 结论文案 / t 分布参考值）、
DID（基线 / 增量 / 对照组增长扣除 / ROI 分档 / 平行趋势 / 无增量 / 空窗口）、装配层（对照 SKU 匹配与排除、端到端增量、无对照降级）、
安全与工具（口令、JWT、CSV BOM、分页夹取）。

## 9. 视觉

「实验室记录本」：方格纸底（`repeating-linear-gradient` 网格）+ 橄榄绿主色（`oklch(0.44 0.085 128)`）+
打字机数字（Courier Prime）+ 手写楷体批注（LXGW WenKai TC，离线回退 `Kaiti SC` / `KaiTi`）。
左侧是深橄榄「书脊」侧栏 + 便利贴；总览用登记表式数字行（不是等宽卡片墙）；曲线是主视觉。
响应式三档：≥1280（双列 + 登记表 4 列）/ ≥768（单列 + 2 列登记表）/ <768（全部单列，登录页隐藏示意图）。

## 10. 已知简化

- 促销对销量的影响在 seed 数据里就是纯价格效应（没有额外的陈列/堆头效应），所以弹性、增量、ROI 三者自洽；
- `SalesDaily` 每个 SKU 固定一个渠道，真实业务里同一 SKU 会在多渠道同时销售；
- 对照组固定取 3 个、按活动前日均销量匹配，没做倾向得分匹配；
- 弹性用 t 分布精确 p 值，但没有做异方差稳健标准误（HC1）。
