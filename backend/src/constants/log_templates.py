"""审计动作 -> 中文标签。"""
from __future__ import annotations

ACTIONS: dict[str, str] = {
    "auth.login": "登录",
    "sku.create": "新建 SKU",
    "sku.update": "修改 SKU 成本/牌价",
    "event.create": "新建价格活动",
    "event.update": "修改价格活动",
    "lift.create": "发起测算",
    "lift.complete": "测算完成",
    "lift.review": "提交复盘",
    "export.reports": "导出复盘清单",
    "export.runs": "导出测算记录",
    "http.mutation": "写请求",
}
