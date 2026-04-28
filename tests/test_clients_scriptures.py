"""Tests for ScriptureDB against the real bundled SQLite DB."""

from ironrod.clients.scriptures import ScriptureDB
from ironrod.models import Reference

# These constants are baked in by the upstream public-domain dataset.
EXPECTED_VOLUMES = 5
EXPECTED_BOOKS = 87
EXPECTED_CHAPTERS = 1582
EXPECTED_VERSES = 41995
GEN_1_1_TEXT = "In the beginning God created the heaven and the earth."


def test_counts(scripture_db: ScriptureDB) -> None:
    assert len(scripture_db.volumes()) == EXPECTED_VOLUMES
    assert len(scripture_db.books()) == EXPECTED_BOOKS
    assert sum(scripture_db.chapter_count(b.id) for b in scripture_db.books()) == EXPECTED_CHAPTERS


def test_volume_order(scripture_db: ScriptureDB) -> None:
    titles = [v.title for v in scripture_db.volumes()]
    assert titles == [
        "Old Testament",
        "New Testament",
        "Book of Mormon",
        "Doctrine and Covenants",
        "Pearl of Great Price",
    ]


def test_genesis_one_one(scripture_db: ScriptureDB) -> None:
    genesis = next(b for b in scripture_db.books() if b.title == "Genesis")
    verse = scripture_db.verse(Reference(book_id=genesis.id, chapter_number=1, verse_number=1))
    assert verse.text == GEN_1_1_TEXT
    assert verse.book_short_title == "Gen."


def test_one_nephi_one_one_prefix(scripture_db: ScriptureDB) -> None:
    nephi = next(b for b in scripture_db.books() if b.title == "1 Nephi")
    verse = scripture_db.verse(Reference(book_id=nephi.id, chapter_number=1, verse_number=1))
    assert verse.text.startswith("I, Nephi, having been born of goodly parents")


def test_chapter_verses_returns_all(scripture_db: ScriptureDB) -> None:
    nephi = next(b for b in scripture_db.books() if b.title == "1 Nephi")
    verses = scripture_db.chapter_verses(nephi.id, 1)
    assert len(verses) == 20  # 1 Nephi 1 has 20 verses
    assert verses[0].reference.verse_number == 1
    assert verses[-1].reference.verse_number == 20


def test_eternal_scroll_across_chapter_boundary(scripture_db: ScriptureDB) -> None:
    nephi = next(b for b in scripture_db.books() if b.title == "1 Nephi")
    last_of_ch1 = Reference(book_id=nephi.id, chapter_number=1, verse_number=20)
    assert scripture_db.next_reference(last_of_ch1) == Reference(
        book_id=nephi.id, chapter_number=2, verse_number=1,
    )


def test_eternal_scroll_across_book_boundary(scripture_db: ScriptureDB) -> None:
    # Last verse of Malachi (last OT book) → first verse of Matthew.
    malachi = next(b for b in scripture_db.books() if b.title == "Malachi")
    matthew = next(b for b in scripture_db.books() if b.title == "Matthew")
    last = Reference(
        book_id=malachi.id,
        chapter_number=scripture_db.chapter_count(malachi.id),
        verse_number=scripture_db.verse_count(malachi.id, scripture_db.chapter_count(malachi.id)),
    )
    assert scripture_db.next_reference(last) == Reference(
        book_id=matthew.id, chapter_number=1, verse_number=1,
    )


def test_canon_start_prev_is_none(scripture_db: ScriptureDB) -> None:
    assert scripture_db.prev_reference(scripture_db.first_reference()) is None


def test_canon_end_next_is_none(scripture_db: ScriptureDB) -> None:
    assert scripture_db.next_reference(scripture_db.last_reference()) is None


def test_chapter_index_count_and_first(scripture_db: ScriptureDB) -> None:
    idx = scripture_db.chapter_index()
    assert len(idx) == EXPECTED_CHAPTERS
    assert idx[0].label == "Genesis 1"
    assert idx[0].chapter_number == 1


def test_chapter_index_includes_one_nephi_3(scripture_db: ScriptureDB) -> None:
    labels = {entry.label for entry in scripture_db.chapter_index()}
    assert "1 Nephi 3" in labels
    assert "Psalms 119" in labels


def test_unknown_verse_raises(scripture_db: ScriptureDB) -> None:
    bogus = Reference(book_id=1, chapter_number=1, verse_number=999)
    try:
        scripture_db.verse(bogus)
    except KeyError:
        return
    raise AssertionError("expected KeyError for missing verse")


def test_total_verse_count_matches_dataset(scripture_db: ScriptureDB) -> None:
    total = sum(
        scripture_db.verse_count(b.id, ch)
        for b in scripture_db.books()
        for ch in range(1, scripture_db.chapter_count(b.id) + 1)
    )
    assert total == EXPECTED_VERSES
