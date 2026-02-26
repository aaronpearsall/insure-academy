let questions = [];
let currentQuestionIndex = 0;
let selectedAnswer = null;
let selectedAnswers = []; // For multiple choice questions
let answers = []; // Store all answers for results
let score = 0;

// Check authentication on page load
document.addEventListener('DOMContentLoaded', async () => {
    // Check if user is authenticated
    try {
        const authResponse = await fetch('/api/check-auth');
        const authData = await authResponse.json();
        if (!authData.authenticated) {
            window.location.href = '/login';
            return;
        }
    } catch (error) {
        console.error('Auth check failed:', error);
        window.location.href = '/login';
        return;
    }
    // Try to restore progress from localStorage
    const restored = restoreProgress();
    
    // If no saved progress, load fresh questions
    if (!restored || questions.length === 0) {
        loadQuestions();
    } else {
        // Restore UI state
        showQuestion();
        updateScore();
    }
    
    document.getElementById('submitBtn').addEventListener('click', submitAnswer);
    document.getElementById('nextBtn').addEventListener('click', nextQuestion);
    document.getElementById('prevBtn').addEventListener('click', prevQuestion);
    document.getElementById('finishBtn').addEventListener('click', finishQuiz);
    document.getElementById('exitBtn').addEventListener('click', () => {
        if (confirm('Are you sure you want to exit? Your progress will be saved.')) {
            saveProgress();
            window.location.href = '/';
        }
    });
    
    // Save progress periodically
    setInterval(saveProgress, 30000); // Every 30 seconds
    
    // Save progress before page unload
    window.addEventListener('beforeunload', saveProgress);
});

async function loadQuestions() {
    try {
        showLoading();
        
        // Get quiz options from sessionStorage
        const quizOptions = JSON.parse(sessionStorage.getItem('quizOptions') || '{}');
        
        // Fetch filtered questions
        const response = await fetch('/api/questions/filter', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(quizOptions)
        });
        
        questions = await response.json();
        
        // Initialize answers array if not restored
        if (answers.length === 0) {
            answers = questions.map(() => ({ answered: false, selected: null, correct: null }));
        }
        
        if (questions.length === 0) {
            showNoQuestions();
        } else {
            showQuestion();
            updateScore();
        }
    } catch (error) {
        console.error('Error loading questions:', error);
        showError('Failed to load questions. Please try again.');
    }
}

function showLoading() {
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('questionContainer').classList.add('hidden');
    document.getElementById('noQuestions').classList.add('hidden');
}

function showNoQuestions() {
    document.getElementById('loading').classList.add('hidden');
    document.getElementById('questionContainer').classList.add('hidden');
    document.getElementById('noQuestions').classList.remove('hidden');
}

