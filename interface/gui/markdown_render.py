"""Turns the model's Markdown replies into the rich text a QLabel shows:
bold, lists, headings, tables, code. Qt parses the Markdown itself; this only
evens out how it looks inside a chat cell."""
import html
import re

from PySide6.QtGui import (QColor, QFont, QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextDocument, QTextFormat, QTextTable)

_BODY_TAG_RE = re.compile(r"<body[^>]*>")

_CODE_FAMILIES = ["Menlo", "Consolas", "monospace"]
_CODE_BACKGROUND = QColor("#e6ebdc")
_TABLE_BORDER = QColor("#d5dccb")
_TABLE_HEADER_BACKGROUND = QColor("#eef2e7")
_TABLE_CELL_BACKGROUND = QColor("#ffffff")
_QUOTE_COLOR = QColor("#5f6673")
_INDENT_PX = 20
_PARAGRAPH_GAP_PX = 6


def markdown_to_html(text: str, font: QFont, title: str | None = None) -> str:
    """`font` is the label's own, so the reply matches the rest of the chat;
    the document's default would come out smaller. `title` goes above the
    reply in bold, on a line of its own, like "You:" over a prompt."""
    doc = QTextDocument()
    doc.setDefaultFont(font)
    doc.setIndentWidth(_INDENT_PX)
    features = QTextDocument.MarkdownFeature
    # GitHub's dialect, for its tables. Without HTML: a tag in a reply is
    # shown as written, not rendered.
    doc.setMarkdown(text, features.MarkdownDialectGitHub | features.MarkdownNoHTML)
    _style_blocks(doc)
    _style_tables(doc.rootFrame())
    rendered = doc.toHtml()
    if title:
        # Added to the HTML rather than the document: a reply that opens
        # with a table would take a line inserted at its start into the
        # table's first cell.
        heading = f'<p style="margin:0px;"><b>{html.escape(title)}</b></p>'
        rendered = _BODY_TAG_RE.sub(lambda m: m.group(0) + heading, rendered, count=1)
    return rendered


def _select_block(block) -> QTextCursor:
    cursor = QTextCursor(block)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
    return cursor


def _style_blocks(doc: QTextDocument):
    first, last = doc.begin(), doc.lastBlock()
    block = first
    while block.isValid():
        fmt = block.blockFormat()
        block_format = QTextBlockFormat()
        char_format = QTextCharFormat()

        # Spacing is set here rather than left to the parser, which derives it
        # from the font's point size - and the app's font is sized in pixels,
        # which leaves paragraphs with no space between them.
        if QTextCursor(block).currentTable() is not None:
            pass                                    # cells have their padding
        elif block.textList() is not None:
            block_format.setTopMargin(0)
            block_format.setBottomMargin(2)
        else:
            block_format.setTopMargin(_PARAGRAPH_GAP_PX)
            block_format.setBottomMargin(_PARAGRAPH_GAP_PX)

        if fmt.headingLevel():
            # Markdown's sizes are a page's; a reply needs only a step up.
            char_format.setProperty(QTextFormat.Property.FontSizeAdjustment,
                                    1 if fmt.headingLevel() <= 2 else 0)
            char_format.setFontWeight(QFont.Weight.Bold)
            block_format.setTopMargin(10)
            block_format.setBottomMargin(4)
        elif fmt.hasProperty(QTextFormat.Property.BlockCodeFence):
            block_format.setBackground(_CODE_BACKGROUND)
            char_format.setFontFamilies(_CODE_FAMILIES)
            char_format.setFontFixedPitch(True)
        elif fmt.hasProperty(QTextFormat.Property.BlockQuoteLevel):
            char_format.setForeground(_QUOTE_COLOR)
            char_format.setFontItalic(True)

        # The cell's own padding is all the space it needs at its edges.
        if block == first:
            block_format.setTopMargin(0)
        if block == last:
            block_format.setBottomMargin(0)

        cursor = _select_block(block)
        cursor.mergeBlockFormat(block_format)
        cursor.mergeCharFormat(char_format)
        _style_inline_code(block)
        block = block.next()


def _style_inline_code(block):
    """`code` comes in as fixed-pitch text in the default family."""
    it = block.begin()
    while not it.atEnd():
        fragment = it.fragment()
        it += 1
        if not fragment.charFormat().fontFixedPitch():
            continue
        cursor = QTextCursor(block.document())
        cursor.setPosition(fragment.position())
        cursor.setPosition(fragment.position() + fragment.length(),
                           QTextCursor.MoveMode.KeepAnchor)
        code = QTextCharFormat()
        code.setFontFamilies(_CODE_FAMILIES)
        if not block.blockFormat().hasProperty(QTextFormat.Property.BlockCodeFence):
            code.setBackground(_CODE_BACKGROUND)
        cursor.mergeCharFormat(code)


def _style_tables(frame):
    for child in frame.childFrames():
        if isinstance(child, QTextTable):
            # A QLabel draws no borders for a collapsed table, and doubled
            # ones otherwise. The grid is the table's own colour showing
            # through a pixel of spacing between cells with their own.
            fmt = child.format()
            fmt.setBorder(0)
            fmt.setBorderCollapse(False)        # the parser's default; it drops the spacing
            fmt.setBackground(_TABLE_BORDER)
            fmt.setCellSpacing(1)
            fmt.setCellPadding(5)
            fmt.setTopMargin(_PARAGRAPH_GAP_PX)
            fmt.setBottomMargin(_PARAGRAPH_GAP_PX)
            child.setFormat(fmt)
            for row in range(child.rows()):
                for column in range(child.columns()):
                    cell = child.cellAt(row, column)
                    cell_format = cell.format()
                    cell_format.setBackground(
                        _TABLE_HEADER_BACKGROUND if row == 0 else _TABLE_CELL_BACKGROUND)
                    cell.setFormat(cell_format)
        _style_tables(child)
