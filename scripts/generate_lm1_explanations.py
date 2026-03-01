#!/usr/bin/env python3
"""
Generate explanation files for LM1 past papers by extracting explanations from the LM1 Study Text PDF.
Stores one file per past paper in the past_papers folder so explanations correspond to each paper.

Run from project root: python3 scripts/generate_lm1_explanations.py

Output: modules/LM1/past_papers/<paper_stem> Explanations.txt (e.g. "LM1 Exam - 2026 Explanations.txt")
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

import re
from app import load_questions, study_index, MODULES_DIR


def main():
    past_papers_dir = MODULES_DIR / "LM1" / "past_papers"
    past_papers_dir.mkdir(parents=True, exist_ok=True)

    print("Loading questions...")
    questions = load_questions()
    lm1_questions = [q for q in questions if q.get("module") == "LM1"]
    print(f"Found {len(lm1_questions)} LM1 questions.")

    # Group by source_file (one past paper per file)
    by_source = {}
    for q in lm1_questions:
        src = q.get("source_file") or ""
        if not src or not (src.endswith(".pdf") or src.endswith(".txt")):
            continue
        stem = Path(src).stem  # e.g. "LM1 Exam - 2026"
        if stem not in by_source:
            by_source[stem] = []
        by_source[stem].append(q)

    total_written = 0
    for stem, qs in sorted(by_source.items()):
        out_file = past_papers_dir / f"{stem} Explanations.txt"
        blocks = []
        for i, q in enumerate(qs, start=1):
            question_text = q.get("question", "").strip()
            if not question_text:
                continue
            options = q.get("options") or []
            correct_letter = (q.get("correct_answer") or "").strip().upper().split(",")[0]
            correct_option_text = ""
            for opt in options:
                if (opt.get("letter") or "").upper() == correct_letter:
                    correct_option_text = opt.get("text", "")
                    break
            options_text = [o.get("text", "") for o in options]

            explanation = study_index.get_explanation_from_study_text(
                question_text,
                options_text=options_text,
                module="LM1",
                correct_answer_text=correct_option_text or None,
            )
            if not explanation:
                explanation = "See LM1 Study Text for more detail."

            block_lines = [
                "",
                "--------------------------------------------------------------------------------",
                f"Question {i}",
                question_text,
                "",
            ]
            for opt in options:
                letter = (opt.get("letter") or "").upper()
                text = (opt.get("text") or "").strip()
                if letter and text:
                    block_lines.append(f"{letter}. {text}")
            block_lines.extend([
                "",
                f"Answer: {correct_letter or 'A'}",
                f"Explanation: {explanation}",
            ])
            blocks.append("\n".join(block_lines))

        header = f"""LM1 LONDON MARKET - {stem}
================================================================================
Explanations for questions from this past paper. Generated from LM1 Study Text.
================================================================================
"""
        content = header + "\n".join(blocks) + "\n\n"
        out_file.write_text(content, encoding="utf-8")
        print(f"  {out_file.name}: {len(blocks)} questions")
        total_written += len(blocks)

    print(f"Written {total_written} explanations across {len(by_source)} files in {past_papers_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
