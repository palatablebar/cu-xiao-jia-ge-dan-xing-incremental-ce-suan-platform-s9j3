"""共享枚举（后端唯一定义处）。前端副本见 frontend/site/js/config.js。

README「共享枚举出现位置」一节列出全部出现点，改动需两侧同步。
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Channel(StrEnum):
    """销售渠道：决定销量口径与活动投放面。"""

    HYPERMARKET = "hypermarket"
    CONVENIENCE = "convenience"
    GROUPBUY = "groupbuy"
    DISTRIBUTOR = "distributor"


CHANNEL_LABELS: dict[str, str] = {
    Channel.HYPERMARKET.value: "商超",
    Channel.CONVENIENCE.value: "便利店",
    Channel.GROUPBUY.value: "社区团购",
    Channel.DISTRIBUTOR.value: "二批商",
}

CHANNEL_ORDER: list[str] = [
    Channel.HYPERMARKET.value,
    Channel.CONVENIENCE.value,
    Channel.GROUPBUY.value,
    Channel.DISTRIBUTOR.value,
]


class EventKind(StrEnum):
    """促销玩法：影响让利口径与是否计入价格弹性。"""

    DISCOUNT = "discount"
    THRESHOLD = "threshold"
    SECOND_HALF = "second_half"
    MEMBER_DAY = "member_day"


EVENT_KIND_LABELS: dict[str, str] = {
    EventKind.DISCOUNT.value: "直接降价",
    EventKind.THRESHOLD.value: "满减",
    EventKind.SECOND_HALF.value: "第二件半价",
    EventKind.MEMBER_DAY.value: "会员日",
}

EVENT_KIND_ORDER: list[str] = [
    EventKind.DISCOUNT.value,
    EventKind.THRESHOLD.value,
    EventKind.SECOND_HALF.value,
    EventKind.MEMBER_DAY.value,
]


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


RUN_STATUS_LABELS: dict[str, str] = {
    RunStatus.QUEUED.value: "排队中",
    RunStatus.RUNNING.value: "测算中",
    RunStatus.SUCCESS.value: "完成",
    RunStatus.PARTIAL.value: "部分完成",
    RunStatus.FAILED.value: "失败",
}


class TriggerKind(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    SEED = "seed"


TRIGGER_LABELS: dict[str, str] = {
    TriggerKind.MANUAL.value: "手动",
    TriggerKind.SCHEDULE.value: "定时",
    TriggerKind.SEED.value: "初始化",
}


class ReportStatus(StrEnum):
    """复盘结论：只有 admin / analyst 能改。"""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


REPORT_STATUS_LABELS: dict[str, str] = {
    ReportStatus.PENDING.value: "待复盘",
    ReportStatus.CONFIRMED.value: "复盘通过",
    ReportStatus.DISMISSED.value: "复盘驳回",
}

REPORT_STATUS_ORDER: list[str] = [
    ReportStatus.PENDING.value,
    ReportStatus.CONFIRMED.value,
    ReportStatus.DISMISSED.value,
]


class RoiBand(StrEnum):
    """ROI 分档：<1 即「折扣越做越亏」的活动。"""

    PROFIT = "profit"
    BREAKEVEN = "breakeven"
    LOSS = "loss"


ROI_BAND_LABELS: dict[str, str] = {
    RoiBand.PROFIT.value: "增利",
    RoiBand.BREAKEVEN.value: "打平",
    RoiBand.LOSS.value: "亏损",
}

ROI_BAND_ORDER: list[str] = [RoiBand.PROFIT.value, RoiBand.BREAKEVEN.value, RoiBand.LOSS.value]


class ElasticityState(StrEnum):
    """弹性估计状态：样本不足或价格无变化时不下结论。"""

    OK = "ok"
    UNKNOWN = "unknown"


ELASTICITY_STATE_LABELS: dict[str, str] = {
    ElasticityState.OK.value: "已估计",
    ElasticityState.UNKNOWN.value: "不可估计",
}


def roi_band(roi: float | None) -> str:
    """ROI 分档（None 视为亏损口径外的未知，按 loss 显示并附原因）。"""
    if roi is None:
        return RoiBand.LOSS.value
    if roi >= 1.2:
        return RoiBand.PROFIT.value
    if roi >= 1.0:
        return RoiBand.BREAKEVEN.value
    return RoiBand.LOSS.value
