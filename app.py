from flask import Flask, render_template, jsonify, request, session, redirect, url_for
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import re
import secrets
import sqlite3
from pathlib import Path
from functools import wraps
from urllib.parse import urlencode
try:
    from pypdf import PdfReader
except ImportError:
    import PyPDF2
    PdfReader = PyPDF2.PdfReader
from docx import Document

app = Flask(__name__)
CORS(app)

# Set secret key for sessions (use environment variable or generate one)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Default credentials (should be changed via environment variables in production)
DEFAULT_USERNAME = os.environ.get('APP_USERNAME', 'aaron')
# Use pbkdf2:sha256 method for compatibility
_default_password = os.environ.get('APP_PASSWORD', 'insagent2025')
DEFAULT_PASSWORD_HASH = os.environ.get('APP_PASSWORD_HASH', generate_password_hash(_default_password, method='pbkdf2:sha256'))

# Auth & subscription config
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///insure_academy.db')
DATABASE_PATH = _db_url.replace('sqlite:///', '').split('?')[0]
if not DATABASE_PATH or DATABASE_PATH == _db_url:
    DATABASE_PATH = str(Path(__file__).parent / 'insure_academy.db')
elif not os.path.isabs(DATABASE_PATH):
    DATABASE_PATH = str(Path(__file__).parent / DATABASE_PATH)
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID', '')  # monthly subscription price
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

# OAuth (Google) - register once
try:
    from authlib.integrations.flask_client import OAuth
    _oauth = OAuth(app)
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        _oauth.register(
            name='google',
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'}
        )
    oauth = _oauth
except ImportError:
    oauth = None

# Directories: one folder per module, each with past_papers/ and study_text/
MODULES_DIR = Path("modules")
QUESTIONS_FILE = Path("questions.json")
PLANNER_FILE = Path("planner.json")
WRONG_QUESTIONS_FILE = Path("wrong_questions.json")

# Only these modules are shown and loaded (no "All Modules"; practice is per module).
# LM1 and LM2 are London Market units; M05 is the existing diploma unit.
ALLOWED_MODULES = ["LM1", "LM2", "M05"]


def get_module_names():
    """Return allowed modules that exist under modules/ (LM1, LM2, M05)."""
    if not MODULES_DIR.exists():
        return []
    return [m for m in ALLOWED_MODULES if (MODULES_DIR / m).is_dir()]


