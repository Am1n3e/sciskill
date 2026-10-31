"""The independent oracle keeps annotation targets distinct from printed content."""

from pdf_e2e.oracles import bibliography_bodies, rendered_text


def test_href_target_is_not_printed_metadata():
    text, targets = rendered_text(r"\href{https://arxiv.org/abs/9999.99999v9}{Visible title}.")
    assert text == "Visible title."
    assert targets == ["https://arxiv.org/abs/9999.99999v9"]
    assert "9999" not in text


def test_native_bibliography_order_includes_empty_occurrences():
    bodies = bibliography_bodies(
        r"\begin{thebibliography}{}\bibitem[ref()]{ref0002}"
        r"\bibitem[A(2024)]{ref0001}Author.\newblock Title.\end{thebibliography}"
    )
    assert [key for key, _ in bodies] == ["ref0002", "ref0001"]
    assert rendered_text(bodies[0][1])[0] == ""
    assert rendered_text(bodies[1][1])[0] == "Author. Title."
