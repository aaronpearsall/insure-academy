#!/usr/bin/env python3
"""
Verify past-paper explanation files match parsed questions (count, text, answers).

  python3 scripts/verify_explanation_files.py [--module I10]

Exits 0 if all checks pass, 1 otherwise.
"""

import argparse
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from app import QuestionParser, QuestionExplanations, MODULES_DIR, StudyTextIndex

BAD_SPELLING_PATTERNS = [
    (r'\b(teh|hte|adn|waht|insurnace|brokr|clinet)\b', 'common typo'),
    (r'\s+,', 'space before comma'),
    (r"\s+'s\b", "space before apostrophe-s"),
    (r'\b(\w+)\s+\1\b', 'repeated word'),
]


def normalize(s):
    return QuestionExplanations().normalize_text(s or '')


def parse_explanation_file(path, module):
    """Return list of {num, question, answer, explanation, options}."""
    text = path.read_text(encoding='utf-8')
    sections = re.split(r'\n-{3,}|\n={3,}|(?=\nQuestion\s+\d+)', text, flags=re.MULTILINE)
    items = []
    for section in sections:
        if not section.strip():
            continue
        num_m = re.search(r'Question\s+(\d+)', section, re.IGNORECASE)
        if not num_m:
            continue
        num = int(num_m.group(1))
        q_m = re.search(
            r'Question\s+\d+\s*\n(.+?)(?=\n\s*[A-D]\.|\nAnswer:)',
            section,
            re.DOTALL | re.IGNORECASE,
        )
        if not q_m:
            continue
        question = re.sub(r'^\s*[A-D]\.\s*.+$', '', q_m.group(1), flags=re.MULTILINE)
        question = re.sub(r'\s+', ' ', question).strip()
        ans_m = re.search(r'Answer:\s*([A-E](?:,\s*[A-E])*)', section, re.IGNORECASE)
        exp_m = re.search(
            r'Explanation:\s*(.+?)(?=\n\s*(?:Question|Q\d*:|--|==|$|\Z))',
            section,
            re.DOTALL | re.IGNORECASE,
        )
        answer = ans_m.group(1).strip().upper() if ans_m else ''
        explanation = exp_m.group(1).strip() if exp_m else ''
        if not question or not explanation:
            continue
        items.append({
            'num': num,
            'question': question,
            'answer': answer,
            'explanation': explanation,
        })
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', default='I10', help='Module code (default: I10)')
    args = parser.parse_args()
    module = args.module.upper()
    past_dir = MODULES_DIR / module / 'past_papers'
    if not past_dir.is_dir():
        print(f'Module folder not found: {past_dir}')
        return 1

    all_qs = [q for q in QuestionParser.load_questions_from_files() if q.get('module') == module]
    by_stem = {}
    for q in all_qs:
        src = q.get('source_file') or ''
        if not src.lower().endswith('.pdf'):
            continue
        stem = Path(src).stem
        by_stem.setdefault(stem, []).append(q)

    errors = []
    for stem in sorted(by_stem):
        exp_path = past_dir / f'{stem} Explanations.txt'
        qs = sorted(by_stem[stem], key=lambda x: int(x.get('question_number') or x.get('original_order') or 0))
        if not exp_path.is_file():
            errors.append(f'{stem}: missing explanation file')
            continue
        exp_items = parse_explanation_file(exp_path, module)
        if len(exp_items) != len(qs):
            errors.append(f'{stem}: count mismatch — {len(qs)} questions, {len(exp_items)} explanations')
        for i, (q, exp) in enumerate(zip(qs, exp_items), start=1):
            q_num = q.get('question_number') or str(i)
            correct = (q.get('correct_answer') or '').strip().upper()
            if exp['answer'] != correct:
                errors.append(
                    f'{stem} Q{q_num}: answer mismatch — paper={correct}, explanations={exp["answer"]}'
                )
            if normalize(q.get('question', '')) != normalize(exp['question']):
                errors.append(
                    f'{stem} Q{q_num}: question text mismatch'
                )
            for pattern, desc in BAD_SPELLING_PATTERNS:
                for field, label in [(exp['explanation'], 'explanation'), (exp['question'], 'question')]:
                    if re.search(pattern, field, re.IGNORECASE):
                        errors.append(f'{stem} Q{q_num}: {label} has {desc}')
            cleaned = StudyTextIndex.cleanup_explanation_text(exp['explanation'])
            if len(cleaned) < 20:
                errors.append(f'{stem} Q{q_num}: explanation too short')
        # sequential question numbers in file
        nums = [e['num'] for e in exp_items]
        if nums != list(range(1, len(nums) + 1)):
            errors.append(f'{stem}: explanation question numbers not sequential 1..{len(nums)}')

    print(f'Verified {module}: {len(by_stem)} papers, {len(all_qs)} questions')
    if errors:
        print(f'\n{len(errors)} issue(s):')
        for e in errors[:50]:
            print(f'  - {e}')
        if len(errors) > 50:
            print(f'  ... and {len(errors) - 50} more')
        return 1
    print('All explanation files match parsed questions.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
