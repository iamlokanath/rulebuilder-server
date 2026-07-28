from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class MessageResponse(BaseModel):
    message: str
    detail: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(min_length=20)


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    created_at: datetime


class TypeResponse(BaseModel):
    key: str
    label: str
    collection: str


class FieldResponse(BaseModel):
    key: str
    label: str
    data_type: str
    value_source: Literal["distinct", "free_text"]
    operators: list[str]


class OperatorResponse(BaseModel):
    key: str
    label: str
    symbol: str


class RuleItem(BaseModel):
    id: str | None = None
    type: str
    field: str
    operator: str
    value: str | int | float | bool
    next_operator: Literal["AND", "OR", "END"] = "AND"
    group_start: int = Field(default=0, ge=0, le=10)
    group_end: int = Field(default=0, ge=0, le=10)


class RulePreviewRequest(BaseModel):
    rules: list[RuleItem]


class RulePreviewResponse(BaseModel):
    query_text: str
    query_json: dict[str, Any]
    is_valid: bool
    errors: list[str] = []


class SavedRuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    rules: list[RuleItem]
    is_template: bool = False


class SavedRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    rules: list[RuleItem] | None = None
    is_template: bool | None = None


class SavedRuleResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    rules: list[RuleItem]
    is_template: bool
    query_text: str
    query_json: dict[str, Any]
    created_by: str
    created_at: datetime
    updated_at: datetime


class PaginatedRulesResponse(BaseModel):
    items: list[SavedRuleResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ContactResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    company: str
    industry: str
    job_title: str
    department: str
    language: str
    country: str
    state: str
    city: str
    source: str
    status: str
    email: str
    created_date: str


class PaginatedContactsResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int
