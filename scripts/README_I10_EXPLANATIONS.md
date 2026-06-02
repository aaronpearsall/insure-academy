# I10 explanation files

## Files

One file per past paper in `modules/I10/past_papers/`:

- `I10 Exam - 2023 Explanations.txt` … `I10 Exam - 2026 Explanations.txt`

Format matches LM2 (question, options, answer, explanation per block).

## Verify

```bash
python3 scripts/verify_explanation_files.py --module I10
python3 scripts/check_question_spacing.py
```

## After parser or PDF changes

Re-sync question/option text from PDFs while keeping explanations:

```bash
python3 scripts/sync_explanation_qa.py --module I10
python3 scripts/verify_explanation_files.py --module I10
```

## Reload app cache

Use **Reload questions** in the app or restart the server after updating files.