def get_db():
    """Get SQLite connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create users table if not exists."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            google_id TEXT UNIQUE,
            stripe_customer_id TEXT,
            subscription_status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def get_user_by_id(user_id):
    """Get user by id."""
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_email(email):
    """Get user by email."""
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_google_id(google_id):
    """Get user by Google ID."""
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE google_id = ?", (google_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(email, password_hash=None, google_id=None):
    """Create a new user. Returns user dict or None if email exists."""
    email = email.lower().strip()
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (email, password_hash, google_id) VALUES (?, ?, ?)",
            (email, password_hash, google_id)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = last_insert_rowid()").fetchone()
        return dict(row) if row else None
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def update_user_subscription(user_id, status, stripe_customer_id=None):
    """Update user subscription status."""
    conn = get_db()
    if stripe_customer_id:
        conn.execute(
            "UPDATE users SET subscription_status = ?, stripe_customer_id = ? WHERE id = ?",
            (status, stripe_customer_id, user_id)
        )
    else:
        conn.execute("UPDATE users SET subscription_status = ? WHERE id = ?", (status, user_id))
    conn.commit()
    conn.close()


def update_user_password(user_id, password_hash):
    """Update user password."""
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
    conn.commit()
    conn.close()


def user_has_active_subscription(user):
    """Check if user has active subscription. Legacy users (no user dict) are treated as subscribed."""
    if not user:
        return True  # legacy
    status = (user.get('subscription_status') or '').strip().lower()
    return status in ('active', 'trialing')


class QuestionParser:
    """Parse questions from exam papers"""
    
    @staticmethod
    def extract_text_from_pdf(pdf_path):
        """Extract text from PDF file"""
        text = ""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
        except Exception as e:
            print(f"Error reading PDF {pdf_path}: {e}")
        return text
    
    @staticmethod
    def extract_text_from_docx(docx_path):
        """Extract text from DOCX file"""
        text = ""
        try:
            doc = Document(docx_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
        except Exception as e:
            print(f"Error reading DOCX {docx_path}: {e}")
        return text
    
    @staticmethod
    def parse_questions(text):
        """Parse multiple choice questions from text (works for both PDF and text files)"""
        questions = []

        # Normalize PDF layout: "PageNum QuestionNum. " or "PageNum QuestionNum.Letter" (e.g. " 18 42. Which" or " 14 25.What")
        # -> "\n42. Which" / "\n25. What" so question numbers at line start are detected.
        def _norm_page_question(m):
            page_num, q_num = m.group(1), m.group(2)
            if 1 <= int(page_num) <= 99 and 1 <= int(q_num) <= 99:
                return '\n' + q_num + m.group(3) + ' '
            return m.group(0)
        text = re.sub(r'(?<=\s)(\d{1,2})\s+(\d{1,2})([\.\)])\s', _norm_page_question, text)
        # 2024-style: no space after period (e.g. "14 25.What")
        text = re.sub(r'(?<=\s)(\d{1,2})\s+(\d{1,2})([\.\)])(?=[A-Z])', _norm_page_question, text)
        # No space after question number at line start (e.g. "\n26.Why") -> "\n26. Why" so block split matches
        def _norm_line_start_no_space(m):
            q_num = m.group(1)
            if 1 <= int(q_num) <= 99:
                return m.group(1) + m.group(2) + ' '  # insert space before the capital letter (lookahead)
            return m.group(0)
        text = re.sub(r'(?<=\n)(\d{1,2})([\.\)])(?=[A-Z])', _norm_line_start_no_space, text)
        
        # Pattern to match questions starting with numbers (1., 2., etc.)
        # Format: "1. Question text\nA. Option A\nB. Option B\nC. Option C\nD. Option D"
        # Only match question numbers at the start of a line (after newline or start of text)
        # This prevents matching numbers in the middle of text (e.g., "E05" or "contracts. 9")
        # For text files, this is more reliable since there are no page breaks/headers
        question_blocks = re.split(r'(?=^(?:\d+[\.\)]\s)|(?<=\n)(?:\d+[\.\)]\s))', text, flags=re.MULTILINE)
        
        for block in question_blocks:
            # Match question number and content - must start at beginning of block
            # Stop at the next question number OR answer key section
            match = re.match(r'^(\d+)[\.\)]\s*(.+?)(?=\n\d+[\.\)]\s|\n\s*ANSWERS?|$)', block.strip(), re.DOTALL | re.IGNORECASE)
            if not match:
                continue
                
            question_num = match.group(1)
            question_content = match.group(2).strip()
            
            # Skip if this doesn't look like a real question (no options found)
            # Real questions should have at least one option (A., B., etc.)
            # Allow A.£ A.123 A.Word etc. (currency, digits, letters after the period)
            if not re.search(r'\n[A-E][\.\)](?:\s|(?=[A-Z0-9£$%\-]))', question_content, re.IGNORECASE):
                continue
            
            # IMPORTANT: Stop extracting content when we hit:
            # 1. The next question number
            # 2. The answer key section (ANSWERS, Answer Key, etc.)
            next_question_match = re.search(r'\n(\d+)[\.\)]\s', question_content)
            answer_key_match = re.search(r'\n\s*(ANSWERS?|Answer\s+Key|Specimen\s+Examination\s+Answers)', question_content, re.IGNORECASE)
            
            if next_question_match and answer_key_match:
                # Stop at whichever comes first
                stop_pos = min(next_question_match.start(), answer_key_match.start())
                question_content = question_content[:stop_pos].strip()
            elif next_question_match:
                # Truncate at the next question
                question_content = question_content[:next_question_match.start()].strip()
            elif answer_key_match:
                # Truncate at the answer key
                question_content = question_content[:answer_key_match.start()].strip()
            
            # Extract options - look for lines starting with A., B., C., D., E.
            # CRITICAL: Stop if we encounter a new question number (prevents merging questions)
            options = []
            lines = question_content.split('\n')
            current_option = None
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                # CRITICAL CHECK: If we see a new question number, STOP immediately
                # This prevents one question from capturing the next question's options
                if re.match(r'^\d+[\.\)]\s', line):
                    # This is a new question - stop processing
                    break
                
                # Check if this line starts a new option
                option_match = re.match(r'^([A-E])[\.\)]\s*(.+)$', line, re.IGNORECASE)
                if option_match:
                    # Save previous option if exists
                    if current_option and current_option['text']:
                        options.append(current_option)
                    
                    # Start new option
                    option_letter = option_match.group(1).upper()
                    option_text = option_match.group(2).strip()
                    current_option = {
                        'letter': option_letter,
                        'text': option_text
                    }
                elif current_option:
                    # Continue current option (multi-line option text)
                    # Only append if line doesn't look like a new question or option
                    # Also skip common PDF artifacts (headers, footers, page numbers)
                    if (not re.match(r'^\d+[\.\)]', line) and 
                        not re.match(r'^[A-E][\.\)]', line) and
                        not re.search(r'Examination\s+Guide\s+E\d+', line, re.IGNORECASE) and
                        not re.search(r'\d{4}/\d{4}\s+\d+$', line) and
                        not re.search(r'^Page\s+\d+', line, re.IGNORECASE) and
                        len(line.strip()) > 0):
                        current_option['text'] += ' ' + line
            
            # Don't forget the last option
            if current_option and current_option['text']:
                options.append(current_option)
            
            # Clean up option text
            for opt in options:
                opt['text'] = re.sub(r'\s+', ' ', opt['text']).strip()
                # Remove common PDF artifacts (page numbers, headers, footers)
                # Remove patterns like "Examination Guide E05 Examination Guide 2025/2026 13"
                opt['text'] = re.sub(r'\s*Examination\s+Guide\s+E\d+.*?$', '', opt['text'], flags=re.IGNORECASE)
                opt['text'] = re.sub(r'\s*Examination\s+Guide.*?$', '', opt['text'], flags=re.IGNORECASE)
                opt['text'] = re.sub(r'\s*\d{4}/\d{4}\s+\d+.*?$', '', opt['text'])  # Remove "2025/2026 13" patterns
                opt['text'] = re.sub(r'\s*Page\s+\d+.*?$', '', opt['text'], flags=re.IGNORECASE)
                # Remove trailing standalone numbers that are likely page numbers (but preserve if part of sentence)
                # Only remove if it's a standalone number at the end (not part of text like "2021" in a sentence)
                opt['text'] = re.sub(r'\s+\d{1,2}\s*$', '', opt['text'])  # Remove trailing 1-2 digit numbers (likely page refs)
                # Remove common footer/header patterns
                opt['text'] = re.sub(r'^\d+/\d+\s*', '', opt['text'])  # Remove page numbers like "1/15"
                # Remove any remaining "Examination Guide" text
                opt['text'] = re.sub(r'\s*Examination\s+Guide.*', '', opt['text'], flags=re.IGNORECASE)
                opt['text'] = re.sub(r'\s+', ' ', opt['text']).strip()
                # Preserve trailing periods if they're part of the option text (don't remove them)
                # Only remove if it's clearly an artifact (multiple periods or periods with spaces)
                opt['text'] = re.sub(r'\.{2,}', '.', opt['text'])  # Replace multiple periods with single
                opt['text'] = re.sub(r'\s+\.\s*$', '.', opt['text'])  # Fix "text ." to "text."
            
            # Extract question text (everything before the first option)
            clean_question = question_content
            if options:
                # Find where first option starts
                first_option_pattern = rf'^{re.escape(options[0]["letter"])}[\.\)]'
                first_option_match = re.search(first_option_pattern, question_content, re.MULTILINE | re.IGNORECASE)
                if first_option_match:
                    clean_question = question_content[:first_option_match.start()].strip()
            
            # Clean up question text
            clean_question = re.sub(r'\s+', ' ', clean_question).strip()
            
            # Format formulas more clearly - detect common insurance formula patterns
            # Pattern: "Sum insured x amount of loss / Value at risk" or similar
            formula_patterns = [
                (r'Sum insured at the time of loss x amount of loss\s+Value at risk at the time of loss\s+Which',
                 r'Sum insured at the time of loss × amount of loss\n────────────────────────────────────\nValue at risk at the time of loss\n\nWhich'),
                (r'Sum insured.*?x.*?amount of loss\s+Value at risk.*?Which',
                 r'Sum insured at the time of loss × amount of loss\n────────────────────────────────────\nValue at risk at the time of loss\n\nWhich'),
            ]
            
            for pattern, replacement in formula_patterns:
                if re.search(pattern, clean_question, re.IGNORECASE):
                    clean_question = re.sub(pattern, replacement, clean_question, flags=re.IGNORECASE)
                    break
            
            # Try to find correct answer in answer key section (look for answer patterns)
            correct_answer = None
            # Look for answer patterns like "1. C" or "1 C" or "Answer: 1. C"
            answer_patterns = [
                rf'(?:^|\n){re.escape(question_num)}[\.\)\s]*[:\s]*([A-E])(?:\s|$)',
                rf'Question\s+{re.escape(question_num)}[:\s]+([A-E])',
            ]
            for pattern in answer_patterns:
                answer_match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
                if answer_match:
                    correct_answer = answer_match.group(1).upper()
                    break
            
            # Only add if we have a valid question with at least 2 options
            if clean_question and len(options) >= 2 and len(clean_question) > 10:
                questions.append({
                    'id': None,  # Will be assigned in load_questions_from_files
                    'question': clean_question,
                    'options': options,
                    'correct_answer': correct_answer or options[0]['letter'],  # Default to first if not found
                    'is_multiple_choice': False,  # Will be set later based on answer key
                    'explanation': '',
                    'source_file': 'exam_paper',
                    'question_number': question_num
                })
        
        return questions
    
    @staticmethod
    def extract_answer_key(text):
        """Extract answer key and learning objectives from text (look for 'Specimen Examination Answers' section)"""
        answer_key = {}
        learning_objectives = {}
        
        # Look for answer key section - try multiple patterns
        answer_section_patterns = [
            r'Specimen Examination Answers.*?(?=\n\n\n|\Z)',
            r'ANSWERS?.*?(?=\n\n\n|\Z)',
            r'Answer\s+Key.*?(?=\n\n\n|\Z)',
            r'ANSWERS?\s+AND\s+LEARNING\s+OUTCOMES.*?(?=\n\n\n|\Z)',
        ]
        
        answer_text = None
        for pattern in answer_section_patterns:
            answer_section = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if answer_section:
                answer_text = answer_section.group(0)
                break
        
        if answer_text:
            # Pattern 1: "1 C 1.4" or "41 A,B,C 1.2" - captures question num, answer, and learning objective
            answer_pattern1 = r'(\d+)\s+([A-E](?:,\s*[A-E])*)\s+(\d+\.\d+)'
            matches = re.finditer(answer_pattern1, answer_text)
            
            for match in matches:
                q_num = match.group(1)
                answer = match.group(2).strip().upper()
                learning_obj = match.group(3).strip()
                
                # Store full answer (may contain multiple answers like "A,B,C")
                answer_key[q_num] = answer
                
                # Store learning objective (extract main number, e.g., "1.4" -> "1")
                learning_obj_main = learning_obj.split('.')[0]
                learning_objectives[q_num] = learning_obj_main
            
            # Pattern 2: If pattern 1 didn't find many, try simpler pattern "1 C" or "1. C"
            if len(answer_key) < 10:
                answer_pattern2 = r'(?:^|\n)(\d+)[\.\)]?\s+([A-E](?:,\s*[A-E])*)(?:\s+(\d+\.\d+))?(?=\s|$|\n)'
                matches2 = re.finditer(answer_pattern2, answer_text, re.MULTILINE)
                for match in matches2:
                    q_num = match.group(1)
                    answer = match.group(2).strip().upper()
                    learning_obj = match.group(3) if match.group(3) else None
                    
                    # Only add if not already found (pattern 1 takes precedence)
                    if q_num not in answer_key:
                        answer_key[q_num] = answer
                        if learning_obj:
                            learning_obj_main = learning_obj.split('.')[0]
                            learning_objectives[q_num] = learning_obj_main
        
        return answer_key, learning_objectives
    
    @staticmethod
    def parse_questions_from_explanations_format(text):
        """Parse questions from explanations file format (Question X format)"""
        questions = []
        
        # Split by question markers - look for "Question X" or separator lines
        sections = re.split(r'\n-{3,}|\n={3,}|(?=\nQuestion\s+\d+)', text, flags=re.MULTILINE)
        
        for section in sections:
            if not section.strip():
                continue
            
            # Match "Question X [Learning Outcome X.X]" format and extract learning objective
            question_header_match = re.search(r'Question\s+(\d+)\s*(?:\[Learning\s+Outcome\s+(\d+\.\d+)\])?\s*\n(.+?)(?=\nAnswer:|\n\s*Question\s+\d+|\n-{3,}|\n={3,}|$)', section, re.DOTALL | re.IGNORECASE)
            if not question_header_match:
                continue
            
            question_num = question_header_match.group(1)
            learning_obj_full = question_header_match.group(2)  # e.g., "9.5"
            question_content = question_header_match.group(3).strip()
            
            # Skip if no options found
            if not re.search(r'\n[A-E][\.\)]\s', question_content, re.IGNORECASE):
                continue
            
            # Extract question text (everything before first option)
            clean_question = question_content
            first_option_match = re.search(r'\n([A-E])[\.\)]\s', question_content, re.IGNORECASE)
            if first_option_match:
                clean_question = question_content[:first_option_match.start()].strip()
            
            # Extract options
            options = []
            lines = question_content.split('\n')
            current_option = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check if this line starts a new option
                option_match = re.match(r'^([A-E])[\.\)]\s*(.+)$', line, re.IGNORECASE)
                if option_match:
                    if current_option and current_option['text']:
                        options.append(current_option)
                    option_letter = option_match.group(1).upper()
                    option_text = option_match.group(2).strip()
                    current_option = {
                        'letter': option_letter,
                        'text': option_text
                    }
                elif current_option:
                    # Continue current option (multi-line option text)
                    if not re.match(r'^\d+[\.\)]', line) and not re.match(r'^[A-E][\.\)]', line):
                        current_option['text'] += ' ' + line
            
            # Don't forget the last option
            if current_option and current_option['text']:
                options.append(current_option)
            
            # Clean up option text
            for opt in options:
                opt['text'] = re.sub(r'\s+', ' ', opt['text']).strip()
            
            # Extract answer from the section
            answer_match = re.search(r'Answer:\s*([A-E](?:,\s*[A-E])*)', section, re.IGNORECASE)
            correct_answer = answer_match.group(1).strip().upper() if answer_match else None
            
            # Only add if we have a valid question with at least 2 options
            if clean_question and len(options) >= 2 and len(clean_question) > 10:
                question_data = {
                    'id': None,  # Will be assigned in load_questions_from_files
                    'question': clean_question,
                    'options': options,
                    'correct_answer': correct_answer or options[0]['letter'],
                    'is_multiple_choice': ',' in (correct_answer or '') if correct_answer else False,
                    'explanation': '',
                    'source_file': 'curveball_questions',
                    'question_number': question_num
                }
                
                # Add learning objective if found
                if learning_obj_full:
                    question_data['learning_objective'] = learning_obj_full.split('.')[0]  # Main number only
                
                questions.append(question_data)
        
        return questions
    
    @staticmethod
    def fix_display_spacing(text):
        """Fix incorrect spaces and common OCR splits in question/option text."""
        if not text or not isinstance(text, str):
            return text or ''
        # Remove space(s) immediately before comma (e.g. '£250 ,000' -> '£250,000', 'Terry ,' -> 'Terry,')
        text = re.sub(r'\s+,', ',', text)
        # Remove space(s) immediately after comma when followed by digit (e.g. '£33, 000' -> '£33,000')
        text = re.sub(r',\s+(?=\d)', ',', text)
        # Remove space(s) immediately before apostrophe (straight, curly U+2019, or backtick) for possessives
        text = re.sub(r"\s+[''\u2019`](?=[sS]|\s|$)", "'", text)
        # Remove space(s) immediately before full stop when it looks like a decimal (e.g. "1 . 5" -> "1.5")
        text = re.sub(r'(\d)\s+\.\s+(?=\d)', r'\1.', text)
        # Fix common OCR split-words (word broken with stray space)
        text = re.sub(r'policyh\s+older', 'policyholder', text, flags=re.IGNORECASE)
        # Normalise multiple spaces to single
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    @staticmethod
    def load_questions_from_files():
        """Load questions from modules/<name>/past_papers and modules/<name>/study_text (curveballs)."""
        all_questions = []
        global_id_counter = 1
        global_explanations = QuestionExplanations()

        for module in get_module_names():
            past_papers_dir = MODULES_DIR / module / "past_papers"
            if not past_papers_dir.is_dir():
                continue
            for file_path in sorted(past_papers_dir.iterdir()):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() == '.pdf':
                    text = QuestionParser.extract_text_from_pdf(file_path)
                elif file_path.suffix.lower() == '.docx':
                    text = QuestionParser.extract_text_from_docx(file_path)
                elif file_path.suffix.lower() in ['.txt', '.rtf']:
                    text = file_path.read_text(encoding='utf-8')
                else:
                    continue

                answer_key, learning_objectives = QuestionParser.extract_answer_key(text)
                questions = QuestionParser.parse_questions(text)

                for question in questions:
                    question['question'] = QuestionParser.fix_display_spacing(question['question'])
                    for opt in question.get('options', []):
                        opt['text'] = QuestionParser.fix_display_spacing(opt.get('text', ''))
                    q_num = question.get('question_number', '')
                    q_text = question['question'].strip()
                    exp_answer = global_explanations.get_answer(q_text, module, source_file=file_path.name)
                    if exp_answer:
                        question['correct_answer'] = exp_answer
                        question['is_multiple_choice'] = ',' in exp_answer
                    elif q_num in answer_key:
                        question['correct_answer'] = answer_key[q_num].upper()
                        question['is_multiple_choice'] = ',' in answer_key[q_num]
                    question['is_curve_ball'] = global_explanations.get_curve_ball(q_text, module, source_file=file_path.name)
                    if q_num in learning_objectives:
                        question['learning_objective'] = learning_objectives[q_num]
                    question['source_file'] = file_path.name
                    question['module'] = module
                    question['original_order'] = int(q_num) if q_num.isdigit() else 999999
                    question['id'] = global_id_counter
                    global_id_counter += 1
                all_questions.extend(questions)

            # Curveballs from modules/<name>/study_text/
            study_dir = MODULES_DIR / module / "study_text"
            if not study_dir.is_dir():
                continue
            for file_path in sorted(study_dir.iterdir()):
                if not file_path.is_file() or file_path.suffix.lower() != '.txt':
                    continue
                filename_lower = file_path.name.lower()
                if 'curveball' not in filename_lower and 'curve_ball' not in filename_lower:
                    continue
                try:
                    text = file_path.read_text(encoding='utf-8')
                    questions = QuestionParser.parse_questions_from_explanations_format(text)
                    for question in questions:
                        question['question'] = QuestionParser.fix_display_spacing(question['question'])
                        for opt in question.get('options', []):
                            opt['text'] = QuestionParser.fix_display_spacing(opt.get('text', ''))
                        q_text = question['question'].strip()
                        exp_answer = global_explanations.get_answer(q_text, module, source_file=file_path.name)
                        if exp_answer and not question.get('correct_answer'):
                            question['correct_answer'] = exp_answer
                            question['is_multiple_choice'] = ',' in exp_answer
                        elif question.get('correct_answer'):
                            question['is_multiple_choice'] = ',' in question['correct_answer']
                        question['is_curve_ball'] = True
                        question['source_file'] = file_path.name
                        question['module'] = module
                        question['original_order'] = int(question.get('question_number', '0')) if (question.get('question_number') or '0').isdigit() else 999999
                        question['id'] = global_id_counter
                        global_id_counter += 1
                    all_questions.extend(questions)
                except Exception as e:
                    print(f"Error loading curveball from {file_path}: {e}")

        return all_questions

class QuestionExplanations:
    """Load and match pre-written explanations for questions, scoped by module."""
    
    def __init__(self):
        # Maps (module, normalized_question_text) -> {explanation, answer, is_curve_ball}
        self.explanations = {}
        self.load_explanations()
    
    def normalize_text(self, text):
        """Normalize text for matching (lowercase, remove extra spaces, normalize dashes)"""
        if not text:
            return ""
        # Remove extra whitespace, lowercase, remove punctuation for matching
        normalized = re.sub(r'\s+', ' ', text.lower().strip())
        # Normalize different dash/hyphen types to standard hyphen
        normalized = normalized.replace('‐', '-').replace('–', '-').replace('—', '-')
        return normalized
    
    def load_explanations(self):
        """Load explanations from each module's study_text and past_papers. Past paper explanations go in past_papers/ and correspond to each paper (e.g. LM1 Exam - 2026 Explanations.txt)."""
        def collect_study_files(dir_path):
            files = []
            if not dir_path.exists():
                return files
            for file_path in dir_path.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in ['.txt', '.md']:
                    fn = file_path.name.lower()
                    if 'explanation' in fn or 'answer' in fn or 'concept' in fn:
                        files.append(file_path)
            return files

        for module in get_module_names():
            # Study text: explanations not tied to a specific paper (source_file_key '')
            study_dir = MODULES_DIR / module / "study_text"
            for file_path in collect_study_files(study_dir):
                try:
                    text = file_path.read_text(encoding='utf-8')
                    self.parse_explanations(text, module, source_file_key='')
                except Exception as e:
                    print(f"Error loading explanations from {file_path}: {e}")
            # Past papers: one explanations file per paper (e.g. "LM1 Exam - 2026 Explanations.txt" -> paper "LM1 Exam - 2026.pdf")
            past_dir = MODULES_DIR / module / "past_papers"
            if past_dir.exists():
                for file_path in past_dir.iterdir():
                    if not file_path.is_file() or file_path.suffix.lower() != '.txt':
                        continue
                    if 'explanation' not in file_path.name.lower():
                        continue
                    try:
                        text = file_path.read_text(encoding='utf-8')
                        # Match corresponding paper by stem: "LM1 Exam - 2026 Explanations" -> "LM1 Exam - 2026"
                        source_file_key = re.sub(r'\s*Explanations?\s*$', '', file_path.stem, flags=re.IGNORECASE)
                        self.parse_explanations(text, module, source_file_key=source_file_key)
                    except Exception as e:
                        print(f"Error loading explanations from {file_path}: {e}")
    
    def parse_explanations(self, text, module, source_file_key=''):
        """Parse explanations from text file and store under the given module.
        
        Supports multiple formats:
        1. Question [number] [Learning Outcome X.X]
           [question text]
           A. [option]
           B. [option]
           Answer: [answer]
           Explanation: [explanation]
        
        2. Question: [question text]
           Answer: [answer]
           Explanation: [explanation]
        
        3. Q[number]: [question text]
           A: [answer]
           E: [explanation]
        
        4. [question text]
           Answer: [answer]
           Explanation: [explanation]
        """
        # Split by question markers (Question X, QX, or separator lines)
        # Look for patterns like "Question X" or "Q X" or separator lines
        sections = re.split(r'\n-{3,}|\n={3,}|(?=\nQuestion\s+\d+)', text, flags=re.MULTILINE)
        
        for section in sections:
            if not section.strip():
                continue
            
            # Pattern 1: "Question X [Learning Outcome X.X]" format
            question_header_match = re.search(r'Question\s+(\d+)\s*\[.*?\]\s*\n(.+?)(?=\nAnswer:|\n[A-D]\.|$)', section, re.DOTALL | re.IGNORECASE)
            if question_header_match:
                question_text = question_header_match.group(2).strip()
                # Remove options (lines starting with A., B., C., D.)
                question_text = re.sub(r'^\s*[A-D]\.\s*.+$', '', question_text, flags=re.MULTILINE)
                question_text = re.sub(r'\s+', ' ', question_text).strip()
            else:
                # Pattern 2: "Question: ..." or just question text
                question_match = re.search(r'(?:Question\s*\d*:|Q\d*:)\s*(.+?)(?:\n|Answer:|$)', section, re.DOTALL | re.IGNORECASE)
                if not question_match:
                    # Pattern 3: Question text at start (before options)
                    # Find text before first option (A., B., C., D.)
                    question_match = re.search(r'^(.+?)(?=\n\s*[A-D]\.|\n\s*Answer:)', section, re.DOTALL | re.IGNORECASE)
                    if question_match:
                        question_text = question_match.group(1).strip()
                        # Remove "Question X" prefix if present
                        question_text = re.sub(r'^Question\s+\d+.*?\n', '', question_text, flags=re.IGNORECASE)
                        question_text = re.sub(r'\[.*?\]', '', question_text)  # Remove [Learning Outcome X.X]
                        question_text = re.sub(r'\s+', ' ', question_text).strip()
                    else:
                        continue
                else:
                    question_text = question_match.group(1).strip()
                    # Clean up question text
                    question_text = re.sub(r'^\d+[\.\)]\s*', '', question_text)  # Remove leading numbers
                    question_text = re.sub(r'\[.*?\]', '', question_text)  # Remove [Learning Outcome X.X]
                    question_text = re.sub(r'\s+', ' ', question_text).strip()
            
            # Extract answer
            answer_match = re.search(r'Answer:\s*([A-E](?:,\s*[A-E])*)', section, re.IGNORECASE)
            answer = answer_match.group(1).strip() if answer_match else ""
            
            # Extract explanation
            explanation_match = re.search(r'Explanation:\s*(.+?)(?=\n\s*(?:Question|Q\d*:|--|==|Curve\s+Ball:|$|\Z))', section, re.DOTALL | re.IGNORECASE)
            explanation = explanation_match.group(1).strip() if explanation_match else ""
            
            # Extract curve ball flag
            curve_ball_match = re.search(r'Curve\s+Ball:\s*(Yes|True|1)', section, re.IGNORECASE)
            is_curve_ball = bool(curve_ball_match)
            
            if question_text and explanation:
                # Store by (module, source_file_key, normalized question text). source_file_key = paper stem or '' for study_text.
                normalized_q = self.normalize_text(question_text)
                self.explanations[(module, source_file_key, normalized_q)] = {
                    'explanation': explanation,
                    'answer': answer,
                    'is_curve_ball': is_curve_ball
                }
    
    def _source_stem(self, source_file):
        """Return stem of source_file (e.g. 'LM1 Exam - 2026.pdf' -> 'LM1 Exam - 2026')."""
        if not source_file:
            return ''
        return Path(source_file).stem
    
    def _iter_for_module(self, module, source_file_key=None):
        """Yield (normalized_q, data) for a given module (and optionally source_file_key)."""
        for key, data in self.explanations.items():
            mod, src, normalized_q = key
            if module is not None and mod != module:
                continue
            if source_file_key is not None and src != source_file_key:
                continue
            yield normalized_q, data
    
    def get_explanation(self, question_text, module=None, source_file=None):
        """Get pre-written explanation. Prefer explanation from the question's past paper (source_file), then module-wide."""
        normalized_q = self.normalize_text(question_text)
        source_stem = self._source_stem(source_file) if source_file else ''
        
        # Try exact match: (module, source_stem, norm_q) then (module, '', norm_q)
        if module:
            if source_stem and (module, source_stem, normalized_q) in self.explanations:
                return self.explanations[(module, source_stem, normalized_q)]['explanation']
            if (module, '', normalized_q) in self.explanations:
                return self.explanations[(module, '', normalized_q)]['explanation']
        if module is None:
            for (m, src, q), data in self.explanations.items():
                if q == normalized_q:
                    return data['explanation']
        
        # Try fuzzy matching: prefer same paper, then module-wide
        question_words = normalized_q.split()
        common_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'has', 'have', 'had', 
                       'this', 'that', 'these', 'those', 'what', 'which', 'who', 'when', 'where', 'how',
                       'and', 'or', 'but', 'if', 'of', 'to', 'for', 'with', 'from', 'by', 'in', 'on', 'at'}
        key_words = [w for w in question_words if len(w) >= 4 and w not in common_words]
        key_words.extend([w for w in question_words if re.search(r'[£\d]', w)])
        
        best_match = None
        best_score = 0
        for source_key in ([source_stem] if source_stem else []) + ['']:
            for stored_q, data in self._iter_for_module(module, source_key):
                stored_words = set(stored_q.split())
                question_words_set = set(normalized_q.split())
                stored_key_words = [w for w in stored_q.split() if len(w) >= 4 and w not in common_words]
                stored_key_words.extend([w for w in stored_q.split() if re.search(r'[£\d]', w)])
                key_overlap = len(set(key_words) & set(stored_key_words))
                total_overlap = len(stored_words & question_words_set)
                similarity = total_overlap / max(len(stored_words), len(question_words_set), 1)
                key_similarity = key_overlap / max(len(key_words), len(stored_key_words), 1) if key_words else 0
                if (key_similarity >= 0.5 and key_overlap >= 3) or similarity >= 0.8:
                    if similarity > best_score:
                        best_score = similarity
                        best_match = data['explanation']
        
        return best_match
    
    def get_answer(self, question_text, module=None, source_file=None):
        """Get answer from explanations file. Prefer same past paper, then module-wide."""
        normalized_q = self.normalize_text(question_text)
        source_stem = self._source_stem(source_file) if source_file else ''
        if module:
            if source_stem and (module, source_stem, normalized_q) in self.explanations:
                return self.explanations[(module, source_stem, normalized_q)].get('answer', '').strip().upper()
            if (module, '', normalized_q) in self.explanations:
                return self.explanations[(module, '', normalized_q)].get('answer', '').strip().upper()
        if module is None:
            for (m, src, q), data in self.explanations.items():
                if q == normalized_q:
                    return data.get('answer', '').strip().upper()
        key_words = normalized_q.split()[:20]
        key_phrase = ' '.join(key_words)
        best_match = None
        best_score = 0
        for source_key in ([source_stem] if source_stem else []) + ['']:
            for stored_q, data in self._iter_for_module(module, source_key):
                if key_phrase in stored_q or stored_q in normalized_q:
                    stored_words = set(stored_q.split())
                    question_words_set = set(normalized_q.split())
                    overlap = len(stored_words & question_words_set)
                    similarity = overlap / max(len(stored_words), len(question_words_set), 1)
                    if similarity >= 0.6 or overlap >= 8:
                        if similarity > best_score:
                            best_score = similarity
                            best_match = data.get('answer', '').strip().upper()
        return best_match
    
    def get_curve_ball(self, question_text, module=None, source_file=None):
        """Get curve ball flag. Prefer same past paper, then module-wide."""
        normalized_q = self.normalize_text(question_text)
        source_stem = self._source_stem(source_file) if source_file else ''
        if module:
            if source_stem and (module, source_stem, normalized_q) in self.explanations:
                return self.explanations[(module, source_stem, normalized_q)].get('is_curve_ball', False)
            if (module, '', normalized_q) in self.explanations:
                return self.explanations[(module, '', normalized_q)].get('is_curve_ball', False)
        if module is None:
            for (m, src, q), data in self.explanations.items():
                if q == normalized_q:
                    return data.get('is_curve_ball', False)
        key_words = normalized_q.split()[:20]
        key_phrase = ' '.join(key_words)
        best_match = None
        best_score = 0
        for source_key in ([source_stem] if source_stem else []) + ['']:
            for stored_q, data in self._iter_for_module(module, source_key):
                if key_phrase in stored_q or stored_q in normalized_q:
                    stored_words = set(stored_q.split())
                    question_words_set = set(normalized_q.split())
                    overlap = len(stored_words & question_words_set)
                    similarity = overlap / max(len(stored_words), len(question_words_set), 1)
                    if similarity >= 0.6 or overlap >= 8:
                        if similarity > best_score:
                            best_score = similarity
                            best_match = data.get('is_curve_ball', False)
        return best_match if best_match is not None else False

