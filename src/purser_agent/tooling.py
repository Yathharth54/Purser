"""The tool surface the agent and the MCP server share: the page cap and the
words each tool is described with.

Deliberately imports nothing. `purser_mcp` reads these without loading
pydantic-ai, and a description changed here changes it for both surfaces.
"""

from __future__ import annotations

# The most pages one read hands the model. An uncapped read_section returned
# whole sections (4.4 is 80 pages) and every later turn re-sent them: one
# ditching question measured 454k input tokens over 16 model calls.
MAX_READ_PAGES = 6

SEARCH = """Find candidate sections of the manual for a topic.

Returns up to `k` sections, best-scored first, each with the pages inside
it that matched (`hit_pages`) and a `snippet` from the best of them. This
NARROWS the search space -- it does not tell you which candidate is
correct. The right section is first only ~62% of the time and can be
anywhere in the returned list. Read every candidate's section_title and
snippet and judge which one actually answers the question before opening
it with read_section/read_page."""

TOC = "List the manual's Parts and Sections, optionally within one Part."

READ_SECTION = """Read verbatim numbered lines from a section, e.g. section='4.4'.

Returns at most 6 pages per call, starting at `page_from` (a
page_in_section number). Each page carries `section_total`; to read
further, call again with a later `page_from`. Start where search found
the topic -- its `hit_page_numbers` are page_in_section values -- rather
than at page 1 of a long section.

Only for search/toc hits with a real section string. If a search hit's
`section` is None (unsectioned Parts Seven-Ten, Annexures, or a Part's
2-page lead-in), use read_page with its hit_pages instead -- there is no
section string to pass here."""

READ_PAGE = """Read one PDF page plus optional neighbouring pages (up to 2 each side).

Use this for unsectioned search hits (section=None) with the hit's
hit_pages values, or whenever you want a specific page plus its
immediate neighbours without pulling a whole section."""

LOOKUP_TERM = """The manual's own definition of an acronym or term of art.

Prefer this over search for "what does X stand for" / "what is X"
questions about an acronym or defined term -- it is a single hop and
returns the manual's own defining wording, whereas search tends to
surface pages that merely use the term rather than define it."""

ASK = """Ask Purser's own agent a crew question and get a cited answer.

Purser searches and reads the manual itself, then returns a short `body`
plus `citations` whose `text` is spliced byte for byte from the manual --
never written by a model. Use it for a one-call answer; use the reading
tools instead to explore. `not_in_manual` is true when the manual does
not cover the question. Slower (it runs a model) and costs an LLM call."""
