# ironrod

A terminal reader for the LDS standard works (KJV Bible, Book of Mormon,
Doctrine and Covenants, Pearl of Great Price). It opens directly on the verse
you last read, scrolls line by line through the entire canon, and saves your
position on every keystroke.

## Install

```sh
uv tool install .
```

This puts the `ironrod` command on your PATH. Run it:

```sh
ironrod
```

To run it once without installing:

```sh
uvx --from . ironrod
```

## How it works

- On first run, `ironrod` creates a bookmark called `my-study` at Genesis 1:1
  and opens it. You see the study screen immediately — no menu.
- Use `j` / `↓` and `k` / `↑` to scroll line by line. Chapter and book
  boundaries flow continuously: the verse after 1 Nephi 1:20 is 1 Nephi 2:1.
- The verse owning the **top line on screen** is what gets saved. Every
  keystroke that moves the top line rewrites `~/.ironrod/bookmarks.jsonl`.
- Press `g` to fuzzy-find any chapter (`1 Ne 3` matches `1 Nephi 3`).
- Press `:` then a number to jump to a verse in the current chapter
  (e.g. `:7` Enter).
- Press `Enter` in the study screen to append your current position to the
  navigation history (deduplicated against the most recent entry).
- Press `←` / `h` to walk back through the history and `→` / `l` to walk
  forward. The footer shows `← N/M →` while you are walking. Press `Enter` to
  settle (appending the walked-to position with dedup) or `Esc` to cancel and
  return to where you were before walking. Scrolling also settles. Goto and
  verse jumps append to history automatically; plain scrolling does not.
- Press `b` to switch between bookmarks (most-recently-used on top). Press
  `n` from the switcher to create a new one — the new bookmark's birthplace is
  written as its first history entry, so `←` can always walk back to where the
  bookmark started. Switching bookmarks itself does not append to history (the
  current head of each bookmark is already saved in `bookmarks.jsonl`). History
  is per-bookmark and lives in `~/.ironrod/history.jsonl` — delete the file any
  time to clear it.
- Press `q` to quit. Reopening puts you back exactly where you were.

## Data

The bundled `src/ironrod/data/scriptures.db` is a public-domain SQLite export
from <https://github.com/beandog/lds-scriptures>. See
`src/ironrod/data/ATTRIBUTION.txt`.

## Development

```sh
uv sync
uv run pytest
```
