"""批次编排 + 隔离留档的数据库层测试（SQLite 内存库，不依赖 PostgreSQL）。

覆盖：缺日 / 价格异常 / 对照不足三类隔离落库、活动总数对账、总览均值只用可算活动、
三份 CSV 的行数与原因计数一致、重跑后可算 ↔ 隔离迁移不留残影。
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts import demo_config as cfg
from src.models import Base
from src.models.lift_isolation import LiftIsolation
from src.models.lift_report import LiftReport
from src.models.price_event import PriceEvent
from src.models.sales_daily import SalesDaily
from src.models.sku import Sku
from src.services import export_service, lift_service, overview_service


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed(db) -> dict:
    catalog, events, sales = cfg.dataset()
    skus: dict[str, Sku] = {}
    for item in catalog:
        row = Sku(
            code=item["code"],
            name=item["name"],
            category=item["category"],
            spec=item["spec"],
            channel=item["channel"],
            cost=item["cost"],
            list_price=item["list_price"],
        )
        db.add(row)
        db.flush()
        skus[item["code"]] = row
    event_rows: dict[str, PriceEvent] = {}
    for item in events:
        row = PriceEvent(
            event_no=item["event_no"],
            sku_id=skus[item["sku_code"]].id,
            channel=item["channel"],
            base_price=item["base_price"],
            promo_price=item["promo_price"],
            discount=item["discount"],
            start_on=item["start_on"],
            end_on=item["end_on"],
            kind=item["kind"],
        )
        db.add(row)
        db.flush()
        event_rows[item["event_no"]] = row
    for item in sales:
        db.add(
            SalesDaily(
                sku_id=skus[item["sku_code"]].id,
                channel=item["channel"],
                sold_on=item["sold_on"],
                qty=item["qty"],
                revenue=item["revenue"],
                price=item["price"],
                is_promo=item["is_promo"],
                event_id=event_rows[item["event_no"]].id if item["event_no"] else None,
            )
        )
    db.flush()
    return {"skus": skus, "events": event_rows, "event_spec": events}


def _break_data(db, data) -> None:
    """制造三类隔离：A2 缺日、B1 活动日价格异常、C2 全部对照缺日。"""
    skus = data["skus"]
    events = data["events"]
    a2 = events["PE-2601"]
    db.query(SalesDaily).filter(
        SalesDaily.sku_id == skus["A2"].id, SalesDaily.sold_on == a2.start_on
    ).delete()
    b1 = events["PE-2602"]
    db.query(SalesDaily).filter(
        SalesDaily.sku_id == skus["B1"].id, SalesDaily.sold_on == b1.start_on
    ).update({"price": round(b1.promo_price * 1.3, 2)})
    c2 = events["PE-2603"]
    # 只删无活动冲突的对照候选的窗口数据（C4 自己的活动窗口覆盖该时段，保留以免连带影响 PE-2608）。
    for code in ("C1", "C3", "C5", "C6", "C7", "C8"):
        db.query(SalesDaily).filter(
            SalesDaily.sku_id == skus[code].id,
            SalesDaily.sold_on >= c2.start_on - timedelta(days=14),
            SalesDaily.sold_on <= c2.end_on,
        ).delete()
    db.flush()


def test_clean_seed_has_all_events_calculable(db):
    data = _seed(db)
    run = lift_service.create_and_execute(db, trigger="seed", operator_email="seed@pricelift.io")
    db.commit()
    assert run.event_count == 20
    assert run.report_count == 20
    assert run.metrics["eligible"] == 20
    assert run.metrics["isolated"] == 0
    assert run.metrics["loss_events"] == 3
    assert data["events"]["PE-2601"].event_no == "PE-2601"


def test_breaks_are_isolated_and_counts_reconcile(db):
    data = _seed(db)
    _break_data(db, data)
    run = lift_service.create_and_execute(db, trigger="manual", operator_email="analyst@pricelift.io")
    db.commit()

    assert run.event_count == 20
    # 缺失的对照窗口会连带影响相邻批次的对照充足性：隔离数按主因逐条对账，不假定固定值。
    assert run.metrics["isolated"] >= 3
    assert run.metrics["eligible"] == 20 - run.metrics["isolated"]
    assert run.metrics["isolation_reasons"]["missing_days"] >= 1
    assert run.metrics["isolation_reasons"]["insufficient_controls"] >= 1
    assert run.metrics["isolation_reasons"]["price_anomaly"] == 1
    # 活动总数 = 可算 + 隔离；原因计数之和 = 隔离数
    assert run.event_count == run.report_count + run.metrics["isolated"]
    assert sum(run.metrics["isolation_reasons"].values()) == run.metrics["isolated"]

    isolations = db.query(LiftIsolation).filter(LiftIsolation.run_id == run.id).all()
    reasons = {row.event_id: row.reason for row in isolations}
    assert reasons[data["events"]["PE-2601"].id] == "missing_days"
    assert reasons[data["events"]["PE-2602"].id] == "price_anomaly"
    assert reasons[data["events"]["PE-2603"].id] == "insufficient_controls"
    # 隔离活动不写复盘记录，也不会出现 0% 增量 / 亏损标签
    assert db.query(LiftReport).filter(LiftReport.run_id == run.id).count() == run.metrics["eligible"]

    over = overview_service.overview(db)
    assert over["reconciliation"]["events_total"] == 20
    assert over["reconciliation"]["calculable_count"] == run.metrics["eligible"]
    assert over["reconciliation"]["isolated_count"] == run.metrics["isolated"]
    assert over["reconciliation"]["reason_total"] == run.metrics["isolated"]
    assert over["reconciliation"]["balanced"] is True
    assert over["loss_total"] <= 3


def test_overview_average_excludes_isolated_events(db):
    _seed(db)
    clean = lift_service.create_and_execute(db, trigger="manual", operator_email="a@pricelift.io")
    db.commit()
    clean_avg = overview_service.overview(db)["avg_lift_pct"]

    data = {"skus": {s.code: s for s in db.query(Sku).all()}, "events": {e.event_no: e for e in db.query(PriceEvent).all()}}
    _break_data(db, data)
    lift_service.execute_run(db, clean)
    db.commit()
    dirty_avg = overview_service.overview(db)["avg_lift_pct"]

    # 隔离不会把均值拉向 0：均值只由可算活动构成
    assert dirty_avg is not None and clean_avg is not None
    assert abs(dirty_avg) > 0.05
    assert abs(dirty_avg - clean_avg) < 0.25


def test_exports_match_page_counts(db):
    data = _seed(db)
    _break_data(db, data)
    run = lift_service.create_and_execute(db, trigger="manual", operator_email="a@pricelift.io")
    db.commit()

    reports_csv, report_rows = export_service.reports_csv(db, run.id)
    isolations_csv, isolation_rows = export_service.isolations_csv(db, run.id)
    runs_csv, _ = export_service.runs_csv(db)

    assert report_rows == run.metrics["eligible"]
    assert isolation_rows == run.metrics["isolated"]
    assert report_rows + isolation_rows == run.event_count
    assert "缺日" in isolations_csv.decode("utf-8-sig")
    assert "价格异常" in isolations_csv.decode("utf-8-sig")
    assert "对照不足" in isolations_csv.decode("utf-8-sig")
    header = runs_csv.decode("utf-8-sig").splitlines()[0]
    for column in ("活动数", "可算数", "隔离数", "原因-缺日", "原因-对照不足", "原因-价格异常"):
        assert column in header
    assert "unknown" not in reports_csv.decode("utf-8-sig")


def test_rerun_moves_event_between_report_and_isolation(db):
    data = _seed(db)
    run = lift_service.create_and_execute(db, trigger="manual", operator_email="a@pricelift.io")
    db.commit()
    a2 = data["events"]["PE-2601"]
    db.query(SalesDaily).filter(
        SalesDaily.sku_id == data["skus"]["A2"].id, SalesDaily.sold_on == a2.start_on
    ).delete()
    db.commit()

    lift_service.execute_run(db, run)
    db.commit()
    assert db.query(LiftReport).filter(LiftReport.run_id == run.id).count() == 19
    assert db.query(LiftIsolation).filter(LiftIsolation.run_id == run.id).count() == 1

    db.add(
        SalesDaily(
            sku_id=data["skus"]["A2"].id,
            channel="hypermarket",
            sold_on=a2.start_on,
            qty=200,
            revenue=round(200 * a2.promo_price, 2),
            price=a2.promo_price,
            is_promo=True,
            event_id=a2.id,
        )
    )
    db.commit()
    lift_service.execute_run(db, run)
    db.commit()
    assert db.query(LiftReport).filter(LiftReport.run_id == run.id).count() == 20
    assert db.query(LiftIsolation).filter(LiftIsolation.run_id == run.id).count() == 0
