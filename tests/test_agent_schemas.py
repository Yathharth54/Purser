import pytest
from pydantic import ValidationError

from purser_agent.provider import DEFAULT_MODEL, resolve_model
from purser_agent.schemas import Answer, CiteRef


def test_citeref_has_no_quote_field():
    """The model cannot paraphrase a procedure because it has nowhere to put text."""
    assert "quote" not in CiteRef.model_fields
    assert "text" not in CiteRef.model_fields


def test_answer_with_body_but_no_refs_is_rejected():
    with pytest.raises(ValidationError, match="citation"):
        Answer(body="Cabin crew shall arm all doors.", refs=[])


def test_not_in_manual_is_the_honest_exit():
    a = Answer(body="That isn't covered in the SEP manual.", refs=[], not_in_manual=True)
    assert a.not_in_manual


def test_empty_body_needs_no_refs():
    assert Answer(body="", refs=[]).refs == []


def test_line_range_must_be_non_empty():
    with pytest.raises(ValidationError):
        CiteRef(pdf_page=600, line_from=10, line_to=10)


def test_line_range_rejects_inverted_range():
    with pytest.raises(ValidationError):
        CiteRef(pdf_page=600, line_from=10, line_to=5)


def test_valid_answer_passes():
    a = Answer(body="Brace commands.", refs=[CiteRef(pdf_page=600, line_from=12, line_to=18)])
    assert a.refs[0].pdf_page == 600


def test_pdf_page_out_of_range_is_rejected():
    with pytest.raises(ValidationError):
        CiteRef(pdf_page=1227, line_from=0, line_to=1)
    with pytest.raises(ValidationError):
        CiteRef(pdf_page=0, line_from=0, line_to=1)


def test_resolve_model_default(monkeypatch):
    monkeypatch.delenv("PURSER_MODEL", raising=False)
    assert resolve_model() == DEFAULT_MODEL == "openai:gpt-4o"


def test_resolve_model_override(monkeypatch):
    monkeypatch.setenv("PURSER_MODEL", "anthropic:claude-sonnet")
    assert resolve_model() == "anthropic:claude-sonnet"
