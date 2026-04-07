from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oms.database import get_db
from oms.enums import AssetClass
from oms.models import Position
from oms.schemas import PositionResponse

router = APIRouter()


@router.get("", response_model=list[PositionResponse])
async def list_positions(
    asset_class: AssetClass | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Position).where(Position.quantity != 0)
    if asset_class:
        stmt = stmt.where(Position.asset_class == asset_class.value)
    stmt = stmt.order_by(Position.symbol)
    result = await db.execute(stmt)
    positions = result.scalars().all()
    return [PositionResponse.model_validate(p) for p in positions]
