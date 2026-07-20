"""Language resolution on ingest (bug: widget sometimes sends no/blank language)."""

import pytest

from language import resolve_language


class TestExplicitLanguage:
    def test_supported_code_is_honored(self):
        assert resolve_language("en", page_url="https://x.com/pt/home") == "en"
        assert resolve_language("pt-BR") == "pt-BR"

    @pytest.mark.parametrize("raw,expected", [
        ("pt", "pt-BR"),
        ("PT-BR", "pt-BR"),
        ("portuguese", "pt-BR"),
        ("en-US", "en"),
        ("English", "en"),
        ("es-419", "es"),
        ("italiano", "it"),
    ])
    def test_aliases_and_subtags_normalize(self, raw, expected):
        assert resolve_language(raw) == expected


class TestDerivedFromPage:
    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_missing_language_derives_from_page_url_locale(self, blank):
        assert resolve_language(blank, page_url="https://www.wbdigitalsolutions.com/en/services") == "en"
        assert resolve_language(blank, page_url="https://www.wbdigitalsolutions.com/es") == "es"

    def test_derives_from_current_page_when_page_url_absent(self):
        assert resolve_language(None, page_url="", current_page="/it/prezzi") == "it"

    def test_unrecognized_language_still_derives_from_page(self):
        # e.g. widget sends a locale we don't support, but the page says /en
        assert resolve_language("de-DE", page_url="https://x.com/en/home") == "en"


class TestFallback:
    def test_defaults_to_pt_br_when_nothing_resolves(self):
        assert resolve_language(None) == "pt-BR"
        assert resolve_language("", page_url="https://x.com/websites") == "pt-BR"

    @pytest.mark.parametrize("path", [
        "https://www.wbdigitalsolutions.com/websites",  # 'es' is not a standalone segment
        "https://x.com/entretenimento",                 # not an 'en' locale
        "https://x.com/digital",                        # not an 'it' locale
        "/automation",
    ])
    def test_non_locale_paths_do_not_false_match(self, path):
        assert resolve_language(None, page_url=path) == "pt-BR"


class TestLanguageInstructions:
    """#23: the per-language answer instruction is a single, emphatic, exported source."""

    def test_covers_every_supported_language(self):
        import nodes
        from language import SUPPORTED_LANGUAGES
        for lang in SUPPORTED_LANGUAGES:
            assert lang in nodes.LANGUAGE_INSTRUCTIONS

    def test_instruction_is_emphatic_only(self):
        import nodes
        assert "ONLY" in nodes.LANGUAGE_INSTRUCTIONS["en"]
        assert "SOLO" in nodes.LANGUAGE_INSTRUCTIONS["es"]

    def test_unknown_language_falls_back_to_pt(self):
        import nodes
        assert nodes.language_instruction_for("xx") == nodes.LANGUAGE_INSTRUCTIONS["pt-BR"]