function showQuestion() {
    document.getElementById('loading').classList.add('hidden');
    document.getElementById('questionContainer').classList.remove('hidden');
    document.getElementById('noQuestions').classList.add('hidden');
    
    if (questions.length === 0) return;
    
    const question = questions[currentQuestionIndex];
    
    // Update question number and progress
    document.getElementById('currentQuestionNum').textContent = currentQuestionIndex + 1;
    document.getElementById('totalQuestions').textContent = questions.length;
    const progress = ((currentQuestionIndex + 1) / questions.length) * 100;
    document.getElementById('progressFill').style.width = progress + '%';
    
    // Display question
    document.getElementById('questionText').textContent = question.question;
    
    // ALWAYS reset selection state at the start of showing a question
    // This prevents carryover from previous questions
    selectedAnswer = null;
    selectedAnswers = [];
    
    // Check if already answered
    const answer = answers[currentQuestionIndex];
    
    // Display options
    const optionsContainer = document.getElementById('optionsContainer');
    optionsContainer.innerHTML = '';
    
    // Check if this is a multiple choice question
    const isMultiple = question.is_multiple_choice || (question.correct_answer && question.correct_answer.includes(','));
    
    question.options.forEach(option => {
        const optionDiv = document.createElement('div');
        optionDiv.className = 'option';
        optionDiv.dataset.letter = option.letter;
        
        // Check if already answered
        if (answer.answered) {
            const correctAnswers = question.correct_answer ? question.correct_answer.split(',').map(a => a.trim().toUpperCase()) : [];
            const selectedAnswersList = answer.selected ? answer.selected.split(',').map(a => a.trim().toUpperCase()) : [];
            
            if (correctAnswers.includes(option.letter.toUpperCase())) {
                optionDiv.classList.add('correct');
            } else if (selectedAnswersList.includes(option.letter.toUpperCase())) {
                optionDiv.classList.add('incorrect');
            }
        } else if (isMultiple && selectedAnswers.includes(option.letter)) {
            // This should now be empty for new questions, but check anyway
            optionDiv.classList.add('selected');
        }
        
        optionDiv.innerHTML = `
            <span class="option-label">${option.letter}</span>
            <span class="option-text">${option.text}</span>
        `;
        
        if (!answer.answered) {
            optionDiv.addEventListener('click', () => selectOption(option.letter, isMultiple));
        }
        
        optionsContainer.appendChild(optionDiv);
    });
    
    // Reset UI state (selection state already reset above)
    if (!answer.answered) {
        document.getElementById('submitBtn').disabled = true;
        document.getElementById('submitBtn').classList.remove('hidden');
        document.getElementById('nextBtn').classList.add('hidden');
        clearFeedback();
    } else {
        // Already answered, show feedback and enable next button
        showFeedbackForAnswered();
        // Hide submit button - question is already answered
        document.getElementById('submitBtn').classList.add('hidden');
        document.getElementById('submitBtn').disabled = true;
        // Show next button if not on last question
        if (currentQuestionIndex < questions.length - 1) {
            document.getElementById('nextBtn').classList.remove('hidden');
            document.getElementById('nextBtn').disabled = false;
        } else {
            // Last question - show finish button if all answered
            document.getElementById('nextBtn').classList.add('hidden');
            if (allQuestionsAnswered()) {
                document.getElementById('finishBtn').classList.remove('hidden');
                document.getElementById('finishBtn').disabled = false;
            }
        }
    }
    
    document.getElementById('prevBtn').classList.toggle('hidden', currentQuestionIndex === 0);
    // Only show finish button if all questions answered AND we're on the last question
    if (currentQuestionIndex < questions.length - 1 || !allQuestionsAnswered()) {
        document.getElementById('finishBtn').classList.add('hidden');
    }
}

function selectOption(letter, isMultiple = false) {
    if (isMultiple) {
        // Toggle selection for multiple choice
        const index = selectedAnswers.indexOf(letter);
        if (index > -1) {
            // Deselect
            selectedAnswers.splice(index, 1);
        } else {
            // Select
            selectedAnswers.push(letter);
        }
        // Sort to maintain consistent order (A, B, C, D, E)
        selectedAnswers.sort();
        selectedAnswer = selectedAnswers.join(',');
        
        // Debug logging - more detailed
        console.log('Option clicked:', letter);
        console.log('Selected answers array:', [...selectedAnswers]);
        console.log('Joined answer string:', selectedAnswer);
        console.log('All options state:', 
            Array.from(document.querySelectorAll('.option')).map(opt => ({
                letter: opt.dataset.letter,
                selected: opt.classList.contains('selected')
            }))
        );
        
        // Update UI - ensure only clicked option is toggled
        const optionDiv = document.querySelector(`.option[data-letter="${letter}"]`);
        if (optionDiv) {
            optionDiv.classList.toggle('selected');
        }
        
        // Verify UI matches state
        const allOptions = document.querySelectorAll('.option');
        allOptions.forEach(opt => {
            const optLetter = opt.dataset.letter;
            const shouldBeSelected = selectedAnswers.includes(optLetter);
            const isSelected = opt.classList.contains('selected');
            if (shouldBeSelected !== isSelected) {
                console.warn(`Mismatch for option ${optLetter}: should be ${shouldBeSelected}, is ${isSelected}`);
                // Fix the mismatch
                if (shouldBeSelected) {
                    opt.classList.add('selected');
                } else {
                    opt.classList.remove('selected');
                }
            }
        });
    } else {
        // Single choice - replace selection
        selectedAnswer = letter;
        selectedAnswers = [letter];
        
        // Update UI
        document.querySelectorAll('.option').forEach(opt => {
            opt.classList.remove('selected');
        });
        document.querySelector(`.option[data-letter="${letter}"]`).classList.add('selected');
    }
    
    document.getElementById('submitBtn').disabled = (selectedAnswer === null || selectedAnswer === '');
}

