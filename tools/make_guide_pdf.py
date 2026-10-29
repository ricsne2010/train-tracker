#!/usr/bin/env python3
"""Make the printable installation guide (docs/US-Train-Tracker-Install-Guide.pdf) from docs/INSTALL.md.

The guide is written once, in Markdown; this turns it into a US Letter PDF with a Project Moon Pi cover.
Run it after editing INSTALL.md (needs reportlab and Pillow):

  python3 tools/make_guide_pdf.py

It handles the Markdown the guide uses: headings, paragraphs, bullet and numbered lists, tables, code blocks,
**bold**, `code` and links. Text is set in DejaVu Sans (found in common places, or set GUIDE_FONT_DIR).
"""
import datetime
import os
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "INSTALL.md"
OUT = ROOT / "docs" / "US-Train-Tracker-Install-Guide.pdf"
LOGO = ROOT / "src" / "train_tracker" / "web" / "img" / "moon-pi-logo.png"
REPO = "https://github.com/ricsne2010/train-tracker"
FONT_DIRS = [os.environ.get("GUIDE_FONT_DIR", ""), "/usr/share/fonts/truetype/dejavu", str(Path.home() / "Library/Fonts"),
             "/Library/Fonts", "/Applications/FreeCAD.app/Contents/Resources/fonts",
             "/Applications/FreeCAD.app/Contents/Resources/lib/python3.11/site-packages/matplotlib/mpl-data/fonts/ttf"]
INK, MUTED, ACCENT, RULE = colors.HexColor("#1d2330"), colors.HexColor("#5b6472"), colors.HexColor("#c8102e"), colors.HexColor("#d9dde3")


def find_font(name):
    for d in FONT_DIRS:
        if d and (Path(d) / name).exists():
            return str(Path(d) / name)
    sys.exit(f"{name} not found: install the DejaVu fonts or set GUIDE_FONT_DIR to a folder that has them")


for face, file in [("Sans", "DejaVuSans.ttf"), ("Sans-Bold", "DejaVuSans-Bold.ttf"),
                   ("Sans-Oblique", "DejaVuSans-Oblique.ttf"), ("Mono", "DejaVuSansMono.ttf")]:
    pdfmetrics.registerFont(TTFont(face, find_font(file)))
pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-Bold", italic="Sans-Oblique", boldItalic="Sans-Bold")

S = {
    "body": ParagraphStyle("body", fontName="Sans", fontSize=10, leading=14.5, textColor=INK, spaceAfter=6),
    "h1": ParagraphStyle("h1", fontName="Sans-Bold", fontSize=16, leading=20, textColor=INK, spaceBefore=14, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="Sans-Bold", fontSize=12, leading=16, textColor=ACCENT, spaceBefore=10, spaceAfter=4),
    "cell": ParagraphStyle("cell", fontName="Sans", fontSize=9, leading=12.5, textColor=INK),
    "code": ParagraphStyle("code", fontName="Mono", fontSize=8, leading=11, textColor=INK),
    "title": ParagraphStyle("title", fontName="Sans-Bold", fontSize=30, leading=36, alignment=TA_CENTER, textColor=INK),
    "sub": ParagraphStyle("sub", fontName="Sans", fontSize=16, leading=22, alignment=TA_CENTER, textColor=MUTED),
    "credit": ParagraphStyle("credit", fontName="Sans-Bold", fontSize=13, leading=18, alignment=TA_CENTER, textColor=ACCENT),
    "small": ParagraphStyle("small", fontName="Sans", fontSize=9, leading=13, alignment=TA_CENTER, textColor=MUTED),
}


