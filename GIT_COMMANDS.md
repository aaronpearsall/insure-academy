# Quick Git Commands Guide

## Basic Workflow

### 1. Check what files have changed
```bash
cd /Users/aaronpearsall/m05
git status
```

### 2. Add all changes
```bash
git add .
```

Or add specific files:
```bash
git add app.py
git add static/quiz.js
```

### 3. Commit with a message
```bash
git commit -m "Your commit message describing the changes"
```

### 4. Push to GitHub
```bash
git push origin main
```

## Complete Example

```bash
cd /Users/aaronpearsall/m05
git add .
git commit -m "Fixed scoring bug and question parsing"
git push origin main
```

## If You Get Authentication Errors

If `git push` asks for credentials, you'll need to use your Personal Access Token:

1. **Username:** `aaronpearsall`
2. **Password:** Use your GitHub Personal Access Token (not your GitHub password)

If you don't have a token, create one at: https://github.com/settings/tokens

## Quick One-Liner

You can also do it all in one command:

```bash
cd /Users/aaronpearsall/m05 && git add . && git commit -m "Your message" && git push origin main
```

## Useful Commands

**See what's changed:**
```bash
git status
git diff
```

**See commit history:**
```bash
git log --oneline -10
```

**Undo last commit (but keep changes):**
```bash
git reset --soft HEAD~1
```

**See what branch you're on:**
```bash
git branch
```

## Note

- Railway will automatically redeploy when you push to GitHub (if auto-deploy is enabled)
- The `questions.json` file is in `.gitignore`, so it won't be pushed (it regenerates automatically)
- Always write clear commit messages so you can track what changed