async function submitAnswer() {
    if (!selectedAnswer) return;
    
    const question = questions[currentQuestionIndex];
    
    // CRITICAL: Rebuild selectedAnswer from selectedAnswers array to ensure consistency
    // This prevents any state corruption issues
    if (question.is_multiple_choice) {
        const sorted = [...selectedAnswers].sort();
        selectedAnswer = sorted.join(',');
        console.log('Rebuilt answer from array:', {
            original: selectedAnswer,
            fromArray: selectedAnswer,
            array: selectedAnswers,
            sorted: sorted
        });
    }
    
    // Verify what we're about to submit matches the UI
    const selectedInUI = Array.from(document.querySelectorAll('.option.selected'))
        .map(opt => opt.dataset.letter)
        .sort();
    console.log('Selected in UI:', selectedInUI);
    console.log('Selected in state:', selectedAnswers.sort());
    
    if (question.is_multiple_choice && JSON.stringify(selectedInUI) !== JSON.stringify([...selectedAnswers].sort())) {
        console.error('MISMATCH: UI selections do not match state!');
        console.error('UI:', selectedInUI);
        console.error('State:', selectedAnswers);
        // Fix the state to match UI
        selectedAnswers = [...selectedInUI];
        selectedAnswer = selectedAnswers.sort().join(',');
        console.log('Fixed state to match UI:', selectedAnswer);
    }
    
    // Debug logging
    console.log('Submitting answer:', {
        questionId: question.id,
        selectedAnswer: selectedAnswer,
        selectedAnswers: selectedAnswers,
        isMultiple: question.is_multiple_choice,
        questionText: question.question.substring(0, 50)
    });
    
    try {
        const response = await fetch('/api/submit-answer', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                question_id: question.id,
                answer: selectedAnswer
            })
        });
        
        const feedback = await response.json();
        
        // Store answer
        // Check if this question was already answered
        const wasAlreadyAnswered = answers[currentQuestionIndex] && answers[currentQuestionIndex].answered;
        const wasCorrect = wasAlreadyAnswered ? answers[currentQuestionIndex].correct : false;
        
        // Update answer
        answers[currentQuestionIndex] = {
            answered: true,
            selected: selectedAnswer,
            correct: feedback.is_correct,
            feedback: feedback
        };
        
        // Update score: if it was correct before and now incorrect, decrement
        // If it was incorrect before and now correct, increment
        // If it's a new answer, just increment if correct
        if (wasAlreadyAnswered) {
            if (wasCorrect && !feedback.is_correct) {
                score--; // Was correct, now incorrect
            } else if (!wasCorrect && feedback.is_correct) {
                score++; // Was incorrect, now correct
            }
            // If both correct or both incorrect, no change
        } else {
            // New answer
            if (feedback.is_correct) {
                score++;
            }
        }
        
        displayFeedback(feedback, question);
        updateScore();
        
        // Update option styling
        const correctAnswers = feedback.correct_answer ? feedback.correct_answer.split(',').map(a => a.trim().toUpperCase()) : [];
        const selectedAnswersList = selectedAnswer ? selectedAnswer.split(',').map(a => a.trim().toUpperCase()) : [];
        
        document.querySelectorAll('.option').forEach(opt => {
            opt.classList.remove('selected', 'correct', 'incorrect');
            const letter = opt.dataset.letter.toUpperCase();
            if (correctAnswers.includes(letter)) {
                opt.classList.add('correct');
            } else if (selectedAnswersList.includes(letter) && !feedback.is_correct) {
                opt.classList.add('incorrect');
            }
            // Disable clicking
            opt.style.pointerEvents = 'none';
        });
        
        // Clear selection state after submitting (prevents carryover to next question)
        selectedAnswer = null;
        selectedAnswers = [];
        
        // Clear selection state after submitting (prevents carryover to next question)
        selectedAnswer = null;
        selectedAnswers = [];
        
        // Save progress after answering
        saveProgress();
        
        // Hide submit button and show next button
        document.getElementById('submitBtn').classList.add('hidden');
        if (currentQuestionIndex < questions.length - 1) {
            document.getElementById('nextBtn').classList.remove('hidden');
        } else {
            // Last question - show finish button if all answered
            if (allQuestionsAnswered()) {
                document.getElementById('finishBtn').classList.remove('hidden');
            }
        }
        
    } catch (error) {
        console.error('Error submitting answer:', error);
        showError('Failed to submit answer. Please try again.');
    }
}

