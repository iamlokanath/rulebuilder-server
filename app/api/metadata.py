from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import get_database
from app.schemas.common import FieldResponse, OperatorResponse, TypeResponse
from app.services.rule_engine import ALLOWED_OPERATORS

router = APIRouter(tags=["Metadata"])


@router.get(
    "/types",
    response_model=list[TypeResponse],
    summary="List available entity types",
)
async def get_types() -> list[TypeResponse]:
    db = get_database()
    cursor = db.type_master.find({}).sort("label", 1)
    items = []
    async for doc in cursor:
        items.append(
            TypeResponse(
                key=doc["key"],
                label=doc["label"],
                collection=doc["collection"],
            )
        )
    return items


@router.get(
    "/fields/{type_key}",
    response_model=list[FieldResponse],
    summary="List fields for a given type",
)
async def get_fields(type_key: str) -> list[FieldResponse]:
    db = get_database()
    type_doc = await db.type_master.find_one({"key": type_key})
    if not type_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Type '{type_key}' not found",
        )

    cursor = db.field_master.find({"type_key": type_key}).sort("label", 1)
    items = []
    async for doc in cursor:
        items.append(
            FieldResponse(
                key=doc["key"],
                label=doc["label"],
                data_type=doc["data_type"],
                value_source=doc["value_source"],
                operators=doc["operators"],
            )
        )
    return items


@router.get(
    "/values/{field_key}",
    response_model=list[str],
    summary="List distinct values for a field",
)
async def get_values(
    field_key: str,
    type_key: str = Query(default="contact", description="Entity type key"),
    search: str | None = Query(default=None, description="Optional search filter"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[str]:
    db = get_database()
    type_doc = await db.type_master.find_one({"key": type_key})
    if not type_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Type '{type_key}' not found",
        )

    field_doc = await db.field_master.find_one(
        {"type_key": type_key, "key": field_key}
    )
    if not field_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Field '{field_key}' not found for type '{type_key}'",
        )

    collection = db[type_doc["collection"]]
    values = await collection.distinct(field_key)
    normalized = sorted({str(value) for value in values if value is not None})

    if search:
        needle = search.strip().lower()
        normalized = [value for value in normalized if needle in value.lower()]

    return normalized[:limit]


@router.get(
    "/operators",
    response_model=list[OperatorResponse],
    summary="List supported operators",
)
async def get_operators() -> list[OperatorResponse]:
    return [
        OperatorResponse(key=key, label=meta["label"], symbol=meta["symbol"])
        for key, meta in ALLOWED_OPERATORS.items()
    ]
