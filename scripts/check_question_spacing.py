#!/usr/bin/env python3
"""
Audit all loaded questions and options for bad spacing/OCR patterns that
fix_display_spacing() should have corrected. Run from project root.

  python3 scripts/check_question_spacing.py

Exits 0 if no issues found, 1 if any text still has bad patterns.
"""

import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

# Use the same loader as the app (applies fix_display_spacing)
from app import QuestionParser

# Patterns that should NOT appear after normalisation (what we fix)
BAD_PATTERNS = [
    (r'\s+,', "space(s) before comma (e.g. '250 ,000')"),
    (r"\s+'", "space(s) before apostrophe (e.g. \"holder 's\")"),
    (r'policyh\s+older', "OCR split 'policyh older'"),
    (r'(\d)\s+\.\s+(?=\d)', "space around decimal point in number"),
]


def check_text(text, label):
    issues = []
    if not text or not isinstance(text, str):
        return issues
    for pattern, desc in BAD_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(desc)
    return issues


def main():
    print("Loading all questions via QuestionParser.load_questions_from_files()...")
    questions = QuestionParser.load_questions_from_files()
    print(f"Loaded {len(questions)} questions.\n")

    total_options = 0
    question_issues = []
    option_issues = []

    for q in questions:
        qid = q.get("id")
        src = q.get("source_file", "")
        qtext = q.get("question") or ""

        q_issues = check_text(qtext, "question")
        if q_issues:
            question_issues.append((qid, src, qtext[:100], q_issues))

        for opt in q.get("options", []):
            total_options += 1
            otext = opt.get("text") or ""
            o_issues = check_text(otext, "option")
            if o_issues:
                option_issues.append((qid, src, opt.get("letter"), otext[:80], o_issues))

    # Report
    print("Audit: bad spacing patterns that should have been fixed")
    print("=" * 60)
    print(f"Questions checked: {len(questions)}")
    print(f"Options checked:  {total_options}")
    print()

    if question_issues:
        print(f"QUESTIONS with remaining issues: {len(question_issues)}")
        for qid, src, snippet, issues in question_issues[:30]:
            print(f"  id={qid} source={src}")
            print(f"    issues: {issues}")
            print(f"    snippet: {snippet!r}...")
            print()
        if len(question_issues) > 30:
            print(f"  ... and {len(question_issues) - 30} more")
        print()
    else:
        print("Questions: no bad spacing patterns found.")

    if option_issues:
        print(f"OPTIONS with remaining issues: {len(option_issues)}")
        for qid, src, letter, snippet, issues in option_issues[:30]:
            print(f"  id={qid} {letter} source={src}")
            print(f"    issues: {issues}")
            print(f"    snippet: {snippet!r}...")
            print()
        if len(option_issues) > 30:
            print(f"  ... and {len(option_issues) - 30} more")
        print()
    else:
        print("Options: no bad spacing patterns found.")

    total_issues = len(question_issues) + len(option_issues)
    if total_issues:
        print("=" * 60)
        print(f"Total items with issues: {total_issues}")
        return 1
    print("All question and option text passed the spacing audit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