function showFeedbackForAnswered() {
    const answer = answers[currentQuestionIndex];
    if (answer.feedback) {
        displayFeedback(answer.feedback, questions[currentQuestionIndex]);
    }
}

function formatMultipleAnswers(answerString, optionText, question) {
    if (!answerString) return '';
    
    // Check if it's multiple answers (comma-separated)
    const answers = answerString.split(',').map(a => a.trim());
    if (answers.length > 1) {
        // Multiple answers - format each one
        const formatted = answers.map(letter => {
            const option = question.options.find(opt => opt.letter.toUpperCase() === letter.toUpperCase());
            return option ? `${letter}) ${option.text}` : letter;
        });
        return formatted.join(', ');
    } else {
        // Single answer
        return `${answerString}) ${optionText}`;
    }
}

function displayFeedback(feedback, question) {
    const feedbackContent = document.getElementById('feedbackContent');
    const answer = answers[currentQuestionIndex];
    
    let html = `
        <div class="feedback-result ${feedback.is_correct ? 'correct' : 'incorrect'}">
            <h3>${feedback.is_correct ? '✓ Correct!' : '✗ Incorrect'}</h3>
            <p><strong>Your answer:</strong> ${formatMultipleAnswers(answer.selected, feedback.selected_option_text, question)}</p>
            <p><strong>Correct answer:</strong> ${formatMultipleAnswers(feedback.correct_answer, feedback.correct_option_text, question)}</p>
        </div>
    `;
    
    // Show concise explanation from study text
    if (feedback.explanation) {
        html += `
            <div class="feedback-explanation">
                <h4>Explanation:</h4>
                <p>${feedback.explanation}</p>
            </div>
        `;
    }
    
    feedbackContent.innerHTML = html;
}

function clearFeedback() {
    document.getElementById('feedbackContent').innerHTML = 
        '<p class="placeholder">Submit an answer to see feedback</p>';
}

function nextQuestion() {
    if (currentQuestionIndex < questions.length - 1) {
        // Clear selection state before moving to next question
        selectedAnswer = null;
        selectedAnswers = [];
        currentQuestionIndex++;
        saveProgress();
        showQuestion();
    }
}

function prevQuestion() {
    if (currentQuestionIndex > 0) {
        // Clear selection state before moving to previous question
        selectedAnswer = null;
        selectedAnswers = [];
        currentQuestionIndex--;
        saveProgress();
        showQuestion();
    }
}

function allQuestionsAnswered() {
    return answers.every(a => a.answered);
}

