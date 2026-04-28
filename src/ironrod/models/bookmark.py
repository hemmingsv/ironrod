"""Bookmark — a named, persistent reading position."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ironrod.models.reference import Reference


class Bookmark(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    reference: Reference
    created_at: datetime
    updated_at: datetime
