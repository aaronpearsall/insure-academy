# InsureAcademy

A study app for practising multiple choice questions for insurance exams. Designed to support multiple modules (e.g. CII and similar qualifications). Add your own exam papers and study materials to practise any module.

**Disclaimer:** This app is not affiliated with or endorsed by the Chartered Insurance Institute (CII) or any other examining body. It is a personal study tool. You are responsible for ensuring your use of any materials complies with copyright and the terms of the materials you use.

## Setup

1. **Modules**: All content lives under **`modules/`**. Each module (e.g. LM1, M05, LM2, M92) has two folders:
   - **`modules/<name>/past_papers/`** – Exam papers (PDF, DOCX, TXT) for that module.
   - **`modules/<name>/study_text/`** – Study materials, curveball question files, and explanation files for that module.
   - See **`modules/README.md`** for the full layout. Use `.txt` for reliable parsing (see `EXAM_PAPER_TEXT_FORMAT.md`).
2. **Adding a module**: Create `modules/<NewName>/past_papers/` and `modules/<NewName>/study_text/`; the app picks it up automatically.
3. **Question explanations**: Put files with "explanation", "answer", or "concept" in the name inside the module’s `study_text/` folder. See `study_text/EXPLANATIONS_FORMAT.txt` for format (in the repo root or under a module).
4. **Install Dependencies**: Run `pip3 install -r requirements.txt`
5. **Set Login Credentials** (Optional): Set environment variables for custom credentials:
   - `export APP_USERNAME=your_username`
   - `export APP_PASSWORD=your_password`
   - `export SECRET_KEY=your_secret_key` (for session security)
6. **Run the App**: Run `python3 app.py` and open `http://localhost:5001` in your browser

## Login

**Default Credentials:**
- Username: `aaron`
- Password: `insagent2025`

**Important:** Change these credentials before hosting online by setting environment variables.

## Features

- Multiple choice questions from exam papers
- Instant feedback on answers
- Detailed explanations with study text references
- Marking system to track your progress
- Concept explanations and definitions
- Practice is per module; add papers in `modules/<name>/past_papers/` and `modules/<name>/study_text/` (e.g. LM1, M05, LM2, M92)

## File Structure

```
insurance-agent/
├── modules/                  # All content by module (no mixing)
│   ├── LM1/
│   │   ├── past_papers/      # LM1 exam papers (PDF, DOCX, TXT)
│   │   └── study_text/       # LM1 study text, curveballs, explanations
│   ├── M05/
│   │   ├── past_papers/
│   │   └── study_text/
│   ├── LM2/
│   │   ├── past_papers/
│   │   └── study_text/
│   ├── M92/
│   │   ├── past_papers/
│   │   └── study_text/
│   └── README.md
├── app.py
├── static/
├── templates/
├── requirements.txt
└── deploy.sh
```

## Updating the Live App

After making changes to your files:

1. **Option 1: Use the deploy script** (easiest)
   ```bash
   ./deploy.sh "Your commit message"
   ```

2. **Option 2: Manual git commands**
   ```bash
   git add .
   git commit -m "Your commit message"
   git push origin main
   ```

3. **Railway will automatically redeploy** when it detects the push to GitHub (usually takes 1-2 minutes)

**Note:** Make sure Railway is connected to your GitHub repository and has auto-deploy enabled (this is the default).
