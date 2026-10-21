from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.api.v1._template import build_meta, ok, require_gateway
from app.core.f30_batch import run_live
from app.services.f30.rules import MODEL_VERSION

router = APIRouter(prefix="/api/internal/f30", tags=["F30 nội bộ"],
                   dependencies=[Depends(require_gateway)])


class RunBody(BaseModel):
    run_date: Optional[date] = None
    backfill_days: int = Field(0, ge=0, le=90)


@router.post("/run")
async def chay_batch(body: RunBody):
    run_day = body.run_date.isoformat() if body.run_date else None
    result = await run_in_threadpool(run_live, run_day, body.backfill_days)
    return ok(result, build_meta(model_version=MODEL_VERSION, scope="platform",
                                 collection="anomaly_event", mode="live"))
