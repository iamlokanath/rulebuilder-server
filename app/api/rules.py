from datetime import datetime, timezone
from math import ceil
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.database import get_database
from app.core.deps import get_current_user
from app.schemas.common import (
    MessageResponse,
    PaginatedRulesResponse,
    RulePreviewRequest,
    RulePreviewResponse,
    SavedRuleCreate,
    SavedRuleResponse,
    SavedRuleUpdate,
)
from app.services.rule_engine import (
    build_query_json,
    build_query_text,
    rules_to_dicts,
    validate_rules,
)

router = APIRouter(prefix="/rules", tags=["Rules"])


def serialize_rule(doc: dict) -> SavedRuleResponse:
    return SavedRuleResponse(
        id=doc["_id"],
        name=doc["name"],
        description=doc.get("description"),
        rules=doc["rules"],
        is_template=doc.get("is_template", False),
        query_text=doc["query_text"],
        query_json=doc["query_json"],
        created_by=doc["created_by"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.post(
    "/preview",
    response_model=RulePreviewResponse,
    summary="Validate rules and generate live query preview",
)
async def preview_rules(payload: RulePreviewRequest) -> RulePreviewResponse:
    rules = rules_to_dicts(payload.rules)
    errors = validate_rules(rules)
    return RulePreviewResponse(
        query_text=build_query_text(rules) if not errors else "",
        query_json=build_query_json(rules) if not errors else {"group": []},
        is_valid=len(errors) == 0,
        errors=errors,
    )


@router.post(
    "/save",
    response_model=SavedRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a rule set or template",
)
async def save_rules(
    payload: SavedRuleCreate,
    current_user: dict = Depends(get_current_user),
) -> SavedRuleResponse:
    rules = rules_to_dicts(payload.rules)
    errors = validate_rules(rules)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=errors,
        )

    now = datetime.now(timezone.utc)
    doc = {
        "_id": str(uuid4()),
        "name": payload.name.strip(),
        "description": (payload.description or "").strip() or None,
        "rules": rules,
        "is_template": payload.is_template,
        "query_text": build_query_text(rules),
        "query_json": build_query_json(rules),
        "created_by": current_user["_id"],
        "created_at": now,
        "updated_at": now,
    }
    db = get_database()
    await db.saved_rules.insert_one(doc)
    return serialize_rule(doc)


@router.get(
    "",
    response_model=PaginatedRulesResponse,
    summary="List saved rules with search and pagination",
)
async def list_rules(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None),
    templates_only: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
) -> PaginatedRulesResponse:
    db = get_database()
    query: dict = {"created_by": current_user["_id"]}
    if templates_only:
        query["is_template"] = True
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"query_text": {"$regex": search, "$options": "i"}},
        ]

    total = await db.saved_rules.count_documents(query)
    skip = (page - 1) * page_size
    cursor = (
        db.saved_rules.find(query)
        .sort("updated_at", -1)
        .skip(skip)
        .limit(page_size)
    )
    items = [serialize_rule(doc) async for doc in cursor]
    total_pages = ceil(total / page_size) if total else 0
    return PaginatedRulesResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{rule_id}",
    response_model=SavedRuleResponse,
    summary="Get a saved rule by id",
)
async def get_rule(
    rule_id: str,
    current_user: dict = Depends(get_current_user),
) -> SavedRuleResponse:
    db = get_database()
    doc = await db.saved_rules.find_one(
        {"_id": rule_id, "created_by": current_user["_id"]}
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )
    return serialize_rule(doc)


@router.put(
    "/{rule_id}",
    response_model=SavedRuleResponse,
    summary="Update a saved rule",
)
async def update_rule(
    rule_id: str,
    payload: SavedRuleUpdate,
    current_user: dict = Depends(get_current_user),
) -> SavedRuleResponse:
    db = get_database()
    doc = await db.saved_rules.find_one(
        {"_id": rule_id, "created_by": current_user["_id"]}
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )

    updates: dict = {"updated_at": datetime.now(timezone.utc)}
    if payload.name is not None:
        updates["name"] = payload.name.strip()
    if payload.description is not None:
        updates["description"] = payload.description.strip() or None
    if payload.is_template is not None:
        updates["is_template"] = payload.is_template
    if payload.rules is not None:
        rules = rules_to_dicts(payload.rules)
        errors = validate_rules(rules)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=errors,
            )
        updates["rules"] = rules
        updates["query_text"] = build_query_text(rules)
        updates["query_json"] = build_query_json(rules)

    await db.saved_rules.update_one({"_id": rule_id}, {"$set": updates})
    updated = await db.saved_rules.find_one({"_id": rule_id})
    return serialize_rule(updated)


@router.delete(
    "/{rule_id}",
    response_model=MessageResponse,
    summary="Delete a saved rule",
)
async def delete_rule(
    rule_id: str,
    current_user: dict = Depends(get_current_user),
) -> MessageResponse:
    db = get_database()
    result = await db.saved_rules.delete_one(
        {"_id": rule_id, "created_by": current_user["_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )
    return MessageResponse(message="Rule deleted successfully")
