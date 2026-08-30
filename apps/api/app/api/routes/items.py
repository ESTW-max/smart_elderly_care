from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.models import Item
from app.schemas import ErrorDetail, ItemCreate, ItemRead, ItemUpdate
from app.services import items as item_service

router = APIRouter()
ItemId = Annotated[int, Path(ge=1)]


@router.get(
    "/items",
    response_model=list[ItemRead],
    operation_id="listItems",
    summary="List items",
)
async def list_items(session: AsyncSession = Depends(get_session)) -> list[Item]:
    return await item_service.list_items(session)


@router.post(
    "/items",
    response_model=ItemRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="createItem",
    summary="Create an item",
)
async def create_item(
    payload: ItemCreate,
    session: AsyncSession = Depends(get_session),
) -> Item:
    return await item_service.create_item(session, payload)


async def get_item_or_404(item_id: int, session: AsyncSession) -> Item:
    item = await item_service.get_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.put(
    "/items/{item_id}",
    response_model=ItemRead,
    operation_id="updateItem",
    responses={404: {"model": ErrorDetail, "description": "Item not found"}},
    summary="Update an item",
)
async def update_item(
    item_id: ItemId,
    payload: ItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> Item:
    item = await get_item_or_404(item_id, session)
    return await item_service.update_item(session, item, payload)


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteItem",
    responses={404: {"model": ErrorDetail, "description": "Item not found"}},
    summary="Delete an item",
)
async def delete_item(item_id: ItemId, session: AsyncSession = Depends(get_session)) -> None:
    item = await get_item_or_404(item_id, session)
    await item_service.delete_item(session, item)
