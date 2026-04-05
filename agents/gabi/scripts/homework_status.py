#!/usr/bin/env python3
"""Check today's homework status in the aprendiendo repo.

Returns JSON with homework existence, completion status, and metadata.
Uses only the standard library — no external dependencies.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

APRENDIENDO = Path("/media/dan/fdrive/codeprojects/aprendiendo")
HOMEWORK_DIR = APRENDIENDO / "homework"
TZ = ZoneInfo("America/New_York")

DAYS_ES = {
    "Monday": "lunes",
    "Tuesday": "martes",
    "Wednesday": "miércoles",
    "Thursday": "jueves",
    "Friday": "viernes",
    "Saturday": "sábado",
    "Sunday": "domingo",
}


def parse_metadata(text: str) -> dict:
    """Extract type, time estimate, and total points from homework header."""
    meta = {}

    m = re.search(r"\*\*Type:\*\*\s*(.+)", text)
    if m:
        meta["type"] = m.group(1).strip()

    m = re.search(r"\*\*Time:\*\*\s*(.+)", text)
    if m:
        meta["time_estimate"] = m.group(1).strip()

    # Sum all (N points) in part headers
    points = sum(int(p) for p in re.findall(r"\((\d+)\s+points?\)", text))
    if points:
        meta["total_points"] = points

    parts = len(re.findall(r"^## Part \d+", text, re.MULTILINE))
    if parts:
        meta["parts"] = parts

    return meta


def check_drill_completion(text: str) -> tuple[int, int]:
    """Count filled vs unfilled drill blanks.

    Blanks look like: __________ (10+ underscores with nothing else).
    Filled blanks have word characters mixed in: ___a la_____ or replaced entirely.
    """
    # Match lines that are numbered exercises with blanks
    blank_pattern = re.compile(r"^\d+\.\s+.+_{3,}", re.MULTILINE)
    exercise_lines = blank_pattern.findall(text)

    filled = 0
    unfilled = 0

    for line in exercise_lines:
        # Extract the blank portion(s)
        blanks = re.findall(r"_{3,}[^_]*_{0,}", line)
        for blank in blanks:
            # Check if any word characters appear within the underscore region
            content = blank.strip("_")
            if content and re.search(r"\w", content):
                filled += 1
            else:
                unfilled += 1

    return filled, unfilled


def check_writing_completion(text: str) -> bool:
    """Check if the writing section has student-written content.

    The writing section is the last Part, marked 'Closed Book'.
    Student content appears after the grading breakdown and before the
    final '---' delimiter, as prose lines that aren't template elements.
    """
    # Find the writing section — look for "Closed Book" in a Part header
    writing_match = re.search(
        r"^## Part \d+:.*(?:Closed Book|Writing).*$",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    if not writing_match:
        return False

    writing_section = text[writing_match.start():]

    # Find content after the grading breakdown
    grading_match = re.search(
        r"\*\*Grading breakdown:\*\*.*?(?=\n\n|\n---)",
        writing_section,
        re.DOTALL,
    )
    if not grading_match:
        # No grading section found; look for content after Requirements
        grading_match = re.search(
            r"\*\*Requirements.*?\*\*.*?(?=\n\n)",
            writing_section,
            re.DOTALL,
        )

    if not grading_match:
        return False

    # Everything after the grading/requirements block
    after_grading = writing_section[grading_match.end():]

    # Strip to the closing delimiter
    end_match = re.search(r"^---\s*$", after_grading, re.MULTILINE)
    if end_match:
        after_grading = after_grading[:end_match.start()]

    # Check for prose: non-empty lines that aren't template elements
    template_patterns = re.compile(
        r"^\s*$|"           # empty lines
        r"^---\s*$|"        # delimiters
        r"^\*When finished|" # footer instruction
        r"^#+\s|"           # headers
        r"^\*\*|"           # bold markers (requirements, grading)
        r"^-\s"             # bullet points
    )

    prose_lines = [
        line for line in after_grading.split("\n")
        if line.strip() and not template_patterns.match(line)
    ]

    return len(prose_lines) >= 2  # at least 2 lines of actual writing


def main():
    now = datetime.now(TZ)
    today_str = now.strftime("%Y-%m-%d")
    day_en = now.strftime("%A")
    day_es = DAYS_ES.get(day_en, day_en)

    homework_file = HOMEWORK_DIR / f"{today_str}.md"

    result = {
        "today": today_str,
        "day_of_week": day_es,
        "file_exists": False,
        "file_path": None,
        "completed": False,
        "metadata": {},
    }

    if not homework_file.exists():
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    result["file_exists"] = True
    result["file_path"] = str(homework_file)

    text = homework_file.read_text(encoding="utf-8")
    result["metadata"] = parse_metadata(text)

    # Check completion
    filled, unfilled = check_drill_completion(text)
    total_blanks = filled + unfilled
    drills_done = (filled / total_blanks >= 0.8) if total_blanks > 0 else True
    writing_done = check_writing_completion(text)

    result["completed"] = drills_done and writing_done
    result["drills"] = {"filled": filled, "unfilled": unfilled}
    result["writing_completed"] = writing_done

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