function updateScore() {
    document.getElementById('score').textContent = score;
    document.getElementById('total').textContent = questions.length;
}

function saveProgress() {
    const progress = {
        questions: questions,
        answers: answers,
        currentQuestionIndex: currentQuestionIndex,
        score: score,
        quizOptions: JSON.parse(sessionStorage.getItem('quizOptions') || '{}')
    };
    localStorage.setItem('quizProgress', JSON.stringify(progress));
}

function restoreProgress() {
    const saved = localStorage.getItem('quizProgress');
    if (saved) {
        try {
            const progress = JSON.parse(saved);
            // Check if quiz options match
            const currentOptions = JSON.parse(sessionStorage.getItem('quizOptions') || '{}');
            const savedOptions = progress.quizOptions || {};
            
            // Only restore if options match
            if (JSON.stringify(currentOptions) === JSON.stringify(savedOptions)) {
                questions = progress.questions || [];
                answers = progress.answers || [];
                currentQuestionIndex = progress.currentQuestionIndex || 0;
                score = progress.score || 0;
                return true;
            }
        } catch (e) {
            console.error('Error restoring progress:', e);
        }
    }
    return false;
}

function finishQuiz() {
    // RECALCULATE score from answers array to ensure accuracy
    // This prevents issues with score being incorrect due to answer changes or restoration
    let calculatedScore = 0;
    answers.forEach(answer => {
        if (answer && answer.correct === true) {
            calculatedScore++;
        }
    });
    
    // Use the recalculated score
    score = calculatedScore;
    
    // Calculate learning objective breakdown
    const loBreakdown = {};
    questions.forEach((q, index) => {
        const lo = q.learning_objective || 'Unknown';
        if (!loBreakdown[lo]) {
            loBreakdown[lo] = { total: 0, correct: 0 };
        }
        loBreakdown[lo].total += 1;
        if (answers[index] && answers[index].correct) {
            loBreakdown[lo].correct += 1;
        }
    });
    
    // Store results in sessionStorage
    const results = {
        total: questions.length,
        correct: score,
        incorrect: questions.length - score,
        percentage: Math.round((score / questions.length) * 100),
        answers: answers,
        questions: questions,
        learning_objective_breakdown: loBreakdown,
        mode: getModeDescription(),
        timestamp: new Date().toISOString()
    };
    
    // Save results to sessionStorage first
    try {
        sessionStorage.setItem('quizResults', JSON.stringify(results));
        console.log('Results saved to sessionStorage');
    } catch (e) {
        console.error('Error saving to sessionStorage:', e);
    }
    
    // Save to server
    fetch('/api/results', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(results)
    }).catch(err => console.error('Error saving results:', err));
    
    // Clear progress
    localStorage.removeItem('quizProgress');
    
    // Small delay to ensure sessionStorage is saved
    setTimeout(() => {
        window.location.href = '/results';
    }, 100);
}

function getModeDescription() {
    const options = JSON.parse(sessionStorage.getItem('quizOptions') || '{}');
    const modSuffix = options.module ? ` · ${options.module}` : '';
    if (options.curve_ball_only) {
        if (options.count) return `${options.count} Curve Ball Questions${modSuffix}`;
        return `All Curve Ball Questions${modSuffix}`;
    }
    if (options.multiple_choice_only) {
        if (options.count) return `${options.count} Multiple Selection Questions${modSuffix}`;
        return `All Multiple Selection Questions${modSuffix}`;
    }
    if (options.count) return `${options.count} Random Questions${modSuffix}`;
    if (options.year) return `${options.year} Past Paper${modSuffix}`;
    if (options.learning_objective) return `Learning Objective ${options.learning_objective}${modSuffix}`;
    return 'Unknown';
}

function showError(message) {
    const feedbackContent = document.getElementById('feedbackContent');
    feedbackContent.innerHTML = `<div class="feedback-result incorrect"><h3>Error</h3><p>${message}</p></div>`;
}

