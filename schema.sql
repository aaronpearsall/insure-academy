-- Insure Academy — Postgres Schema
-- Run this in Supabase SQL editor (or psql) before first deployment

-- Users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    google_id TEXT UNIQUE,
    stripe_customer_id TEXT,
    subscription_status TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Questions (stable IDs based on content hash — never regenerated)
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,           -- sha256 hash of module+source_file+question_number+text
    module TEXT NOT NULL,          -- LM1, LM2, I10, M05
    source_file TEXT NOT NULL,     -- e.g. "LM1 Exam - 2026.pdf"
    question_number TEXT,
    question_text TEXT NOT NULL,
    options JSONB,                 -- [{"letter": "A", "text": "..."}, ...]
    correct_answer TEXT,           -- e.g. "A" or "A,C"
    is_multiple_choice BOOLEAN DEFAULT FALSE,
    is_curve_ball BOOLEAN DEFAULT FALSE,
    explanation TEXT,
    original_order INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questions_module ON questions(module);
CREATE INDEX IF NOT EXISTS idx_questions_source_file ON questions(source_file);

-- Per-user quiz results
CREATE TABLE IF NOT EXISTS quiz_results (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    module TEXT,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    time_taken INTEGER,            -- seconds
    questions JSONB,               -- snapshot of question texts at time of quiz
    answers JSONB,                 -- {question_id: selected_answer, ...}
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quiz_results_user_id ON quiz_results(user_id);
CREATE INDEX IF NOT EXISTS idx_quiz_results_created_at ON quiz_results(created_at);

-- Per-user wrong questions
CREATE TABLE IF NOT EXISTS user_wrong_questions (
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    question_id TEXT REFERENCES questions(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, question_id)
);

-- Per-user planner
CREATE TABLE IF NOT EXISTS planner_items (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    enrolled_units JSONB DEFAULT '[]',
    plan JSONB DEFAULT '[]',
    exemptions JSONB DEFAULT '{}',
    active_modules JSONB DEFAULT '[]',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_planner_user ON planner_items(user_id);
