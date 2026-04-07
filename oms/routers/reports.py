from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from oms.database import get_db
from oms.services import report_service

router = APIRouter()


@router.get("/trades")
async def trade_file(trade_date: date | None = None, db: AsyncSession = Depends(get_db)):
    csv_data = await report_service.generate_trade_file(db, trade_date)
    filename = f"GHFM_TRADES_{(trade_date or date.today()).isoformat()}.csv"
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/positions")
async def position_report(db: AsyncSession = Depends(get_db)):
    csv_data = await report_service.generate_position_report(db)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=GHFM_POSITIONS.csv"},
    )


@router.get("/reconciliation")
async def reconciliation(db: AsyncSession = Depends(get_db)):
    return await report_service.generate_reconciliation(db)
