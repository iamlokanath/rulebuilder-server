from math import ceil
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.database import get_database
from app.core.deps import get_current_user
from app.schemas.common import PaginatedContactsResponse, RulePreviewRequest
from app.services.rule_engine import rules_to_dicts, validate_rules


router = APIRouter(prefix="/contacts", tags=["Contacts"])


OPERATOR_MAP = {
    "=": "$eq",
    "!=": "$ne",
    ">": "$gt",
    "<": "$lt",
    ">=": "$gte",
    "<=": "$lte",
}


def build_mongo_filter(rules: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten nested groups into MongoDB $and/$or expressions."""
    if not rules:
        return {}

    def apply_operator(field: str, operator: str, value: Any) -> dict[str, Any]:
        if operator == "LIKE":
            return {field: {"$regex": str(value), "$options": "i"}}
        if operator == "NOT LIKE":
            return {field: {"$not": {"$regex": str(value), "$options": "i"}}}
        if operator == "IN":
            values = [item.strip() for item in str(value).split(",") if item.strip()]
            return {field: {"$in": values}}
        if operator == "NOT IN":
            values = [item.strip() for item in str(value).split(",") if item.strip()]
            return {field: {"$nin": values}}
        mongo_op = OPERATOR_MAP.get(operator, "$eq")
        return {field: {mongo_op: value}}

    # Evaluate nested groups with a stack-based approach
    stack: list[list[dict[str, Any]]] = [[]]
    combinators: list[str] = ["AND"]

    for index, rule in enumerate(rules):
        for _ in range(int(rule.get("group_start") or 0)):
            stack.append([])
            combinators.append("AND")

        condition = apply_operator(rule["field"], rule["operator"], rule["value"])
        stack[-1].append(condition)

        for _ in range(int(rule.get("group_end") or 0)):
            group = stack.pop()
            combinator = combinators.pop()
            joined = {"$and": group} if combinator == "AND" else {"$or": group}
            if len(group) == 1:
                joined = group[0]
            stack[-1].append(joined)

        if index < len(rules) - 1:
            next_op = (rule.get("next_operator") or "AND").upper()
            if next_op in {"AND", "OR"} and stack:
                # Store intended combinator for current open group
                combinators[-1] = next_op

    def join_group(items: list[dict[str, Any]], combinator: str) -> dict[str, Any]:
        if not items:
            return {}
        if len(items) == 1:
            return items[0]
        key = "$and" if combinator == "AND" else "$or"
        return {key: items}

    while len(stack) > 1:
        group = stack.pop()
        combinator = combinators.pop()
        stack[-1].append(join_group(group, combinator))

    return join_group(stack[0], combinators[0] if combinators else "AND")


@router.get(
    "",
    response_model=PaginatedContactsResponse,
    summary="List contacts with optional rule-based filtering",
)
async def list_contacts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> PaginatedContactsResponse:
    del current_user
    db = get_database()
    query: dict[str, Any] = {}
    if search:
        query["$or"] = [
            {"first_name": {"$regex": search, "$options": "i"}},
            {"last_name": {"$regex": search, "$options": "i"}},
            {"company": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]

    total = await db.contacts.count_documents(query)
    skip = (page - 1) * page_size
    cursor = db.contacts.find(query).sort("id", 1).skip(skip).limit(page_size)
    items = []
    async for doc in cursor:
        doc.pop("_id", None)
        items.append(doc)

    return PaginatedContactsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
    )


@router.post(
    "/filter",
    response_model=PaginatedContactsResponse,
    summary="Filter contacts using dynamic rule builder payload",
)
async def filter_contacts(
    payload: RulePreviewRequest,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> PaginatedContactsResponse:
    del current_user
    rules = rules_to_dicts(payload.rules)
    errors = validate_rules(rules)
    if errors:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=errors,
        )

    mongo_filter = build_mongo_filter(rules)
    db = get_database()
    total = await db.contacts.count_documents(mongo_filter)
    skip = (page - 1) * page_size
    cursor = (
        db.contacts.find(mongo_filter).sort("id", 1).skip(skip).limit(page_size)
    )
    items = []
    async for doc in cursor:
        doc.pop("_id", None)
        items.append(doc)

    return PaginatedContactsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
    )
