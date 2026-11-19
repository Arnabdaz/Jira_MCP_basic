"""Navigate long markdown documents by section, so agents read only what they need.

Long Confluence pages (often AI-written) can run to 100k+ characters. Instead of
returning them whole, tools show a numbered outline and let the agent read one
section, search within the page, or page through parts. Everything here is pure
and deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Linear-time on purpose: an overlapping form like `(.+?)[ \t#]*$` backtracks
# quadratically on long lines of spaces/hashes. Closing hashes are stripped in Python.
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$")
# A fence starts a line, optionally inside blockquotes/panels ("> "). List items and
# table cells never carry one: the ADF converter starts a code-first list item on a
# new line and flattens table cells onto one row, so fence-like text after "- " or
# "| " is ordinary text. Linear: the repeated prefix is a fixed marker character.
_FENCE_RE = re.compile(r"^[ \t]*(?:>[ \t]*)*(`{3,}|~{3,})")
_MAX_DEPTH = 3  # number only the first three heading levels present
_SNIPPET_RADIUS = 200
_PHRASE_BONUS = 500
_MIN_TERM_LEN = 2


@dataclass(frozen=True)
class Section:
    """A numbered section. Offsets index into the markdown it was parsed from."""

    number: str  # "2.1"
    title: str
    depth: int  # 1-based outline depth
    start: int  # start of the heading line
    end: int  # end of the section, including its subsections
    body_start: int  # first character after the heading line
    own_end: int  # end of the section's own text, before its first subsection

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class SearchHit:
    section: Section | None  # None = the intro before the first heading
    snippet: str
    score: int


def _strip_closing_hashes(title: str) -> str:
    """Drop an optional closing `##` sequence ("Setup ##" -> "Setup"; keeps "C# tips")."""
    text = title.strip()
    without = text.rstrip("#")
    if without != text and (not without or without[-1] in " \t"):
        return without.strip()
    return text


def _is_inline_code(marker: str, rest: str) -> bool:
    """A backtick 'fence' whose line contains another backtick is inline code (CommonMark)."""
    return marker[0] == "`" and "`" in rest


def _outline_heads(raw: list[tuple[int, str, int, int]]) -> list[tuple[int, str, int, int]]:
    """Choose the numbered headings and give each its outline depth.

    - A lone top-level heading that opens the page is its title, not a section.
    - Only the first three heading levels present are numbered; deeper ones stay text.
    - Depth follows real nesting (a stack of open ancestors), so a skipped level
      ("# A" then "### B") numbers as 1 / 1.1, never 1.0.1, and a heading before the
      first top-level one never gets a 0.
    """
    levels = sorted({r[0] for r in raw})
    if len(levels) > 1 and raw[0][0] == levels[0] and sum(r[0] == levels[0] for r in raw) == 1:
        levels = levels[1:]
    kept = set(levels[:_MAX_DEPTH])
    heads: list[tuple[int, str, int, int]] = []
    open_levels: list[int] = []
    for level, title, start, body_start in raw:
        if level not in kept:
            continue
        while open_levels and open_levels[-1] >= level:
            open_levels.pop()
        open_levels.append(level)
        heads.append((len(open_levels), title, start, body_start))
    return heads


def parse_sections(md: str) -> tuple[str, list[Section]]:
    """Split markdown into (intro, sections in document order). Code fences are skipped."""
    if not md:
        return "", []

    raw: list[tuple[int, str, int, int]] = []  # (level, title, start, body_start)
    fence: str | None = None  # the open fence marker, e.g. "```" or "~~~~"
    pos = 0
    # Split on "\n" only: str.splitlines also breaks on U+2028, \x0c, ... which
    # markdown does not treat as line ends.
    for line in md.split("\n"):
        text = line.rstrip("\r")
        line_end = min(pos + len(line) + 1, len(md))
        fence_match = _FENCE_RE.match(text)
        rest = text[fence_match.end() :] if fence_match else ""
        if fence_match and fence is None and not _is_inline_code(fence_match.group(1), rest):
            fence = fence_match.group(1)
        elif fence is not None:
            marker = fence_match.group(1) if fence_match else ""
            # CommonMark: a closing fence uses the same character, is at least as long,
            # and has nothing but whitespace after it ("```python" does not close).
            if marker[:1] == fence[0] and len(marker) >= len(fence) and not rest.strip():
                fence = None
        elif fence_match is None:
            match = _HEADING_RE.match(text)
            if match:
                title = _strip_closing_hashes(match.group(2))
                raw.append((len(match.group(1)), title, pos, line_end))
        pos = line_end

    heads = _outline_heads(raw)
    if not heads:
        return md.strip(), []

    # Section ends in one reverse pass (linear): next_at_or_above[d] is the start of
    # the nearest following heading whose depth is <= d.
    ends = [len(md)] * len(heads)
    next_at_or_above = [len(md)] * (_MAX_DEPTH + 1)
    for i in range(len(heads) - 1, -1, -1):
        depth, start = heads[i][0], heads[i][2]
        ends[i] = next_at_or_above[depth]
        for d in range(depth, _MAX_DEPTH + 1):
            next_at_or_above[d] = start

    sections: list[Section] = []
    counters = [0] * _MAX_DEPTH
    for i, (depth, title, start, body_start) in enumerate(heads):
        counters[depth - 1] += 1
        for k in range(depth, _MAX_DEPTH):
            counters[k] = 0
        end = ends[i]
        own_end = heads[i + 1][2] if i + 1 < len(heads) else len(md)
        sections.append(
            Section(
                number=".".join(str(c) for c in counters[:depth]),
                title=title,
                depth=depth,
                start=start,
                end=end,
                body_start=body_start,
                own_end=own_end,
            )
        )
    return md[: heads[0][2]].strip(), sections


def children_of(sections: list[Section], parent: Section | None) -> list[Section]:
    """All descendants of ``parent`` (every section when ``parent`` is None)."""
    if parent is None:
        return list(sections)
    return [s for s in sections if parent.start < s.start < parent.end]


def _fmt_size(chars: int) -> str:
    return f"{chars:,} chars"


def render_outline(
    sections: list[Section], max_entries: int = 80, max_chars: int | None = None
) -> str:
    """Indented outline with numbers and sizes, kept within ``max_entries``/``max_chars``.

    Too big: collapse to two levels, then one level, then list only the first
    sections that fit. The trailing notes say what was left out.
    """
    if not sections:
        return ""
    top = min(s.depth for s in sections)

    def line(s: Section) -> str:
        return f"{'  ' * (s.depth - top)}{s.number} {s.title} ({_fmt_size(s.size)})"

    def fits(lines: list[str]) -> bool:
        within_chars = max_chars is None or len("\n".join(lines)) <= max_chars
        return len(lines) <= max_entries and within_chars

    shown = sections
    for depth_limit in (top + 1, top):
        if fits([line(s) for s in shown]):
            break
        shown = [s for s in sections if s.depth <= depth_limit]
    lines = [line(s) for s in shown]

    notes: list[str] = []
    hidden = len(sections) - len(shown)
    if hidden:
        notes.append(f"({hidden} deeper sections not shown; read a section to see its subsections)")
    if not fits(lines):
        kept: list[str] = []
        for candidate in lines:
            if not fits([*kept, candidate]):
                break
            kept.append(candidate)
        notes.append(
            f"({len(lines) - len(kept)} more sections not shown; use find= to locate them)"
        )
        lines = kept
    return "\n".join(lines) + "".join(f"\n{n}" for n in notes)


def find_sections(sections: list[Section], ref: str) -> list[Section]:
    """Match by number, then exact title (case-insensitive), then title substring."""
    wanted = ref.strip().rstrip(".")
    if not wanted:
        return []
    by_number = [s for s in sections if s.number == wanted]
    if by_number:
        return by_number
    lowered = wanted.lower()
    exact = [s for s in sections if s.title.lower() == lowered]
    if exact:
        return exact
    return [s for s in sections if lowered in s.title.lower()]


def _snippet(text: str, pos: int) -> str:
    start = max(0, pos - _SNIPPET_RADIUS)
    end = pos + _SNIPPET_RADIUS
    body = re.sub(r"\s+", " ", text[start:end]).strip()
    return f"{'…' if start > 0 else ''}{body}{'…' if end < len(text) else ''}"


def search_terms(query: str) -> list[str]:
    """The query words used for searching (lowercased, 2+ characters, de-duplicated)."""
    return sorted({w for w in re.findall(r"\w+", query.lower()) if len(w) >= _MIN_TERM_LEN})


def search_sections(
    md: str,
    intro: str,
    sections: list[Section],
    query: str,
    *,
    limit: int = 5,
    scope: Section | None = None,
) -> list[SearchHit]:
    """Rank sections by how many query terms they contain, then by occurrences.

    With ``scope``, only that section and its subsections are searched.
    """
    terms = search_terms(query)
    if not terms:
        return []
    phrase = " ".join(re.findall(r"\w+", query.lower()))

    if scope is None:
        segments: list[tuple[Section | None, str]] = [(None, intro)]
        segments += [(s, md[s.start : s.own_end]) for s in sections]
    else:
        scoped = [scope, *children_of(sections, scope)]
        segments = [(s, md[s.start : s.own_end]) for s in scoped]

    ranked: list[tuple[int, int, SearchHit]] = []
    for index, (section, text) in enumerate(segments):
        lowered = text.lower()
        counts = {t: lowered.count(t) for t in terms}
        matched = [t for t, c in counts.items() if c]
        if not matched:
            continue
        score = len(matched) * 1000 + sum(counts.values())
        phrase_pos = lowered.find(phrase) if len(terms) > 1 else -1
        if phrase_pos >= 0:
            score += _PHRASE_BONUS
        pos = phrase_pos if phrase_pos >= 0 else min(lowered.find(t) for t in matched)
        ranked.append((-score, index, SearchHit(section, _snippet(text, pos), score)))
    ranked.sort(key=lambda r: (r[0], r[1]))
    return [hit for _, _, hit in ranked[:limit]]


def split_parts(text: str, max_chars: int) -> list[str]:
    """Split into parts of at most ``max_chars``, breaking at blank lines where possible."""
    max_chars = max(1, max_chars)
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    current = ""
    for chunk in text.split("\n\n"):
        if len(chunk) > max_chars:
            # Hard-cut an oversized paragraph by index (no copying of the remainder),
            # topping up the current part first unless little room is left in it.
            start = 0
            while start < len(chunk):
                room = max_chars - (len(current) + 2) if current else max_chars
                # max(1, ...): with a tiny budget, room 0 must still flush, or the
                # empty slice would never advance `start`.
                if current and room < max(1, max_chars // 4):
                    parts.append(current)
                    current = ""
                    continue
                piece = chunk[start : start + room]
                start += len(piece)
                joined = f"{current}\n\n{piece}" if current else piece
                if start >= len(chunk):
                    current = joined  # the tail may share a part with what follows
                else:
                    parts.append(joined)
                    current = ""
            continue
        candidate = f"{current}\n\n{chunk}" if current else chunk
        if len(candidate) <= max_chars:
            current = candidate
        else:
            parts.append(current)
            current = chunk
    if current:
        parts.append(current)
    return parts
