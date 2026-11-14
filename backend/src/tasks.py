"""Celery 任务：心跳 + 每日自动重算（把全部活动再跑一遍，产出当天批次）。"""
from __future__ import annotations

import time

from src.config.celery_app import TASK_DAILY, TASK_HEARTBEAT, celery_app
from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger("tasks")


def _redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@celery_app.task(name=TASK_HEARTBEAT)
def heartbeat() -> str:
    try:
        _redis().set(f"{settings.app_name}:worker:heartbeat", time.time())
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("heartbeat failed: %s", exc)
        return "error"


@celery_app.task(name=TASK_DAILY)
def daily_refresh() -> dict:
    """每天 07:40 自动跑一次测算，让总览里的复盘条目不会过期。"""
    from src.config.database import session_scope
    from src.services import audit_service, lift_service

    with session_scope() as db:
        run = lift_service.create_and_execute(
            db,
            trigger="schedule",
            operator_email="scheduler@" + settings.app_name + ".io",
        )
        audit_service.record(
            db,
            actor_email="scheduler@" + settings.app_name + ".io",
            actor_role="admin",
            action="lift.complete",
            entity="lift_run",
            entity_id=run.id,
            detail={"trigger": "schedule", "run_no": run.run_no, "reports": run.report_count},
            layer="worker",
        )
    logger.info("daily refresh finished: run=%s reports=%s", run.run_no, run.report_count)
    return {"run_no": run.run_no, "reports": run.report_count}
