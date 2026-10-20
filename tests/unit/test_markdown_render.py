import os
import re
import sys

from PySide6.QtGui import QFont

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from interface.gui.markdown_render import markdown_to_html  # noqa: E402


def render(text, title=None):
    # Sized in pixels, as the app's stylesheet sizes it.
    font = QFont()
    font.setPixelSize(14)
    return markdown_to_html(text, font, title=title)


def test_bold_is_rendered_not_shown_as_asterisks():
    html = render("the **AI/LLM** models")

    assert "**" not in html
    assert re.search(r'font-weight:700;">AI/LLM<', html)


def test_html_in_a_reply_is_shown_as_written():
    html = render("raw <b>tag</b> here")

    assert "&lt;b&gt;tag&lt;/b&gt;" in html


def test_paragraphs_keep_a_gap_with_a_pixel_sized_font():
    html = render("one\n\ntwo")

    assert "margin-bottom:6px" in html


def test_table_is_drawn_as_a_grid():
    html = render("| a | b |\n|---|---|\n| 1 | 2 |")

    table = re.search(r"<table[^>]*>", html).group(0)
    assert "border-collapse" not in table
    assert 'cellspacing="1"' in table and "bgcolor" in table
    assert html.count("<td bgcolor=") == 4


def test_title_goes_above_a_reply_that_opens_with_a_table():
    html = render("| a | b |\n|---|---|\n| 1 | 2 |", title="Assistant:")

    assert html.index("<b>Assistant:</b>") < html.index("<table")
