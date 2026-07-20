"""Safe, structured response bubble formatting (#22)."""

import main


class TestFormatResponseParts:
    def test_empty_is_no_bubbles(self):
        assert main.format_response_parts("") == []
        assert main.format_response_parts("   \n\n  ") == []

    def test_paragraphs_split_on_blank_lines(self):
        out = main.format_response_parts("Parágrafo um.\n\nParágrafo dois.")
        assert out == ["Parágrafo um.", "Parágrafo dois."]

    def test_no_empty_bubbles_from_extra_blank_lines(self):
        # naive split("\n\n") would emit empty bubbles for the leading/trailing/triple breaks
        out = main.format_response_parts("\n\nUm.\n\n\n\nDois.\n\n")
        assert out == ["Um.", "Dois."]

    def test_bulleted_list_stays_one_bubble(self):
        text = "Fazemos:\n- Sites\n- Automação\n- IA"
        assert main.format_response_parts(text) == [text]

    def test_url_is_never_split_across_bubbles(self):
        text = "Agende aqui: https://agenda.wbdigitalsolutions.com/book?x=1"
        out = main.format_response_parts(text)
        assert out == [text]
        assert all("https://agenda.wbdigitalsolutions.com/book?x=1" in "".join(out) for _ in [0])

    def test_bubbles_are_capped_and_overflow_merged(self):
        text = "\n\n".join(f"P{i}" for i in range(9))
        out = main.format_response_parts(text)
        assert len(out) == main.MAX_RESPONSE_BUBBLES
        # the last bubble holds the merged overflow, nothing is dropped
        assert "".join(out).count("P") == 9
        assert "P8" in out[-1]

    def test_greeting_splits_by_sentence(self):
        out = main.format_response_parts("Olá 👋! Tudo bem? Como ajudo?", is_greeting=True)
        assert len(out) >= 2
        assert out[0] == "Olá 👋!"

    def test_single_line_answer_is_one_bubble(self):
        assert main.format_response_parts("Depende do escopo.") == ["Depende do escopo."]


class TestShapeResponseUsesFormatter:
    def test_non_greeting_uses_blank_line_split(self):
        out = main._shape_response(
            {"revised_response": "A.\n\nB.", "intent": "inquire_services", "step": "x"}, "pt-BR", "/"
        )
        assert out["is_greeting"] is False
        assert out["response_parts"] == ["A.", "B."]

    def test_greeting_splits_into_bubbles(self):
        out = main._shape_response(
            {"revised_response": "Olá 👋! Como posso ajudar?", "intent": "greeting", "step": "x"}, "pt-BR", "/"
        )
        assert out["is_greeting"] is True
        assert len(out["response_parts"]) >= 2


class TestStripMarkdown:
    def test_removes_bold_keeps_text(self):
        assert main.strip_markdown("Somos a **WB Digital Solutions** e ajudamos.") == \
            "Somos a WB Digital Solutions e ajudamos."

    def test_removes_headings_and_stray_markers(self):
        assert main.strip_markdown("## Título\ntexto **x** e __y__") == "Título\ntexto x e y"

    def test_plain_text_unchanged(self):
        assert main.strip_markdown("Olá! Tudo bem? 🚀") == "Olá! Tudo bem? 🚀"

    def test_does_not_mangle_technical_text(self):
        # single * / _ must be left alone: snake_case, math, tech names, URLs
        for keep in ("user_id e all_MiniLM_L6", "3 * 4 = 12", "Next.js e Node.js",
                     "https://x.com/a_b_c", "custa R$ 5 * 2"):
            assert main.strip_markdown(keep) == keep

    def test_does_not_collapse_across_paragraphs(self):
        # no DOTALL: two stray ** in different lines don't eat everything between
        assert main.strip_markdown("linha um **\n\nlinha dois") == "linha um \n\nlinha dois"

    def test_shape_response_strips_bold(self):
        out = main._shape_response(
            {"revised_response": "Fale com a **WB** hoje.", "intent": "inquire_services", "step": "x"},
            "pt-BR", "/",
        )
        assert "**" not in out["response_parts"][0] and "WB" in out["response_parts"][0]
