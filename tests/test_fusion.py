from pathlib import Path

import pytest

from purser_core.corpus import Corpus
from purser_core.fusion import rrf
from purser_core.glossary import expand_query, find_term
from purser_core.models import GlossaryEntry


def test_rrf_rewards_pages_ranked_well_by_both_lanes():
    lane_a = [(10, 9.0), (20, 8.0), (30, 7.0)]
    lane_b = [(20, 0.9), (30, 0.8), (40, 0.7)]
    fused = rrf(lane_a, lane_b)
    assert fused[0][0] == 20  # only page ranked highly in both


def test_rrf_keeps_pages_found_by_only_one_lane():
    fused = dict(rrf([(10, 9.0)], [(99, 0.5)]))
    assert 10 in fused and 99 in fused


def test_rrf_scores_descend():
    scores = [s for _, s in rrf([(1, 1.0), (2, 0.9)], [(2, 1.0), (3, 0.8)])]
    assert scores == sorted(scores, reverse=True)


def test_rrf_handles_empty_lane():
    assert rrf([], [(5, 1.0)])[0][0] == 5


needs_index = pytest.mark.skipif(not Path("data/manual.sqlite").is_file(), reason="index not built")


@pytest.fixture(scope="module")
def corpus():
    return Corpus("data")


@needs_index
def test_find_term_resolves_an_abbreviation(corpus):
    entry = find_term(corpus, "abp")
    assert entry is not None
    assert "Able Bodied" in entry.definition


@needs_index
def test_expand_query_appends_the_expansion(corpus):
    expanded = expand_query(corpus, "how many ABP do I brief")
    assert "Able Bodied Passenger" in expanded
    assert "ABP" in expanded  # original survives


@needs_index
def test_expand_query_is_a_noop_without_matches(corpus):
    assert expand_query(corpus, "zzzz nonsense") == "zzzz nonsense"


# --- Correction 1: expand_query must inject SHORT expansions only ---
#
# The glossary now holds multi-line prose merged definitions running up to 582
# characters (e.g. "I.C.A.O"). Appending one of those to a six-word question
# drowns the query instead of sharpening it. Only short, abbreviation-style
# definitions (<= 80 chars) belong in the expanded query, capped at 3 per
# query. These use synthetic GlossaryEntry objects so the test does not
# depend on which real manual terms happen to be long or short today.


class _FakeCorpus:
    """Duck-typed stand-in for Corpus: expand_query/find_term only need
    `.glossary` and a settable attribute for the cached index."""

    def __init__(self, entries: list[GlossaryEntry]) -> None:
        self.glossary = entries


def test_expand_query_skips_long_prose_definitions():
    long_definition = "A " * 45 + "very long prose explanation indeed."  # > 80 chars
    assert len(long_definition) > 80
    entries = [GlossaryEntry(term="ICAO", definition=long_definition, pdf_page=1)]
    corpus = _FakeCorpus(entries)

    result = expand_query(corpus, "what is ICAO for")

    assert long_definition not in result
    assert result == "what is ICAO for"


def test_expand_query_injects_short_abbreviation():
    entries = [GlossaryEntry(term="PBE", definition="Protective Breathing Equipment", pdf_page=1)]
    corpus = _FakeCorpus(entries)

    result = expand_query(corpus, "where is the PBE stowed")

    assert "Protective Breathing Equipment" in result
    assert "PBE" in result  # original survives


def test_expand_query_injects_at_most_three_expansions():
    entries = [
        GlossaryEntry(term=f"T{i}", definition=f"Short definition {i}", pdf_page=1)
        for i in range(5)
    ]
    corpus = _FakeCorpus(entries)

    result = expand_query(corpus, "T0 T1 T2 T3 T4")

    injected = sum(1 for e in entries if e.definition in result)
    assert injected == 3
