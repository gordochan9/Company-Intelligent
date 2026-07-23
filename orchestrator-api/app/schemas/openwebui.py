from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OpenWebUIAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=8000)
    messages: list[dict[str, Any]] = Field(default_factory=list, max_length=40)


class OpenWebUIAskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_answer: str
    final_status: str
    public_citations: list[dict[str, Any]] = Field(default_factory=list)
    public_limitations: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)
