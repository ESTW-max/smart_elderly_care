from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item
from app.schemas import ItemCreate, ItemUpdate


async def list_items(session: AsyncSession) -> list[Item]:
    result = await session.execute(select(Item).order_by(Item.created_at.desc(), Item.id.desc()))
    return list(result.scalars().all())


async def get_item(session: AsyncSession, item_id: int) -> Item | None:
    return await session.get(Item, item_id)


async def create_item(session: AsyncSession, payload: ItemCreate) -> Item:
    item = Item(title=payload.title)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def update_item(session: AsyncSession, item: Item, payload: ItemUpdate) -> Item:
    item.completed = payload.completed
    await session.commit()
    await session.refresh(item)
    return item


async def delete_item(session: AsyncSession, item: Item) -> None:
    await session.delete(item)
    await session.commit()
