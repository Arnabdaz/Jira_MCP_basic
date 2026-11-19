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
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
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


def parse_sections(md: str) -> tuple[str, list[Section]]:
    """Split markdown into (intro, sections in document order). Code fences are skipped."""
    if not md:
        return "", []

    raw: list[tuple[int, str, int, int]] = []  # (level, title, start, body_start)
    in_fence = False
    pos = 0
    for line in md.splitlines(keepends=True):
        text = line.rstrip("\r\n")
        if _FENCE_RE.match(text):
            in_fence = not in_fence
        elif not in_fence:
            match = _HEADING_RE.match(text)
            if match:
                title = _strip_closing_hashes(match.group(2))
                raw.append((len(match.group(1)), title, pos, pos + len(line)))
        pos += len(line)

    depth_of = {lvl: i + 1 for i, lvl in enumerate(sorted({r[0] for r in raw})[:_MAX_DEPTH])}
    heads = [(depth_of[lvl], title, s, b) for lvl, title, s, b in raw if lvl in depth_of]
    if not heads:
        return md.strip(), []

    sections: list[Section] = []
    counters = [0] * _MAX_DEPTH
    for i, (depth, title, start, body_start) in enumerate(heads):
        counters[depth - 1] += 1
        for k in range(depth, _MAX_DEPTH):
            counters[k] = 0
        end = next((h[2] for h in heads[i + 1 :] if h[0] <= depth), len(md))
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


def render_outline(sections: list[Section], max_entries: int = 80) -> str:
    """Indented outline with numbers and sizes; collapses to two levels when too long."""
    if not sections:
        return ""
    top = min(s.depth for s in sections)
    shown = sections
    note = ""
    if len(sections) > max_entries:
        shown = [s for s in sections if s.depth <= top + 1]
        hidden = len(sections) - len(shown)
        note = f"\n({hidden} deeper sections not shown; read a section to see its subsections)"
        if len(shown) > max_entries:
            note += f"\n({len(shown) - max_entries} more sections after these)"
            shown = shown[:max_entries]
    lines = [f"{'  ' * (s.depth - top)}{s.number} {s.title} ({_fmt_size(s.size)})" for s in shown]
    return "\n".join(lines) + note


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


def search_sections(
    md: str, intro: str, sections: list[Section], query: str, limit: int = 5
) -> list[SearchHit]:
    """Rank sections by how many query terms they contain, then by occurrences."""
    words = re.findall(r"\w+", query.lower())
    terms = sorted({w for w in words if len(w) >= _MIN_TERM_LEN})
    if not terms:
        return []
    phrase = " ".join(words)

    segments: list[tuple[Section | None, str]] = [(None, intro)]
    segments += [(s, md[s.start : s.own_end]) for s in sections]

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
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    current = ""
    for chunk in text.split("\n\n"):
        para = chunk
        while len(para) > max_chars:
            if current:
                parts.append(current)
                current = ""
            parts.append(para[:max_chars])
            para = para[max_chars:]
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars:
            current = candidate
        else:
            parts.append(current)
            current = para
    if current:
        parts.append(current)
    return parts
