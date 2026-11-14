"""角色 -> 权限点映射。README 与前端 site/js/config.js 同步。

角色键固定为 admin / analyst / viewer，本项目的展示名与职责：
  admin   平台管理员：维护 SKU 成本与活动配置、导出、看审计
  analyst 价格分析师：跑测算式、复盘结论
  viewer  销售只读：只看复盘结果与曲线，不能测算/复盘/导出
"""
from __future__ import annotations

from src.constants.enums import Role

ROLE_LABELS: dict[str, str] = {
    Role.ADMIN.value: "平台管理员",
    Role.ANALYST.value: "价格分析师",
    Role.VIEWER.value: "销售只读",
}

ROLE_DUTIES: dict[str, str] = {
    Role.ADMIN.value: "维护 SKU 成本与活动配置、导出复盘清单、查看审计",
    Role.ANALYST.value: "发起弹性/DID 测算、复核复盘结论、修正口径",
    Role.VIEWER.value: "只读查看活动、曲线与复盘结果，不能测算或导出",
}

PERMISSIONS: dict[str, set[str]] = {
    Role.ADMIN.value: {
        "sku:read", "sku:write",
        "event:read", "event:write",
        "sales:read",
        "lift:read", "lift:create", "lift:review",
        "export:read", "audit:read", "overview:read",
    },
    Role.ANALYST.value: {
        "sku:read",
        "event:read",
        "sales:read",
        "lift:read", "lift:create", "lift:review",
        "export:read", "overview:read",
    },
    Role.VIEWER.value: {
        "sku:read", "event:read", "sales:read", "lift:read", "overview:read",
    },
}

SKU_WRITE_ROLES = (Role.ADMIN.value,)
EVENT_WRITE_ROLES = (Role.ADMIN.value,)
LIFT_CREATE_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
REVIEW_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
EXPORT_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
AUDIT_ROLES = (Role.ADMIN.value,)
READ_ROLES = (Role.ADMIN.value, Role.ANALYST.value, Role.VIEWER.value)


def has_permission(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())
