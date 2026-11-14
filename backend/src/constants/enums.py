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


class IsolationReason(StrEnum):
    """活动不可算的原因：先核对窗口完整性，再判定可算性。

    缺日 / 对照不足 / 价格异常三类分别隔离，互不混淆；
    其余（活动前零销量、活动窗过短等）归入无法测算，同样保留原因说明。
    """

    MISSING_DAYS = "missing_days"
    INSUFFICIENT_CONTROLS = "insufficient_controls"
    PRICE_ANOMALY = "price_anomaly"
    NOT_CALCULABLE = "not_calculable"


ISOLATION_REASON_LABELS: dict[str, str] = {
    IsolationReason.MISSING_DAYS.value: "缺日",
    IsolationReason.INSUFFICIENT_CONTROLS.value: "对照不足",
    IsolationReason.PRICE_ANOMALY.value: "价格异常",
    IsolationReason.NOT_CALCULABLE.value: "无法测算",
}

ISOLATION_REASON_ORDER: list[str] = [
    IsolationReason.MISSING_DAYS.value,
    IsolationReason.INSUFFICIENT_CONTROLS.value,
    IsolationReason.PRICE_ANOMALY.value,
    IsolationReason.NOT_CALCULABLE.value,
]


def roi_band(roi: float | None) -> str:
    """ROI 分档：≥1.2 增利、[1.0, 1.2) 打平、<1 亏损。

    可算活动里 ROI 为 None 只有一种情况：增量 ≤ 0，让利没有换来增量，ROI 不计；
    这类活动确实没跑赢让利，仍按亏损口径标记。
    数据缺陷类活动不会走到这里，它们由 services/eligibility.py 隔离、不写复盘记录。
    """
    if roi is None:
        return RoiBand.LOSS.value
    if roi >= 1.2:
        return RoiBand.PROFIT.value
    if roi >= 1.0:
        return RoiBand.BREAKEVEN.value
    return RoiBand.LOSS.value
