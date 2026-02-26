# Modules (past papers + study text per module)

Each **module** has its own folder with two subfolders:

- **`past_papers/`** – Exam papers (PDF, DOCX, TXT) for this module. Questions are parsed from these files.
- **`study_text/`** – Study materials and curveball question files for this module.
  - PDF/DOCX/TXT here are used for feedback and concept search.
  - TXT files with **"curveball"** or **"curve_ball"** in the name are loaded as extra practice questions.
  - Files with **"explanation"**, **"answer"**, or **"concept"** in the name are used as pre-written explanations.

## Structure

```
modules/
├── LM1/
│   ├── past_papers/    ← LM1 exam papers
│   └── study_text/     ← LM1 study text, curveballs, explanations
├── M05/
│   ├── past_papers/
│   └── study_text/
├── LM2/
│   ├── past_papers/
│   └── study_text/
├── M92/
│   ├── past_papers/
│   └── study_text/
└── README.md           ← this file
```

## Adding a new module

1. Create a folder with the module name (e.g. `modules/LM3/`).
2. Inside it, create two folders: `past_papers/` and `study_text/`.
3. Put your exam papers in `past_papers/` and study/curveball/explanation files in `study_text/`.
4. The app will pick up the new module automatically (no code changes).

Practice is always **per module**; questions are never mixed across modules.
