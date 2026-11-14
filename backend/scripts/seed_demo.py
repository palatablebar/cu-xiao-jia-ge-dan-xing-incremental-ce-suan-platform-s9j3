"""幂等 seed：3 账号 / 48 SKU / 90 天销量(4320) / 20 场活动 / 1 次测算批次 → 20 条复盘。

自然键 upsert（重复执行不新增、不覆盖人工改过的复盘状态）：
  users.email / skus.code / price_events.event_no / sales_daily(sku_id, sold_on) / lift_runs.seed_key
  lift_reports(run_id, event_id) / audit_logs.seed_key

SEED_SUMMARY 契约（batch-plan.md 固定键名与顺序；本项目映射见 README）：
  brand=pricelift users=3 sources=<SKU 数> runs=<批次> findings=<复盘条数> pending=<待复盘>
"""
from __future__ import annotations

from sqlalchemy import func, select

from src.config.database import session_scope
from src.models.audit import AuditLog
from src.models.lift_report import LiftReport
from src.models.lift_run import LiftRun
from src.models.price_event import PriceEvent
from src.models.sales_daily import SalesDaily
from src.models.sku import Sku
from src.models.user import User
from src.services import lift_service

from scripts import demo_config as cfg
from scripts.demo_config import DEMO_PASSWORD, DEMO_USERS, ORG

SEED_RUN_KEY = "seed-lift-run-1"
SEED_RUN_OPERATOR = "analyst@pricelift.io"


def ensure_users(db) -> int:
    for email, display_name, role in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            from src.utils.security import hash_password

            db.add(
                User(
                    email=email,
                    password_hash=hash_password(DEMO_PASSWORD),
                    display_name=display_name,
                    role=role,
                    org=ORG,
                )
            )
    db.flush()
    return db.scalar(select(func.count()).select_from(User)) or 0


def ensure_skus(db, catalog: list[dict]) -> dict[str, Sku]:
    existing = {sku.code: sku for sku in db.scalars(select(Sku)).all()}
    for item in catalog:
        if item["code"] in existing:
            continue
        sku = Sku(
            code=item["code"],
            name=item["name"],
            category=item["category"],
            spec=item["spec"],
            channel=item["channel"],
            cost=item["cost"],
            list_price=item["list_price"],
            enabled=True,
        )
        db.add(sku)
        db.flush()
        existing[item["code"]] = sku
    db.flush()
    return existing


def ensure_events(db, events: list[dict], skus: dict[str, Sku]) -> dict[str, PriceEvent]:
    existing = {event.event_no: event for event in db.scalars(select(PriceEvent)).all()}
    for item in events:
        if item["event_no"] in existing:
            continue
        sku = skus[item["sku_code"]]
        event = PriceEvent(
            event_no=item["event_no"],
            sku_id=sku.id,
            channel=item["channel"],
            base_price=item["base_price"],
            promo_price=item["promo_price"],
            discount=item["discount"],
            start_on=item["start_on"],
            end_on=item["end_on"],
            kind=item["kind"],
            note=item["note"],
            seed_key=item["seed_key"],
        )
        db.add(event)
        db.flush()
        existing[item["event_no"]] = event
    db.flush()
    return existing


def ensure_sales(db, sales: list[dict], skus: dict[str, Sku], events: dict[str, PriceEvent]) -> int:
    current = db.scalar(select(func.count()).select_from(SalesDaily)) or 0
    if current >= len(sales):
        return current
    have = {
        (sku_id, sold_on)
        for sku_id, sold_on in db.execute(select(SalesDaily.sku_id, SalesDaily.sold_on)).all()
    }
    mappings = []
    for row in sales:
        sku = skus[row["sku_code"]]
        if (sku.id, row["sold_on"]) in have:
            continue
        event = events.get(row["event_no"]) if row["event_no"] else None
        mappings.append(
            {
                "sku_id": sku.id,
                "channel": row["channel"],
                "sold_on": row["sold_on"],
                "qty": row["qty"],
                "revenue": row["revenue"],
                "price": row["price"],
                "is_promo": row["is_promo"],
                "event_id": event.id if event else None,
            }
        )
    if mappings:
        db.bulk_insert_mappings(SalesDaily, mappings)
        db.flush()
    return db.scalar(select(func.count()).select_from(SalesDaily)) or 0


def ensure_run(db) -> LiftRun:
    run = lift_service.create_and_execute(
        db,
        trigger="seed",
        operator_email=SEED_RUN_OPERATOR,
        seed_key=SEED_RUN_KEY,
    )
    return run


def ensure_audit(db, skus_total: int, events_total: int) -> None:
    seeds = [
        ("seed-audit-sku", "admin@pricelift.io", "admin", "sku.update", "sku", {"count": skus_total}),
        ("seed-audit-event", "admin@pricelift.io", "admin", "event.create", "price_event", {"count": events_total}),
        ("seed-audit-run", SEED_RUN_OPERATOR, "analyst", "lift.create", "lift_run", {"seed": SEED_RUN_KEY}),
    ]
    for seed_key, email, role, action, entity, detail in seeds:
        exists = db.scalar(select(AuditLog).where(AuditLog.seed_key == seed_key))
        if exists is None:
            db.add(
                AuditLog(
                    actor_email=email,
                    actor_role=role,
                    action=action,
                    entity=entity,
                    detail=detail,
                    layer="seed",
                    seed_key=seed_key,
                )
            )
    db.flush()


def seed_all() -> dict:
    catalog, events, sales = cfg.dataset()
    with session_scope() as db:
        users = ensure_users(db)
        skus = ensure_skus(db, catalog)
        event_rows = ensure_events(db, events, skus)
        ensure_sales(db, sales, skus, event_rows)
        ensure_run(db)
        ensure_audit(db, len(skus), len(event_rows))

        reports = db.scalar(select(func.count()).select_from(LiftReport)) or 0
        pending = db.scalar(select(func.count()).select_from(LiftReport).where(LiftReport.status == "pending")) or 0
        runs = db.scalar(select(func.count()).select_from(LiftRun)) or 0
        summary = (
            f"SEED_SUMMARY brand=pricelift users={users} sources={len(skus)} "
            f"runs={runs} findings={reports} pending={pending}"
        )
        print(summary, flush=True)
        return {
            "users": users,
            "skus": len(skus),
            "events": len(event_rows),
            "runs": runs,
            "reports": reports,
            "pending": pending,
        }


if __name__ == "__main__":
    seed_all()