def inline(text):
    """Markdown inline (bold, code, links) to reportlab's paragraph markup."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"`([^`]+)`", r'<font name="Mono" size="9">\1</font>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)

    def link(m):
        label, url = m.group(1), m.group(2)
        if not re.match(r"https?:", url):
            url = f"{REPO}/blob/main/docs/{url}"
        return f'<link href="{url}" color="#1f5fbf"><u>{label}</u></link>'
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)


def parse(md):
    """Markdown lines to flowables (the title block before the first ## goes on the cover instead)."""
    lines = md.splitlines()
    first = next(i for i, l in enumerate(lines) if l.startswith("## "))
    flow, i = [], first
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip() == "---":
            i += 1
        elif line.startswith("## "):
            flow.append(Paragraph(inline(line[3:]), S["h1"]))
            i += 1
        elif line.startswith("### "):
            flow.append(Paragraph(inline(line[4:]), S["h2"]))
            i += 1
        elif line.startswith("```"):
            j = i + 1
            while not lines[j].startswith("```"):
                j += 1
            code = Preformatted("\n".join(lines[i + 1:j]), S["code"], maxLineLength=92, splitChars="/ ", newLineChars="  ")
            box = Table([[code]], colWidths=[6.5 * inch])
            box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f2f4f7")),
                                     ("BOX", (0, 0), (-1, -1), 0.5, RULE), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                     ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
            flow += [box, Spacer(1, 8)]
            i = j + 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append([Paragraph(inline(c), S["cell"]) for c in cells])
                i += 1
            widths = [1.9 * inch, 4.6 * inch] if len(rows[0]) == 2 else None
            t = Table(rows, colWidths=widths, repeatRows=1 if rows[0][0].text else 0)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f5")),
                                   ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
            flow += [t, Spacer(1, 8)]
        elif re.match(r"(\d+\.|-) ", line):
            ordered = line[0].isdigit()
            items = []
            while i < len(lines) and re.match(r"(\d+\.|-) ", lines[i]):
                text = re.sub(r"^(\d+\.|-) ", "", lines[i])
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                    text += " " + lines[i].strip()
                    i += 1
                items.append(ListItem(Paragraph(inline(text), S["body"]), leftIndent=16))
            flow.append(ListFlowable(items, bulletType="1" if ordered else "bullet", start="1" if ordered else None,
                                     bulletFormat="%s." if ordered else None,
                                     bulletFontName="Sans", bulletFontSize=9, leftIndent=16))
        else:
            text = [line.strip()]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"(#|```|\||(\d+\.|-) )", lines[i]):
                text.append(lines[i].strip())
                i += 1
            flow.append(Paragraph(inline(" ".join(text)), S["body"]))
    return flow


def cover():
    return [Spacer(1, 1.1 * inch), Image(str(LOGO), width=3 * inch, height=3 * inch), Spacer(1, 0.45 * inch),
            Paragraph("US Train Tracker", S["title"]), Spacer(1, 6),
            Paragraph("Installation Guide", S["sub"]), Spacer(1, 0.3 * inch),
            Paragraph("Mac · Windows · Raspberry Pi · iPhone · Android", S["small"]), Spacer(1, 1.2 * inch),
            Paragraph("Designed and Created by Project Moon Pi", S["credit"]), Spacer(1, 8),
            Paragraph(f"{datetime.date.today():%B %Y} · {REPO.replace('https://', '')}", S["small"]),
            PageBreak()]


def footer(canvas, doc):
    if doc.page == 1:
        return
    canvas.saveState()
    canvas.setFont("Sans", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(inch, 0.55 * inch, "US Train Tracker · Installation Guide · Designed and Created by Project Moon Pi")
    canvas.drawRightString(LETTER[0] - inch, 0.55 * inch, str(doc.page))
    canvas.restoreState()


def main():
    doc = SimpleDocTemplate(str(OUT), pagesize=LETTER, leftMargin=inch, rightMargin=inch, topMargin=0.9 * inch,
                            bottomMargin=0.9 * inch, title="US Train Tracker: Installation Guide",
                            author="Project Moon Pi", subject="Installing US Train Tracker on Mac, Windows, Raspberry Pi and phones")
    flow = cover() + parse(SRC.read_text())
    # keep each heading with what follows it
    kept = []
    for f in flow:
        if kept and isinstance(kept[-1], Paragraph) and kept[-1].style.name in ("h1", "h2"):
            kept[-1] = KeepTogether([kept[-1], f])
        else:
            kept.append(f)
    doc.build(kept, onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
