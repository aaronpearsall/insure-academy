#!/usr/bin/env python3
"""
Sync question/option text in explanation files from freshly parsed PDFs.
Preserves Explanation: text for each question. Run after parser/OCR fixes.

  python3 scripts/sync_explanation_qa.py --module I10
"""

import argparse
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from app import QuestionParser, MODULES_DIR, StudyTextIndex


def parse_explanations(path):
    text = path.read_text(encoding='utf-8')
    sections = re.split(r'\n-{3,}|\n={3,}|(?=\nQuestion\s+\d+)', text, flags=re.MULTILINE)
    items = {}
    for section in sections:
        num_m = re.search(r'Question\s+(\d+)', section, re.IGNORECASE)
        exp_m = re.search(
            r'Explanation:\s*(.+?)(?=\n\s*(?:Question|Q\d*:|--|==|$|\Z))',
            section,
            re.DOTALL | re.IGNORECASE,
        )
        if num_m and exp_m:
            items[int(num_m.group(1))] = exp_m.group(1).strip()
    return items


def format_option(text):
    text = (text or '').strip()
    if text and not text.endswith('.') and not text.endswith('?'):
        text += '.'
    return text


def build_file(stem, module, qs, explanations):
    if module == 'I10':
        header = f"""I10 INSURANCE BROKING FUNDAMENTALS - {stem}
================================================================================
Explanations for questions from this past paper. I10 Insurance Broking Fundamentals.
================================================================================
"""
    else:
        header = f"""{module} - {stem}
================================================================================
Explanations for questions from this past paper.
================================================================================
"""
    blocks = []
    for i, q in enumerate(qs, start=1):
        explanation = explanations.get(i) or 'See I10 study materials for further detail.'
        explanation = StudyTextIndex.cleanup_explanation_text(
            StudyTextIndex.fix_ocr_errors(explanation)
        )
        lines = [
            '',
            '--------------------------------------------------------------------------------',
            f'Question {i}',
            q['question'].strip(),
            '',
        ]
        for opt in q.get('options', []):
            letter = (opt.get('letter') or '').upper()
            text = format_option(opt.get('text', ''))
            if letter and text:
                lines.append(f'{letter}. {text}')
        answer = (q.get('correct_answer') or 'A').strip().upper().split(',')[0]
        lines.extend([
            '',
            f'Answer: {answer}',
            f'Explanation: {explanation}',
        ])
        blocks.append('\n'.join(lines))
    return header + '\n'.join(blocks) + '\n\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', default='I10')
    args = parser.parse_args()
    module = args.module.upper()
    past_dir = MODULES_DIR / module / 'past_papers'

    all_qs = [q for q in QuestionParser.load_questions_from_files() if q.get('module') == module]
    by_stem = {}
    for q in all_qs:
        src = q.get('source_file') or ''
        if src.lower().endswith('.pdf'):
            by_stem.setdefault(Path(src).stem, []).append(q)

    for stem, qs in sorted(by_stem.items()):
        qs = sorted(qs, key=lambda x: int(x.get('question_number') or 0))
        exp_path = past_dir / f'{stem} Explanations.txt'
        if not exp_path.is_file():
            print(f'Skip {stem}: no explanation file')
            continue
        explanations = parse_explanations(exp_path)
        content = build_file(stem, module, qs, explanations)
        exp_path.write_text(content, encoding='utf-8')
        print(f'  synced {exp_path.name}: {len(qs)} questions')

    return 0


if __name__ == '__main__':
    sys.exit(main())
