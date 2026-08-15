"""Guard that the interface can render every server message in both locales."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


APP_JS = Path("app/static/app.js").read_text(encoding="utf-8")
PYTHON_SOURCES = ("app/mixing.py", "app/extraction.py", "app/main.py")


def _locale_keys(locale: str) -> set[str]:
    block = re.search(rf"\n  {locale}: \{{\n(.*?)\n  \}},\n", APP_JS, re.S)
    assert block, f"locale {locale} not found in app.js"
    return set(re.findall(r"^    (\w+):", block.group(1), re.M))


def _raised_error_codes() -> set[str]:
    codes: set[str] = set()
    for source in PYTHON_SOURCES:
        codes |= set(re.findall(r'code="([a-z_]+)"', Path(source).read_text(encoding="utf-8")))
    return codes


def test_both_locales_define_the_same_keys() -> None:
    english, chinese = _locale_keys("en"), _locale_keys("zh")

    assert english - chinese == set(), "keys missing from the Chinese locale"
    assert chinese - english == set(), "keys missing from the English locale"


def test_every_raised_error_code_is_translated() -> None:
    codes = _raised_error_codes()
    english, chinese = _locale_keys("en"), _locale_keys("zh")

    assert codes, "no coded errors found; the extraction regex is probably wrong"
    assert {f"error_{code}" for code in codes} <= english
    assert {f"error_{code}" for code in codes} <= chinese


@pytest.mark.parametrize("locale", ["en", "zh"])
def test_reachability_codes_are_translated(locale: str) -> None:
    source = Path("app/mixing.py").read_text(encoding="utf-8")
    reasons = set(re.findall(r'\n\s+reasons,\n\s+"([a-z_]+)"', source))
    suggestions = set(re.findall(r'\n\s+suggestions,\n\s+"([a-z_]+)"', source))
    keys = _locale_keys(locale)

    assert reasons and suggestions, "reason/suggestion codes not found in app/mixing.py"
    assert {f"reason_{code}" for code in reasons} <= keys
    assert {f"suggestion_{code}" for code in suggestions} <= keys


@pytest.mark.parametrize("locale", ["en", "zh"])
def test_translation_placeholders_match_the_parameters_the_server_sends(locale: str) -> None:
    """A {placeholder} with no matching param would render as literal braces."""
    block = re.search(rf"\n  {locale}: \{{\n(.*?)\n  \}},\n", APP_JS, re.S).group(1)
    source = "".join(Path(name).read_text(encoding="utf-8") for name in PYTHON_SOURCES)

    for key, template in re.findall(r"^    (error_\w+):\s*\n?\s*\"(.*?)\",$", block, re.M):
        code = key.removeprefix("error_")
        raise_site = re.search(rf'code="{code}"(.*?)\n\s*\)', source, re.S)
        if raise_site is None:
            continue
        supplied = set(re.findall(r"(\w+)=", raise_site.group(1)))
        for placeholder in re.findall(r"\{(\w+)\}", template):
            assert placeholder in supplied, f"{locale}/{key} uses {{{placeholder}}}, which is never sent"
