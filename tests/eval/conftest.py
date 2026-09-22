"""Surface the eval summary line on every plain `pytest tests/eval/` run.

tests/eval/test_eval.py computes and print()s a recall@8/top-3/MRR summary so
nobody reading a run sees only the flattering pass/fail. But pytest discards
captured stdout for a passing test, so that print() is only visible with
`-s` -- invisible on the command people actually type. This hook re-emits the
same line in the terminal summary section, which always renders regardless of
output capture.

This is a separate file from tests/conftest.py (which loads .env for
OPENAI_API_KEY) so that fixture stays untouched.
"""

from __future__ import annotations


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    from tests.eval.test_eval import LAST_SUMMARY

    if LAST_SUMMARY:
        terminalreporter.write_line(LAST_SUMMARY)
