# ironrod

A terminal reader for the LDS standard works (KJV Bible, Book of Mormon,
Doctrine and Covenants, Pearl of Great Price). It opens directly on the verse
you last read, scrolls line by line through the entire canon, and saves your
position on every keystroke.

## Install

Without cloning the repo, you can simply run:

```sh
uv tool install git+https://github.com/hemmingsv/ironrod
```

This puts the `ironrod` command on your PATH. Run it:

```sh
ironrod
```

To run it once without installing:

```sh
uvx --from git+https://github.com/hemmingsv/ironrod ironrod
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
  settle (committing the walked-to position) or `Esc` to cancel and return to
  where you were before walking. Scrolling also settles. Goto and verse jumps
  append to history automatically; plain scrolling does not.
- Press `q` to quit. Reopening puts you back on the most-recently-used
  bookmark, at the verse you left it on.

You can use ironrod with just the default `my-study` bookmark and never open
the switcher — read at one position and walk history with ←/→. The bookmark
menu only matters if you want to keep separate reading positions:

- Press `b` to switch between bookmarks (most-recently-used on top). Press
  `c` from the switcher to create a new one — the new bookmark's birthplace is
  written as its first history entry, so `←` can always walk back to where the
  bookmark started. Switching bookmarks itself does not append to history (the
  current head of each bookmark is already saved in `bookmarks.jsonl`). History
  is per-bookmark and lives in `~/.ironrod/history.jsonl` — delete the file any
  time to clear it.

## Data

The bundled `src/ironrod/data/scriptures.db` is a public-domain SQLite export
from <https://github.com/beandog/lds-scriptures>. See
`src/ironrod/data/ATTRIBUTION.txt`.

## Development

```sh
uv sync
uv run pytest
uv run ironrod
```
