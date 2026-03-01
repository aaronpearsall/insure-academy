# LM1 explanations file generator

## What it does

`generate_lm1_explanations.py` builds **one explanations file per past paper** in `modules/LM1/past_papers/` by:

1. Loading all LM1 questions from the app (past papers).
2. Grouping questions by source paper (e.g. "LM1 Exam - 2026.pdf").
3. For each paper, generating an explanation from the **LM1 Study Text** PDF for each of its 50 questions (with spelling/grammar cleanup).
4. Writing `<paper_stem> Explanations.txt` in the same folder as the paper (e.g. `LM1 Exam - 2026 Explanations.txt`).

The app loads explanation files from **past_papers** (and still from study_text for module-wide explanations). Each question is matched to the explanation for its own past paper first.

## How to run

From the **project root**:

```bash
python3 scripts/generate_lm1_explanations.py
```

Output: one file per paper in `modules/LM1/past_papers/`, e.g. `LM1 Exam - 2019 Explanations.txt` … `LM1 Exam - 2026 Explanations.txt`.

## Curation

- You can **edit any `<stem> Explanations.txt` file by hand** to correct or replace explanations for that paper.
- After adding new past papers or changing the study text, re-run the script to regenerate; re-apply manual edits as needed.
- To add more spelling/OCR fixes, extend `OCR_CORRECTIONS` in `app.py` and run the script again.
