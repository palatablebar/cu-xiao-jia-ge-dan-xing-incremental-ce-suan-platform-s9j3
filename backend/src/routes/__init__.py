"""路由聚合：统一 /api 前缀（Nginx 反代时剥掉 /api）。"""
from fastapi import APIRouter

from src.routes.audit import router as audit_router
from src.routes.auth import router as auth_router
from src.routes.exports import router as exports_router
from src.routes.health import router as health_router
from src.routes.lift_reports import router as lift_reports_router
from src.routes.lift_runs import router as lift_runs_router
from src.routes.overview import router as overview_router
from src.routes.price_events import router as price_events_router
from src.routes.sales import router as sales_router
from src.routes.skus import router as skus_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(overview_router)
api_router.include_router(skus_router)
api_router.include_router(price_events_router)
api_router.include_router(sales_router)
api_router.include_router(lift_runs_router)
api_router.include_router(lift_reports_router)
api_router.include_router(exports_router)
api_router.include_router(audit_router)
