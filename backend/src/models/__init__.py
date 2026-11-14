"""ORM 模型聚合导出（Base 用于 create_all）。"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from src.models.user import User  # noqa: E402
from src.models.audit import AuditLog  # noqa: E402
from src.models.sku import Sku  # noqa: E402
from src.models.price_event import PriceEvent  # noqa: E402
from src.models.sales_daily import SalesDaily  # noqa: E402
from src.models.lift_run import LiftRun  # noqa: E402
from src.models.lift_report import LiftReport  # noqa: E402

__all__ = ["Base", "User", "AuditLog", "Sku", "PriceEvent", "SalesDaily", "LiftRun", "LiftReport"]
