#!/usr/bin/env python3
"""Generate a grocery list PDF from JSON input.

Usage:
    generate_grocery_pdf.py <input.json> <output.pdf>

Input JSON format:
{
  "title": "Grocery List - Week of April 6",
  "sections": [
    {
      "name": "Produce",
      "items": [
        {"name": "Cilantro", "qty": "2 bunches", "note": "for Dan only"}
      ]
    }
  ]
}
"""

import json
import sys
from pathlib import Path

from fpdf import FPDF

FONT_DIR = "/usr/share/fonts/truetype/dejavu"


def generate(input_path: str, output_path: str) -> None:
    with open(input_path) as f:
        data = json.load(f)

    pdf = FPDF()
    # Sans for titles/headers, serif for list items
    pdf.add_font("Sans", "B", f"{FONT_DIR}/DejaVuSans-Bold.ttf")
    pdf.add_font("Serif", "", f"{FONT_DIR}/DejaVuSerif.ttf")
    pdf.add_font("Serif", "B", f"{FONT_DIR}/DejaVuSerif-Bold.ttf")
    pdf.add_font("Serif", "I", f"{FONT_DIR}/DejaVuSerif-Italic.ttf")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=10)

    # Title
    pdf.set_font("Sans", "B", 13)
    title = data.get("title", "Grocery List")
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    for section in data.get("sections", []):
        # Section header
        pdf.set_font("Serif", "B", 10)
        pdf.set_fill_color(235, 235, 235)
        pdf.cell(0, 5, f"  {section['name']}", new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(1)

        # Items
        pdf.set_font("Serif", "", 10)
        for item in section.get("items", []):
            qty = item.get("qty", "")
            name = item.get("name", "")
            note = item.get("note", "")

            line = f"   [ ]  {name}"
            if qty:
                line += f"  \u2014  {qty}"
            if note:
                line += f"  ({note})"

            pdf.cell(0, 4.5, line, new_x="LMARGIN", new_y="NEXT")

        pdf.ln(1)

    # Footer
    pdf.set_font("Serif", "I", 8)
    pdf.cell(0, 8, "Eat food. Not too much. Mostly plants.", new_x="LMARGIN", new_y="NEXT")

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pdf.output(output_path)
    print(output_path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: generate_grocery_pdf.py <input.json> <output.pdf>", file=sys.stderr)
        sys.exit(1)
    generate(sys.argv[1], sys.argv[2])
