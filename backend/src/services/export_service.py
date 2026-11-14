"""导出服务：复盘清单 / 测算记录 CSV（UTF-8 BOM，Excel 直接打开）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.enums import (
    CHANNEL_LABELS,
    EVENT_KIND_LABELS,
    REPORT_STATUS_LABELS,
    ROI_BAND_LABELS,
    RUN_STATUS_LABELS,
    TRIGGER_LABELS,
)
from src.models.lift_report import LiftReport
from src.models.lift_run import LiftRun
from src.models.price_event import PriceEvent
from src.models.sku import Sku
from src.utils.csv_export import to_csv


def reports_csv(db: Session, run_id: int | None = None) -> tuple[bytes, int]:
    stmt = select(LiftReport)
    if run_id:
        stmt = stmt.where(LiftReport.run_id == run_id)
    reports = db.scalars(stmt.order_by(LiftReport.id)).all()
    runs = {item.id: item for item in db.scalars(select(LiftRun)).all()}
    events = {item.id: item for item in db.scalars(select(PriceEvent)).all()}
    skus = {item.id: item for item in db.scalars(select(Sku)).all()}

    headers = [
        "事件号",
        "测算批次",
        "SKU编码",
        "SKU名称",
        "品类",
        "渠道",
        "玩法",
        "开始日",
        "结束日",
        "牌价",
        "促销价",
        "折扣率",
        "基线日销",
        "实际日销",
        "增量件数",
        "增量率",
        "弹性",
        "p值",
        "R²",
        "ROI",
        "ROI分档",
        "平行趋势",
        "对照SKU",
        "复盘状态",
        "复核人",
        "复核备注",
        "结论",
    ]
    rows = []
    for item in reports:
        event = events.get(item.event_id)
        sku = skus.get(item.sku_id)
        run = runs.get(item.run_id)
        rows.append(
            [
                event.event_no if event else "",
                run.run_no if run else "",
                sku.code if sku else "",
                sku.name if sku else "",
                sku.category if sku else "",
                CHANNEL_LABELS.get(event.channel, event.channel) if event else "",
                EVENT_KIND_LABELS.get(event.kind, event.kind) if event else "",
                event.start_on.isoformat() if event else "",
                event.end_on.isoformat() if event else "",
                f"{event.base_price:.2f}" if event else "",
                f"{event.promo_price:.2f}" if event else "",
                f"{event.discount * 100:.1f}%" if event else "",
                f"{item.baseline_qty:.1f}",
                f"{item.actual_qty:.1f}",
                item.incremental_qty,
                f"{item.lift_pct * 100:.1f}%" if item.lift_pct is not None else "unknown",
                f"{item.elasticity:.2f}" if item.elasticity is not None else "unknown",
                f"{item.p_value:.4f}" if item.p_value is not None else "",
                f"{item.r2:.2f}" if item.r2 is not None else "",
                f"{item.roi:.2f}" if item.roi is not None else "unknown",
                ROI_BAND_LABELS.get(item.roi_band, item.roi_band),
                "通过" if item.parallel_ok else "存疑",
                "|".join((item.control_skus or {}).get("codes", [])),
                REPORT_STATUS_LABELS.get(item.status, item.status),
                item.reviewer or "",
                item.review_note or "",
                item.note or "",
            ]
        )
    return to_csv(headers, rows), len(rows)


def runs_csv(db: Session) -> tuple[bytes, int]:
    runs = db.scalars(select(LiftRun).order_by(LiftRun.id)).all()
    headers = ["批次号", "触发方式", "状态", "操作人", "窗口天数", "活动数", "复盘条数", "平均弹性", "平均增量", "平均ROI", "开始时间", "结束时间"]
    rows = []
    for run in runs:
        metrics = run.metrics or {}
        rows.append(
            [
                run.run_no,
                TRIGGER_LABELS.get(run.trigger, run.trigger),
                RUN_STATUS_LABELS.get(run.status, run.status),
                run.operator_email,
                run.window_days,
                run.event_count,
                run.report_count,
                metrics.get("avg_elasticity", ""),
                metrics.get("avg_lift_pct", ""),
                metrics.get("avg_roi", ""),
                run.started_at.strftime("%Y-%m-%d %H:%M") if run.started_at else "",
                run.finished_at.strftime("%Y-%m-%d %H:%M") if run.finished_at else "",
            ]
        )
    return to_csv(headers, rows), len(rows)