class StudyTextIndex:
    """Index study text for concept lookup"""
    
    # Common OCR and spelling corrections (insurance / London Market study text)
    OCR_CORRECTIONS = {
        'los': 'loss', 'ocurs': 'occurs', 'ocured': 'occurred', 'wil': 'will', 'prof': 'proof',
        'diferent': 'different', 'alowed': 'allowed', 'seeking': 'seeking', 'sek': 'seek',
        'comon': 'common', 'efect': 'effect', 'vesel': 'vessel', 'ben': 'been', 'gods': 'goods',
        'aply': 'apply', 'acident': 'accident', 'shortfal': 'shortfall', 'clasification': 'classification',
        'remedy': 'remedy', 'obstacle': 'obstacle', 'otherwise': 'otherwise', 'principle': 'principle',
        'available': 'available', 'insurer': 'insurer', 'required': 'required', 'condition': 'condition',
        'notice': 'notice', 'policy': 'policy', 'insured': 'insured',
        'reinsurer': 'reinsurer', 'reinsurance': 'reinsurance', 'underwriter': 'underwriter',
        'broker': 'broker', 'premium': 'premium', 'indemnity': 'indemnity', 'liability': 'liability',
        'subrogation': 'subrogation', 'utmost': 'utmost', 'disclosure': 'disclosure',
        'warranty': 'warranty', 'proposal': 'proposal', 'certificate': 'certificate',
        'endorsement': 'endorsement', 'exclusion': 'exclusion', 'deductible': 'deductible',
        'occurrence': 'occurrence', 'aggregate': 'aggregate', 'subscription': 'subscription',
        'syndicate': 'syndicate', 'Lloyd\'s': 'Lloyd\'s', 'market': 'market',
        'regulatory': 'regulatory', 'legislation': 'legislation', 'compliance': 'compliance',
        'procedures': 'procedures', 'hospitality': 'hospitality', 'suspicious': 'suspicious',
        'laundering': 'laundering', 'protection': 'protection', 'data': 'data',
        'organisation': 'organisation',
        'comunicating': 'communicating', 'bared': 'barred', 'agre': 'agree',
        'suficient': 'sufficient', 'imediately': 'immediately', 'loking': 'looking',
        'carying': 'carrying', 'god': 'good', 'aplys': 'applies', 'equaly': 'equally',
        'aply': 'apply', 'terminology': 'terminology', 'precluded': 'precluded',
    }
    
    def __init__(self):
        self.full_texts = {}  # Store full text by file
        self.question_explanations = QuestionExplanations()  # Load pre-written explanations
        self.load_study_text()
    
    @staticmethod
    def fix_ocr_errors(text):
        """Fix common OCR errors in text"""
        if not text:
            return text
        
        # Fix common OCR errors
        words = text.split()
        corrected_words = []
        
        for word in words:
            # Remove trailing punctuation temporarily
            punct = ''
            if word and word[-1] in '.,!?;:':
                punct = word[-1]
                word_clean = word[:-1]
            else:
                word_clean = word
            
            # Check for OCR errors (case-insensitive)
            word_lower = word_clean.lower()
            if word_lower in StudyTextIndex.OCR_CORRECTIONS:
                # Preserve original capitalization
                if word_clean[0].isupper():
                    corrected = StudyTextIndex.OCR_CORRECTIONS[word_lower].capitalize()
                else:
                    corrected = StudyTextIndex.OCR_CORRECTIONS[word_lower]
                corrected_words.append(corrected + punct)
            else:
                corrected_words.append(word)
        
        return ' '.join(corrected_words)
    
    @staticmethod
    def cleanup_explanation_text(text):
        """Fix spelling, grammar and consistency in explanation text. Use for all explanations (LM1 and M05)."""
        if not text or not isinstance(text, str):
            return text or ''
        # Remove page/section references (e.g. "2: Basic insurance legal principles and terminology 49")
        text = re.sub(r'\d+:\s*[A-Za-z][^.]*?\s+\d+(?=\s|$)', ' ', text)
        # Remove heading-style fragments that run into the next sentence (e.g. "Precluded subrogation rights There" -> "There")
        text = re.sub(
            r'\b(Precluded subrogation rights|Insured has no rights|Information that the insured does not know)\s+',
            ' ',
            text,
            flags=re.IGNORECASE
        )
        # Normalise whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        # Fix repeated words (the the, a a, is is, etc.)
        for word in ['the', 'a', 'an', 'is', 'are', 'was', 'were', 'to', 'of', 'in', 'on', 'and', 'it', 'be', 'have', 'has', 'that', 'this']:
            text = re.sub(rf'\b({re.escape(word)})\s+\1\b', r'\1', text, flags=re.IGNORECASE)
        # Fix common grammar: 'a' before vowel sound (a insurer -> an insurer, a underwriter -> an underwriter)
        text = re.sub(r'\ba\s+([aeiouAEIOU])', r'an \1', text)
        # Remove double punctuation
        text = re.sub(r'\.\s*\.', '.', text)
        text = re.sub(r'\?\s*\?', '?', text)
        text = re.sub(r'!\s*!', '!', text)
        # Space after sentence-ending punctuation if missing
        text = re.sub(r'\.([A-Z])', r'. \1', text)
        text = re.sub(r'\?([A-Z])', r'? \1', text)
        text = re.sub(r'!([A-Z])', r'! \1', text)
        # Ensure first character is uppercase
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        # Ensure ends with sentence punctuation
        text = text.rstrip()
        if text and text[-1] not in '.!?':
            text = text.rstrip(',;:') + '.'
        # Final whitespace normalisation
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def load_study_text(self):
        """Load study text from each module's study_text: modules/<name>/study_text/."""
        for module in get_module_names():
            study_dir = MODULES_DIR / module / "study_text"
            if not study_dir.exists():
                continue
            for file_path in study_dir.iterdir():
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() == '.pdf':
                    text = QuestionParser.extract_text_from_pdf(file_path)
                elif file_path.suffix.lower() == '.docx':
                    text = QuestionParser.extract_text_from_docx(file_path)
                elif file_path.suffix.lower() == '.txt':
                    text = file_path.read_text(encoding='utf-8')
                else:
                    continue
                key = f"{module}/{file_path.name}"
                self.full_texts[key] = text
    
    @staticmethod
    def _strip_question_number_from_explanation(text):
        """Remove leading 'Question N' / 'Question N.' so explanations don't show question numbers."""
        if not text or not isinstance(text, str):
            return (text or '').strip()
        t = text.strip()
        # Strip "Question 51 ", "Question 51.", "Question 120 By ..." etc.
        t = re.sub(r'^Question\s+\d+\s*[.:]?\s*', '', t, flags=re.IGNORECASE)
        return t.strip()

    @staticmethod
    def _explanation_is_low_value(explanation, question_text):
        """True if the explanation adds no conceptual detail (circular or just restates answer)."""
        if not explanation or not question_text:
            return True
        def norm(s):
            s = re.sub(r'[^\w\s]', ' ', (s or '').lower())
            return re.sub(r'\s+', ' ', s).strip()
        en = norm(explanation)
        if len(en) < 15:
            return True
        # Circular: "the correct answer is X. you selected Y" - no conceptual content
        if re.search(r'correct answer is .+ you selected', en) or re.search(r'you selected .+ correct answer', en):
            return True
        qn = norm(question_text)
        qw = set(qn.split())
        ew = set(en.split())
        overlap = len(qw & ew) / max(len(qw), 1)
        if overlap >= 0.75 and len(ew) <= len(qw) * 1.3:
            return True
        if qn in en and len(en) <= len(qn) + 5:
            return True
        return False

    def generate_feedback_explanation(self, question_text, correct_answer_text, selected_answer_text, options_text=None, is_correct=False, module=None, source_file=None):
        # First, try to get pre-written explanation (prefer same past paper, then module-wide)
        pre_written = self.question_explanations.get_explanation(question_text, module, source_file=source_file)
        if pre_written:
            # Strip any "Question N" prefix and clean up
            explanation = self._strip_question_number_from_explanation(pre_written)
            explanation = self.fix_ocr_errors(explanation)
            explanation = self.cleanup_explanation_text(explanation)
            if explanation and not explanation.endswith(('.', '!', '?')):
                explanation += '.'
            # If the explanation is just the question repeated, use study text instead
            if self._explanation_is_low_value(explanation, question_text):
                pre_written = None
            else:
                if is_correct:
                    return f"Correct! {explanation}"
                else:
                    return f"The correct answer is {correct_answer_text}. {explanation}"
        
        # Fall back to study text search if no pre-written explanation or it was low-value
        # Extract key concepts from question and answer
        # Focus on legal terms and concepts, not common words
        question_lower = question_text.lower()
        answer_lower = correct_answer_text.lower()
        
        # Extract important legal/concept terms (longer, specific words)
        important_terms = []
        # Get terms from question (focus on legal concepts)
        question_terms = re.findall(r'\b\w{5,}\b', question_lower)
        important_terms.extend([t for t in question_terms if t not in 
                                ['which', 'there', 'their', 'would', 'could', 'should', 'about', 'other', 
                                 'these', 'those', 'court', 'legal', 'law', 'policy', 'cover', 'invalid']])
        
        # Get terms from correct answer
        answer_terms = re.findall(r'\b\w{4,}\b', answer_lower)
        important_terms.extend([t for t in answer_terms if len(t) > 4])
        
        # Remove duplicates
        important_terms = list(dict.fromkeys(important_terms))[:10]
        
        # Find relevant study text sections (scoped to module when provided)
        relevant_sections = self.find_relevant_text(question_text, options_text, module=module)
        
        if not relevant_sections:
            # Fallback when no study text found - avoid circular "correct is X, you selected Y"
            mod_ref = f" {module} study text" if module else " the study text"
            if is_correct:
                return f"Correct! {correct_answer_text} is the right answer. Refer to the{mod_ref} for more detail on this topic."
            else:
                return f"The correct answer is {correct_answer_text}. For a full explanation of why this is correct and how it relates to the syllabus, refer to the{mod_ref}."
        
        core_explanation = self._extract_explanation_from_sections(
            question_text, options_text or [], relevant_sections, correct_answer_text
        )
        if core_explanation is None:
            mod_ref = f" {module} study text" if module else " the study text"
            if is_correct:
                return f"Correct! {correct_answer_text} is the right answer. Refer to the{mod_ref} for more detail."
            else:
                return f"The correct answer is {correct_answer_text}. For a full explanation, refer to the{mod_ref}."
        
        # Clean up formatting and spelling/grammar
        core_explanation = re.sub(r'[•\-\*]\s*', '', core_explanation)
        core_explanation = re.sub(r'^\d+[\.\)]\s*', '', core_explanation, flags=re.MULTILINE)
        core_explanation = re.sub(r'^\s*[•\-\*]\s*', '', core_explanation, flags=re.MULTILINE)
        core_explanation = re.sub(r'^[A-Z]\s+', '', core_explanation)
        core_explanation = re.sub(r'\b(after you have|you may study|you should|you will learn)\b[^.]*\.?\s*', '', core_explanation, flags=re.IGNORECASE)
        core_explanation = re.sub(r'\s+', ' ', core_explanation).strip()
        core_explanation = re.sub(r'\.{2,}', '.', core_explanation)
        core_explanation = re.sub(r'^[,\s;:]+', '', core_explanation)
        core_explanation = re.sub(r'[,;:]+$', '', core_explanation)
        core_explanation = self.fix_ocr_errors(core_explanation)
        core_explanation = self.cleanup_explanation_text(core_explanation)
        
        if is_correct:
            return f"Correct! {core_explanation}"
        else:
            return f"The correct answer is {correct_answer_text}. {core_explanation}"
    
    def _extract_explanation_from_sections(self, question_text, options_text, relevant_sections, correct_answer_text=None):
        """Extract the best explanation string from relevant study text sections. Used by feedback and by LM1 file generation."""
        question_lower = question_text.lower()
        important_terms = []
        question_terms = re.findall(r'\b\w{5,}\b', question_lower)
        important_terms.extend([t for t in question_terms if t not in 
                                ['which', 'there', 'their', 'would', 'could', 'should', 'about', 'other', 
                                 'these', 'those', 'court', 'legal', 'law', 'policy', 'cover', 'invalid']])
        if options_text:
            answer_terms = re.findall(r'\b\w{4,}\b', ' '.join(options_text).lower())
            important_terms.extend([t for t in answer_terms if len(t) > 4])
        important_terms = list(dict.fromkeys(important_terms))[:10]
        
        instructional_patterns = [
            r'after you have', r'you may study', r'you should', r'you will learn',
            r'this section', r'next section', r'previous section'
        ]
        explanatory_words = ['means', 'refers', 'defined', 'definition', 'is when', 'is that', 
                             'applies', 'applies when', 'occurs', 'requires', 'entitles', 'allows']
        
        best_explanation = None
        best_score = 0
        
        for section in relevant_sections:
            section_text = section['text']
            section_lower = section_text.lower()
            if any(re.search(p, section_lower) for p in instructional_patterns):
                continue
            score = 0
            term_matches = sum(1 for term in important_terms if term in section_lower)
            score += term_matches * 3
            explanatory_matches = sum(1 for word in explanatory_words if word in section_lower)
            score += explanatory_matches * 2
            
            sentences = re.split(r'[.!?]\s+', section_text)
            explanatory_sentences = []
            for sentence in sentences:
                sentence_lower = sentence.lower()
                if any(re.search(p, sentence_lower) for p in instructional_patterns):
                    continue
                # Skip sentences that are just the question restated (e.g. "Question 51 By disclosing...")
                if re.match(r'^question\s+\d+\s', sentence_lower):
                    continue
                term_count = sum(1 for term in important_terms if term in sentence_lower)
                if term_count > 0:
                    is_explanatory = any(w in sentence_lower for w in explanatory_words) or 'is' in sentence_lower or 'are' in sentence_lower
                    if is_explanatory and len(sentence.split()) > 8:
                        explanatory_sentences.append((term_count, sentence.strip()))
            
            if explanatory_sentences:
                explanatory_sentences.sort(key=lambda x: x[0], reverse=True)
                explanation = explanatory_sentences[0][1]
                explanation = self._strip_question_number_from_explanation(explanation)
                explanation = re.sub(r'^[A-Z]\s+', '', explanation)
                explanation = re.sub(r'^\d+[\.\)]\s*', '', explanation)
                explanation = self.fix_ocr_errors(explanation)
                explanation = re.sub(r'\.{2,}', '.', explanation)
                words = explanation.split()
                if len(words) > 50:
                    explanation = ' '.join(words[:50])
                    last_period = explanation.rfind('.')
                    if last_period > len(explanation) * 0.7:
                        explanation = explanation[:last_period+1]
                if len(explanation.split()) >= 8 and score >= 2 and score > best_score:
                    best_score = score
                    best_explanation = explanation
        
        if best_explanation and best_score >= 2:
            return best_explanation
        
        best_section = relevant_sections[0]['text']
        sentences = re.split(r'[.!?]\s+', best_section)
        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(re.search(p, sentence_lower) for p in instructional_patterns):
                continue
            term_count = sum(1 for term in important_terms if term in sentence_lower)
            if term_count > 0 and len(sentence.split()) > 8:
                out = ' '.join(sentence.split()[:40])
                out = self.fix_ocr_errors(out)
                if not out.endswith(('.', '!', '?')):
                    out += '.'
                return out
        
        if correct_answer_text:
            return f"This relates to {correct_answer_text.lower()}."
        return "See study text for more detail."
    
    def get_explanation_from_study_text(self, question_text, options_text=None, module=None, correct_answer_text=None):
        """Get a single explanation string from study text (for feedback or for generating LM1 explanations file)."""
        relevant_sections = self.find_relevant_text(question_text, options_text, module=module)
        if not relevant_sections:
            return None
        raw = self._extract_explanation_from_sections(
            question_text, options_text or [], relevant_sections, correct_answer_text
        )
        if not raw:
            return None
        raw = re.sub(r'[•\-\*]\s*', '', raw)
        raw = re.sub(r'^\d+[\.\)]\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'^[A-Z]\s+', '', raw)
        raw = re.sub(r'\s+', ' ', raw).strip()
        raw = self.fix_ocr_errors(raw)
        raw = self.cleanup_explanation_text(raw)
        return raw
    
    def find_relevant_text(self, question_text, options_text=None, module=None):
        """Find relevant study text sections for a question. If module is set, only search that module's study text."""
        # Extract meaningful keywords from question
        # Focus on legal terms, concepts, and important nouns
        question_lower = question_text.lower()
        
        # Extract key legal terms and concepts (longer words, proper nouns, etc.)
        # Look for legal terms, act names, concepts
        keywords = []
        
        # Extract words that are likely legal terms (5+ chars, not common words)
        common_words = {'which', 'there', 'their', 'would', 'could', 'should', 'about', 'other', 
                        'these', 'those', 'court', 'legal', 'law', 'act', 'may', 'can', 'must'}
        
        # Get meaningful words from question
        question_words = re.findall(r'\b\w{4,}\b', question_lower)
        keywords.extend([w for w in question_words if w not in common_words and len(w) > 3])
        
        # Also extract from options if provided
        if options_text:
            for opt in options_text:
                opt_words = re.findall(r'\b\w{4,}\b', opt.lower())
                keywords.extend([w for w in opt_words if w not in common_words and len(w) > 3])
        
        # Remove duplicates and keep top keywords
        keywords = list(dict.fromkeys(keywords))[:8]  # Top 8 unique keywords
        
        if not keywords:
            return []
        
        relevant_sections = []
        texts_to_search = self.full_texts.items() if module is None else [(k, v) for k, v in self.full_texts.items() if k.startswith(module + "/")]
        for file_name, full_text in texts_to_search:
            # Split into paragraphs (double newlines or sentence breaks)
            paragraphs = re.split(r'\n\s*\n|\.\s+(?=[A-Z])', full_text)
            
            scored_paragraphs = []
            
            for para in paragraphs:
                # Skip very short paragraphs
                para_clean = para.strip()
                if len(para_clean) < 30:
                    continue
                
                # Skip paragraphs that are mostly reference lists
                # Check for patterns like "Act 1906, 5C5" or lots of codes/references
                code_patterns = len(re.findall(r'\d{4}[A-Z]?\d+[A-Z]?', para_clean))
                reference_patterns = len(re.findall(r'[A-Z]\d+[A-Z]?\d*', para_clean))
                
                # If there are many codes/references relative to text length, skip it
                words_in_para = len(para_clean.split())
                if words_in_para > 0:
                    code_density = (code_patterns + reference_patterns) / words_in_para
                    if code_density > 0.15:  # More than 15% codes/references
                        continue
                
                # Skip if it starts with a reference pattern
                if re.match(r'^[A-Z][a-z]+\s+\d{4}', para_clean):
                    # Check if it's mostly a list (many commas, few sentences)
                    commas = para_clean.count(',')
                    periods = para_clean.count('.')
                    if commas > periods * 2 and commas > 5:
                        continue
                
                # Skip table of contents style content
                if re.match(r'^(Chapter|Section|Page|\d+\.)', para_clean, re.IGNORECASE):
                    continue
                
                # Skip paragraphs that are mostly numbers/codes
                words = para_clean.split()
                if len(words) > 0:
                    non_word_chars = sum(1 for w in words if not re.search(r'[a-zA-Z]{3,}', w))
                    if non_word_chars / len(words) > 0.4:  # More than 40% non-words
                        continue
                
                para_lower = para_clean.lower()
                
                # Score paragraph by keyword matches
                score = 0
                matched_keywords = []
                for keyword in keywords:
                    if keyword in para_lower:
                        score += 2  # Higher weight for keyword matches
                        matched_keywords.append(keyword)
                
                # Bonus for multiple keyword matches
                if len(matched_keywords) >= 2:
                    score += len(matched_keywords)
                
                if score > 0:
                    # Limit paragraph to reasonable length and clean it
                    words = para_clean.split()
                    if len(words) > 100:
                        # Take a relevant chunk (try to find where keywords appear)
                        best_start = 0
                        best_score = 0
                        for i in range(len(words) - 50):
                            chunk = ' '.join(words[i:i+60])
                            chunk_score = sum(1 for kw in keywords if kw in chunk.lower())
                            if chunk_score > best_score:
                                best_score = chunk_score
                                best_start = i
                        para_clean = ' '.join(words[best_start:best_start+60])
                    
                    # Strictly limit to 50 words max
                    words = para_clean.split()
                    if len(words) > 50:
                        # Take first 50 words
                        para_clean = ' '.join(words[:50])
                        # Try to end at a sentence boundary if possible
                        last_period = para_clean.rfind('.')
                        last_excl = para_clean.rfind('!')
                        last_quest = para_clean.rfind('?')
                        last_punct = max(last_period, last_excl, last_quest)
                        # If we find punctuation in the last 40% of text, use it
                        if last_punct > len(para_clean) * 0.6:
                            para_clean = para_clean[:last_punct+1].strip()
                        else:
                            # Otherwise just ensure it doesn't end mid-word
                            para_clean = para_clean.rstrip()
                            if not para_clean.endswith(('.', '!', '?', ';', ':')):
                                para_clean += '.'
                    
                    # Clean up extra whitespace and formatting issues
                    para_clean = re.sub(r'\s+', ' ', para_clean).strip()
                    # Remove bullet points and list markers
                    para_clean = re.sub(r'[•\-\*]\s*', '', para_clean)
                    # Remove duplicate words/phrases (like "Chapter 1Chapter 1")
                    para_clean = re.sub(r'(\w+)\1+', r'\1', para_clean)
                    # Remove page numbers and formatting artifacts
                    para_clean = re.sub(r'\d+/\d+', '', para_clean)  # Remove page numbers like "1/15"
                    para_clean = re.sub(r'Chapter \d+Chapter \d+', 'Chapter', para_clean)
                    # Remove list markers at start of sentences
                    para_clean = re.sub(r'^\d+[\.\)]\s*', '', para_clean, flags=re.MULTILINE)
                    # Fix OCR errors
                    para_clean = StudyTextIndex.fix_ocr_errors(para_clean)
                    para_clean = re.sub(r'\s+', ' ', para_clean).strip()
                    
                    # Final word count check
                    words = para_clean.split()
                    if len(words) > 50:
                        para_clean = ' '.join(words[:50]).rstrip()
                        if not para_clean.endswith(('.', '!', '?', ';', ':')):
                            para_clean += '.'
                    elif len(words) < 10:
                        # Skip if too short after cleaning
                        continue
                    
                    scored_paragraphs.append({
                        'score': score,
                        'text': para_clean.strip(),
                        'matched_keywords': matched_keywords
                    })
            
            # Sort by score and get best match
            scored_paragraphs.sort(key=lambda x: x['score'], reverse=True)
            
            # Get top 1-2 most relevant sections
            for section in scored_paragraphs[:2]:
                if len(section['text'].split()) >= 10:  # At least 10 words
                    relevant_sections.append({
                        'file': file_name,
                        'text': section['text'],
                        'relevance_score': section['score']
                    })
                    if len(relevant_sections) >= 2:  # Max 2 sections
                        break
        
        # Sort by relevance score
        relevant_sections.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        return relevant_sections[:2]  # Return top 2 most relevant

# Initialize
study_index = StudyTextIndex()

# In-memory cache so we don't reparse all PDFs on every request (fixes slow load and slow submit)
_questions_cache = None

def load_questions():
    """Load questions from file or parse from papers. Uses in-memory cache after first load."""
    global _questions_cache
    if _questions_cache is not None:
        return _questions_cache
    questions = QuestionParser.load_questions_from_files()
    save_questions(questions)
    _questions_cache = questions
    return questions

def save_questions(questions):
    """Save questions to file"""
    with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(questions, f, indent=2, ensure_ascii=False)


def load_planner():
    """Load study planner data (enrolled units + long-term plan)."""
    if PLANNER_FILE.exists():
        try:
            with open(PLANNER_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Ensure expected keys exist
                data.setdefault('enrolled_units', [])
                data.setdefault('plan', [])
                data.setdefault('exemptions', {})
                data.setdefault('active_modules', [])
                return data
        except Exception:
            pass
    return {'enrolled_units': [], 'plan': [], 'exemptions': {}, 'active_modules': []}


def save_planner(data):
    """Persist study planner data."""
    existing = load_planner() if PLANNER_FILE.exists() else {}
    cleaned = {
        'enrolled_units': data.get('enrolled_units', existing.get('enrolled_units', [])),
        'plan': data.get('plan', existing.get('plan', [])),
        'exemptions': data.get('exemptions', existing.get('exemptions', {})),
        'active_modules': data.get('active_modules', existing.get('active_modules', [])),
    }
    with open(PLANNER_FILE, 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)


def load_wrong_questions():
    """Load the set of question IDs the user has gotten wrong (for review stack)."""
    if not WRONG_QUESTIONS_FILE.exists():
        return []
    try:
        with open(WRONG_QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def save_wrong_questions(question_ids):
    """Persist the wrong-questions stack."""
    with open(WRONG_QUESTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(question_ids), f)


def update_wrong_stack_from_results(questions, answers):
    """Add incorrect question IDs to stack, remove correct ones."""
    wrong_ids = set(load_wrong_questions())
    for i, ans in enumerate(answers or []):
        if i >= len(questions):
            break
        q_id = questions[i].get('id')
        if not q_id:
            continue
        if ans.get('correct'):
            wrong_ids.discard(q_id)
        else:
            wrong_ids.add(q_id)
    save_wrong_questions(wrong_ids)


@app.context_processor
def inject_session_user_id():
    """Expose session user id for templates (e.g. billing link for account users)."""
    return {'session_user_id': session.get('user_id')}


def login_required(f):
    """Decorator to require login for routes. Redirects to /subscribe if not subscribed."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('login'))
        # Subscription check: legacy users (no user_id) skip; DB users must have active subscription
        if session.get('user_id'):
            user = get_user_by_id(session['user_id'])
            if not user_has_active_subscription(user):
                return redirect(url_for('subscribe'))
        return f(*args, **kwargs)
    return decorated_function


def login_required_only(f):
    """Decorator to require login only (no subscription check). Use for subscribe/checkout routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page - supports legacy (username) and new (email) users."""
    if request.method == 'POST':
        identifier = (request.form.get('username') or request.form.get('email') or '').strip()
        password = request.form.get('password', '')
        
        # Legacy: username + password
        if identifier == DEFAULT_USERNAME and check_password_hash(DEFAULT_PASSWORD_HASH, password):
            session['logged_in'] = True
            session['username'] = identifier
            session['user_id'] = None  # legacy
            return redirect(url_for('index'))
        
        # New: email + password from DB
        if '@' in identifier:
            user = get_user_by_email(identifier)
            if user and user.get('password_hash') and check_password_hash(user['password_hash'], password):
                session['logged_in'] = True
                session['username'] = user['email']
                session['user_id'] = user['id']
                if not user_has_active_subscription(user):
                    return redirect(url_for('subscribe'))
                return redirect(url_for('index'))
        
        return render_template('login.html', error='Invalid email or password')
    
    if session.get('logged_in'):
        if session.get('user_id'):
            user = get_user_by_id(session['user_id'])
            if not user_has_active_subscription(user):
                return redirect(url_for('subscribe'))
        return redirect(url_for('index'))
    
    error = request.args.get('error')
    if error == 'google_auth_failed':
        error_msg = 'Google sign-in failed. Please try again.'
    elif error == 'google_no_email':
        error_msg = 'Could not get email from Google. Please use email sign-up.'
    elif error == 'google_create_failed':
        error_msg = 'Could not create account. Please try again.'
    elif error == 'google_not_configured':
        error_msg = 'Google sign-in is not configured.'
    else:
        error_msg = None
    return render_template('login.html', google_client_id=GOOGLE_CLIENT_ID, error=error_msg)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Sign up with email + password."""
    if session.get('logged_in'):
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        
        if not email or '@' not in email:
            return render_template('signup.html', error='Please enter a valid email address.')
        if len(password) < 8:
            return render_template('signup.html', error='Password must be at least 8 characters.')
        if password != confirm:
            return render_template('signup.html', error='Passwords do not match.')
        
        existing = get_user_by_email(email)
        if existing:
            return render_template('signup.html', error='An account with this email already exists.')
        
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        user = create_user(email, password_hash=password_hash)
        if not user:
            return render_template('signup.html', error='Could not create account. Please try again.')
        
        session['logged_in'] = True
        session['username'] = user['email']
        session['user_id'] = user['id']
        return redirect(url_for('subscribe'))
    
    return render_template('signup.html', google_client_id=GOOGLE_CLIENT_ID)


@app.route('/auth/google')
def auth_google():
    """Initiate Google OAuth."""
    if not oauth or not hasattr(oauth, 'google'):
        return redirect(url_for('login') + '?error=google_not_configured')
    redirect_uri = url_for('auth_google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/auth/google/callback')
def auth_google_callback():
    """Handle Google OAuth callback."""
    if not oauth or not hasattr(oauth, 'google'):
        return redirect(url_for('login') + '?error=google_not_configured')
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        return redirect(url_for('login') + '?error=google_auth_failed')
    
    user_info = token.get('userinfo') or {}
    google_id = user_info.get('sub')
    email = (user_info.get('email') or '').strip().lower()
    
    if not google_id or not email:
        return redirect(url_for('login') + '?error=google_no_email')
    
    user = get_user_by_google_id(google_id)
    if not user:
        user = get_user_by_email(email)
        if user:
            # Link Google to existing email account
            conn = get_db()
            conn.execute("UPDATE users SET google_id = ? WHERE id = ?", (google_id, user['id']))
            conn.commit()
            conn.close()
            user = get_user_by_id(user['id'])
        else:
            user = create_user(email, google_id=google_id)
    
    if not user:
        return redirect(url_for('login') + '?error=google_create_failed')
    
    session['logged_in'] = True
    session['username'] = user['email']
    session['user_id'] = user['id']
    
    if not user_has_active_subscription(user):
        return redirect(url_for('subscribe'))
    return redirect(url_for('index'))


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password for email users."""
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('index'))  # legacy users have no change-password
    
    user = get_user_by_id(user_id)
    if not user or not user.get('password_hash'):
        return redirect(url_for('index'))  # Google-only users
    
    if request.method == 'POST':
        current = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        
        if not check_password_hash(user['password_hash'], current):
            return render_template('change-password.html', error='Current password is incorrect.')
        if len(new_password) < 8:
            return render_template('change-password.html', error='New password must be at least 8 characters.')
        if new_password != confirm:
            return render_template('change-password.html', error='New passwords do not match.')
        
        update_user_password(user_id, generate_password_hash(new_password, method='pbkdf2:sha256'))
        return redirect(url_for('index'))
    
    return render_template('change-password.html')


@app.route('/subscribe')
def subscribe():
    """Subscription page - must be logged in."""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('index'))  # legacy users skip subscription
    user = get_user_by_id(user_id)
    if user_has_active_subscription(user):
        return redirect(url_for('index'))
    return render_template('subscribe.html', stripe_publishable_key=STRIPE_PUBLISHABLE_KEY,
                          stripe_price_id=STRIPE_PRICE_ID)


@app.route('/create-checkout-session', methods=['POST'])
@login_required_only
def create_checkout_session():
    """Create Stripe Checkout session for subscription."""
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        return jsonify({'error': 'Stripe not configured'}), 500
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Legacy users do not need subscription'}), 400
    
    user = get_user_by_id(user_id)
    price_id = request.json.get('price_id') if request.is_json else request.form.get('price_id')
    if not price_id:
        price_id = STRIPE_PRICE_ID
    
    try:
        customer_id = user.get('stripe_customer_id')
        if not customer_id:
            customer = stripe.Customer.create(email=user['email'])
            customer_id = customer.id
            conn = get_db()
            conn.execute("UPDATE users SET stripe_customer_id = ? WHERE id = ?", (customer_id, user_id))
            conn.commit()
            conn.close()
        
        session_obj = stripe.checkout.Session.create(
            customer=customer_id,
            mode='subscription',
            line_items=[{'price': price_id, 'quantity': 1}],
            success_url=url_for('subscribe_success', _external=True),
            cancel_url=url_for('subscribe', _external=True),
            metadata={'user_id': str(user_id)}
        )
        return jsonify({'url': session_obj.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/subscribe/success')
def subscribe_success():
    """Redirect after successful subscription - webhook will set status."""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('subscribe.html', stripe_publishable_key=STRIPE_PUBLISHABLE_KEY,
                          stripe_price_id=STRIPE_PRICE_ID, success=True)


@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks for checkout.session.completed and customer.subscription events."""
    import stripe
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')
    
    if not STRIPE_WEBHOOK_SECRET:
        return '', 400
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        return '', 400
    except Exception:
        return '', 400
    
    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        user_id = session_obj.get('metadata', {}).get('user_id')
        subscription_id = session_obj.get('subscription')
        if user_id and subscription_id:
            update_user_subscription(int(user_id), 'active', session_obj.get('customer'))
        
        # Also handle subscription object from session
        if 'subscription' in session_obj and session_obj['subscription']:
            sub = stripe.Subscription.retrieve(session_obj['subscription'])
            status = (sub.get('status') or '').lower()
            if status == 'active':
                customer_id = sub.get('customer')
                conn = get_db()
                rows = conn.execute("SELECT id FROM users WHERE stripe_customer_id = ?", (str(customer_id),)).fetchall()
                conn.close()
                for row in rows:
                    update_user_subscription(row[0], 'active')
    
    elif event['type'] == 'customer.subscription.updated':
        sub = event['data']['object']
        status = (sub.get('status') or '').lower()
        customer_id = sub.get('customer')
        conn = get_db()
        rows = conn.execute("SELECT id FROM users WHERE stripe_customer_id = ?", (str(customer_id),)).fetchall()
        conn.close()
        for row in rows:
            update_user_subscription(row[0], status)
    
    elif event['type'] == 'customer.subscription.deleted':
        sub = event['data']['object']
        customer_id = sub.get('customer')
        conn = get_db()
        rows = conn.execute("SELECT id FROM users WHERE stripe_customer_id = ?", (str(customer_id),)).fetchall()
        conn.close()
        for row in rows:
            update_user_subscription(row[0], 'canceled')
    
    return '', 200


@app.route('/billing/portal')
@login_required_only
def billing_portal():
    """Redirect to Stripe Customer Portal for payment method, invoices, and cancellation."""
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
    if not STRIPE_SECRET_KEY:
        return redirect(url_for('index'))
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('index'))
    user = get_user_by_id(user_id)
    if not user:
        return redirect(url_for('index'))
    customer_id = user.get('stripe_customer_id')
    if not customer_id:
        return redirect(url_for('subscribe'))
    try:
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=url_for('index', _external=True),
        )
        return redirect(portal.url)
    except Exception:
        return redirect(url_for('index'))


@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('selection.html')

@app.route('/quiz')
@login_required
def quiz():
    return render_template('quiz.html')

@app.route('/results')
@login_required
def results():
    return render_template('results.html')

@app.route('/history')
@login_required
def history():
    return render_template('history.html')


@app.route('/planner')
@login_required
def planner():
    """Exam planner page (certificate / diploma / advanced diploma)."""
    return render_template('planner.html')

@app.route('/api/check-auth')
def check_auth():
    """Check if user is authenticated"""
    return jsonify({'authenticated': session.get('logged_in', False)})


@app.route('/api/planner', methods=['GET', 'POST'])
@login_required
def planner_api():
    """Get or update the long-term exam planner (enrolled units and plan rows)."""
    if request.method == 'GET':
        return jsonify(load_planner())
    
    data = request.get_json(silent=True) or {}
    save_planner(data)
    return jsonify({'ok': True})


@app.route('/api/planner/active-modules', methods=['POST'])
@login_required
def update_active_modules():
    """Update which modules the user has selected for home screen display."""
    data = request.get_json(silent=True) or {}
    active = data.get('active_modules', [])
    if not isinstance(active, list):
        active = []
    existing = load_planner()
    existing['active_modules'] = [m for m in active if m in get_module_names()]
    save_planner(existing)
    return jsonify({'ok': True, 'active_modules': existing['active_modules']})

@app.route('/api/questions')
@login_required
def get_questions():
    """Get all questions"""
    questions = load_questions()
    return jsonify(questions)

@app.route('/api/questions/filter', methods=['POST'])
@login_required
def get_filtered_questions():
    """Get filtered questions by count, year, learning objective, curve ball, wrong questions, or multiple choice"""
    data = request.json or {}
    count = data.get('count')
    year = data.get('year')
    learning_objective = data.get('learning_objective')
    multiple_choice_only = data.get('multiple_choice_only', False)
    curve_ball_only = data.get('curve_ball_only', False)
    wrong_questions_only = data.get('wrong_questions_only', False)
    module_filter = data.get('module')
    
    all_questions = load_questions()
    
    # Practice is always per module; require module
    if not module_filter or module_filter not in get_module_names():
        return jsonify([])
    all_questions = [q for q in all_questions if q.get('module') == module_filter]
    
    # Filter by wrong-questions stack (questions user got wrong before)
    if wrong_questions_only:
        wrong_ids = set(load_wrong_questions())
        filtered = [q for q in all_questions if q.get('id') in wrong_ids]
        import random
        random.shuffle(filtered)
        if count:
            filtered = filtered[:int(count)]
        return jsonify(filtered)
    
    # Filter by curve ball only if specified
    if curve_ball_only:
        filtered = [q for q in all_questions if q.get('is_curve_ball', False)]
        # Shuffle for variety
        import random
        random.shuffle(filtered)
        # Limit by count if specified
        if count:
            filtered = filtered[:int(count)]
    # Filter by multiple choice only if specified
    elif multiple_choice_only:
        filtered = [q for q in all_questions if q.get('is_multiple_choice', False)]
        # Shuffle for variety
        import random
        random.shuffle(filtered)
        # Limit by count if specified
        if count:
            filtered = filtered[:int(count)]
    # Filter by learning objective if specified
    elif learning_objective:
        filtered = [q for q in all_questions if q.get('learning_objective') == str(learning_objective)]
        # Shuffle for variety
        import random
        random.shuffle(filtered)
        # Limit to 20 or all if less than 20
        if len(filtered) > 20:
            filtered = filtered[:20]
    # Filter by year if specified
    elif year:
        # Filter questions from the specified year
        filtered = [q for q in all_questions if str(year) in q.get('source_file', '')]
        # Sort by question number to maintain exact PDF order (1, 2, 3, ..., 50)
        def get_sort_key(q):
            q_num = q.get('question_number', '')
            try:
                # Use question_number directly for exact numerical order
                return int(q_num) if q_num.isdigit() else 999999
            except:
                # Fallback to original_order if question_number is invalid
                return q.get('original_order', 999999)
        filtered.sort(key=get_sort_key)
    else:
        filtered = all_questions
        # Only shuffle if it's a count-based selection (not a year)
        if count:
            import random
            random.shuffle(filtered)
    
    # Limit by count if specified (only for count-based selections, not learning objective)
    if count and not year and not learning_objective:
        filtered = filtered[:int(count)]
    
    return jsonify(filtered)

@app.route('/api/modules')
@login_required
def get_modules():
    """Return discovered modules (from modules/ subdirs) with question counts."""
    questions = load_questions()
    names = get_module_names()
    counts = {mod: 0 for mod in names}
    for q in questions:
        mod = q.get('module')
        if mod in counts:
            counts[mod] += 1
    return jsonify([{'code': mod, 'count': counts[mod]} for mod in names])

@app.route('/api/years')
@login_required
def get_available_years():
    """Get list of available exam years"""
    questions = load_questions()
    module_filter = request.args.get('module')
    if module_filter:
        questions = [q for q in questions if q.get('module') == module_filter]
    years = set()
    for q in questions:
        source = q.get('source_file', '')
        # Extract year from filename like "M05 Exam - 2024.pdf"
        year_match = re.search(r'(\d{4})', source)
        if year_match:
            years.add(year_match.group(1))
    return jsonify(sorted(list(years), reverse=True))

@app.route('/api/learning-objectives')
@login_required
def get_learning_objectives():
    """Get list of available learning objectives with question counts"""
    questions = load_questions()
    module_filter = request.args.get('module')
    if module_filter:
        questions = [q for q in questions if q.get('module') == module_filter]
    objectives = {}
    for q in questions:
        lo = q.get('learning_objective')
        if lo:
            if lo not in objectives:
                objectives[lo] = 0
            objectives[lo] += 1
    # Return sorted by objective number
    return jsonify(sorted([{'number': k, 'count': v} for k, v in objectives.items()], 
                          key=lambda x: float(x['number'])))

@app.route('/api/multiple-choice-count')
@login_required
def get_multiple_choice_count():
    """Get count of multiple choice questions available"""
    questions = load_questions()
    module_filter = request.args.get('module')
    if module_filter:
        questions = [q for q in questions if q.get('module') == module_filter]
    multiple_choice_count = sum(1 for q in questions if q.get('is_multiple_choice', False))
    return jsonify({'count': multiple_choice_count})

@app.route('/api/wrong-questions-count')
@login_required
def get_wrong_questions_count():
    """Get count of questions in the wrong-questions stack for the given module."""
    questions = load_questions()
    module_filter = request.args.get('module')
    if not module_filter:
        return jsonify({'count': 0})
    wrong_ids = set(load_wrong_questions())
    count = sum(1 for q in questions if q.get('module') == module_filter and q.get('id') in wrong_ids)
    return jsonify({'count': count})


@app.route('/api/curve-ball-count')
@login_required
def get_curve_ball_count():
    """Get count of curve ball questions available"""
    try:
        questions = load_questions()
        module_filter = request.args.get('module')
        if module_filter:
            questions = [q for q in questions if q.get('module') == module_filter]
        curve_ball_count = sum(1 for q in questions if q.get('is_curve_ball', False))
        print(f"Curve ball count API called: {curve_ball_count} questions found out of {len(questions)} total")
        return jsonify({'count': curve_ball_count})
    except Exception as e:
        print(f"Error in get_curve_ball_count: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'count': 0, 'error': str(e)}), 500

@app.route('/api/stats')
@login_required
def get_stats():
    """Get overall dashboard stats"""
    questions = load_questions()
    modules = {}
    for q in questions:
        mod = q.get('module', 'General')
        modules[mod] = modules.get(mod, 0) + 1
    
    results_file = Path("results_history.json")
    history = []
    if results_file.exists():
        with open(results_file, 'r', encoding='utf-8') as f:
            history = json.load(f)
    
    total_correct = sum(r.get('correct', 0) for r in history)
    total_qs_attempted = sum(r.get('total', 0) for r in history)
    avg_score = round((total_correct / total_qs_attempted) * 100) if total_qs_attempted > 0 else 0

    # Practice streak: consecutive days with at least one quiz
    streak = 0
    if history:
        from datetime import datetime, timezone, timedelta
        dates = set()
        for r in history:
            ts = r.get('timestamp', '')
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    dates.add(dt.date())
                except (ValueError, TypeError):
                    pass
        if dates:
            dates_sorted = sorted(dates, reverse=True)
            today = datetime.now(timezone.utc).date()
            for i, d in enumerate(dates_sorted):
                expected = today - timedelta(days=i)
                if d == expected:
                    streak += 1
                else:
                    break
    
    return jsonify({
        'total_questions': len(questions),
        'total_modules': len(modules),
        'quizzes_completed': len(history),
        'avg_score': avg_score,
        'practice_streak': streak
    })

@app.route('/api/results', methods=['POST'])
@login_required
def save_results():
    """Save quiz results to history"""
    data = request.json
    results_file = Path("results_history.json")
    
    # Load existing results
    if results_file.exists():
        with open(results_file, 'r', encoding='utf-8') as f:
            results_history = json.load(f)
    else:
        results_history = []
    
    # Add timestamp and save
    result_entry = {
        'id': len(results_history) + 1,
        'timestamp': data.get('timestamp', ''),
        'total': data.get('total', 0),
        'correct': data.get('correct', 0),
        'incorrect': data.get('incorrect', 0),
        'percentage': data.get('percentage', 0),
        'mode': data.get('mode', ''),
        'learning_objective_breakdown': data.get('learning_objective_breakdown', {}),
        'questions': data.get('questions', []),
        'answers': data.get('answers', [])
    }
    
    results_history.append(result_entry)

    # Update wrong-question stack: add incorrect, remove correct
    questions = data.get('questions', [])
    answers = data.get('answers', [])
    if questions and answers:
        update_wrong_stack_from_results(questions, answers)
    
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results_history, f, indent=2, ensure_ascii=False)
    
    return jsonify({'success': True, 'message': 'Results saved'})

@app.route('/api/results/history')
@login_required
def get_results_history():
    """Get all quiz results history"""
    results_file = Path("results_history.json")
    if results_file.exists():
        with open(results_file, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify([])

@app.route('/api/question/<int:question_id>')
@login_required
def get_question(question_id):
    """Get a specific question with study text references"""
    questions = load_questions()
    question = next((q for q in questions if q['id'] == question_id), None)
    
    if question:
        # Find relevant study text
        relevant_text = study_index.find_relevant_text(question['question'])
        question['study_text'] = relevant_text
    
    return jsonify(question)

@app.route('/api/submit-answer', methods=['POST'])
@login_required
def submit_answer():
    """Submit an answer and get feedback"""
    data = request.json
    question_id = data.get('question_id')
    selected_answer = data.get('answer')
    
    questions = load_questions()
    question = next((q for q in questions if q['id'] == question_id), None)
    
    if not question:
        return jsonify({'error': 'Question not found'}), 404
    
    # Handle multiple answer questions
    correct_answers = [a.strip().upper() for a in question['correct_answer'].split(',')]
    selected_answers = [a.strip().upper() for a in selected_answer.split(',')]
    
    # Check if correct (all selected answers are correct and all correct answers are selected)
    is_correct = (set(selected_answers) == set(correct_answers)) and len(selected_answers) == len(correct_answers)
    
    # Get correct option text(s) for feedback
    correct_options = [opt for opt in question['options'] if opt['letter'] in correct_answers]
    selected_options = [opt for opt in question['options'] if opt['letter'] in selected_answers]
    
    # Validate that we found the options
    if not correct_options:
        return jsonify({'error': f'Correct answer(s) {question["correct_answer"]} not found in options for question {question_id}'}), 400
    if not selected_options:
        return jsonify({'error': f'Selected answer(s) {selected_answer} not found in options for question {question_id}'}), 400
    
    # For single answer, use first option; for multiple, combine them
    correct_option = correct_options[0] if len(correct_options) == 1 else None
    correct_option_text = correct_option['text'] if correct_option else ', '.join([opt['text'] for opt in correct_options])
    selected_option = selected_options[0] if len(selected_options) == 1 else None
    selected_option_text = selected_option['text'] if selected_option else ', '.join([opt['text'] for opt in selected_options])
    
    # Generate concise feedback explanation from study text (scoped to question's module)
    options_text = [opt['text'] for opt in question['options']]
    feedback_explanation = study_index.generate_feedback_explanation(
        question['question'],
        correct_option_text,
        selected_option_text,
        options_text,
        is_correct,
        module=question.get('module'),
        source_file=question.get('source_file')
    )
    
    feedback = {
        'is_correct': is_correct,
        'correct_answer': question['correct_answer'],
        'correct_option_text': correct_option_text,
        'is_multiple_choice': question.get('is_multiple_choice', False),
        'selected_option_text': selected_option_text,
        'explanation': feedback_explanation,
        'learning_objective': question.get('learning_objective', ''),
        'feedback_points': []
    }
    
    return jsonify(feedback)

@app.route('/api/reload-questions', methods=['POST'])
@login_required
def reload_questions():
    """Reload questions from exam papers and refresh cache"""
    global _questions_cache
    questions = QuestionParser.load_questions_from_files()
    save_questions(questions)
    _questions_cache = questions
    study_index.load_study_text()  # Reload study text too
    return jsonify({'message': f'Loaded {len(questions)} questions', 'count': len(questions)})

@app.route('/api/submit-results', methods=['POST'])
@login_required
def submit_results():
    """Save quiz results"""
    data = request.json
    # Store results (could save to file/database)
    return jsonify({'success': True, 'message': 'Results saved'})

if __name__ == '__main__':
    init_db()
    # Ensure modules dir exists; create default module folders if empty
    MODULES_DIR.mkdir(exist_ok=True)
    for name in ["LM1", "M05", "LM2", "M92"]:
        (MODULES_DIR / name / "past_papers").mkdir(parents=True, exist_ok=True)
        (MODULES_DIR / name / "study_text").mkdir(parents=True, exist_ok=True)
    
    # Allow port to be set via environment variable (for hosting platforms)
    port = int(os.environ.get('PORT', 5001))
    # In production, set debug=False and host='0.0.0.0'
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)

