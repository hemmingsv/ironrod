"""Scripture identity types: Volume, Book, Reference, Verse, ChapterEntry."""

from pydantic import BaseModel, ConfigDict, Field


class Volume(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int = Field(ge=1)
    title: str
    short_title: str


class Book(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int = Field(ge=1)
    volume_id: int = Field(ge=1)
    title: str
    short_title: str


class Reference(BaseModel):
    """Pointer to a single verse — the unit of persistence."""

    model_config = ConfigDict(frozen=True)

    book_id: int = Field(ge=1)
    chapter_number: int = Field(ge=1)
    verse_number: int = Field(ge=1)


class Verse(BaseModel):
    model_config = ConfigDict(frozen=True)

    reference: Reference
    book_title: str
    book_short_title: str
    text: str


class ChapterEntry(BaseModel):
    """One row of the chapter index used by the Goto fuzzy-finder."""

    model_config = ConfigDict(frozen=True)

    book_id: int = Field(ge=1)
    book_title: str
    book_short_title: str
    chapter_number: int = Field(ge=1)
    label: str
