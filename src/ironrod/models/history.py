"""HistoryRecord — one entry in a bookmark's navigation history."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ironrod.models.reference import Reference


class HistoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str = Field(min_length=1)
    reference: Reference
    created_at: datetime
