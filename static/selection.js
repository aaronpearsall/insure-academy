// Selection page logic - v5 (LM1/LM2 only; no mixing)
let selectedOptions = null;
let currentModule = null;  // always LM1 or LM2 once loaded

document.addEventListener('DOMContentLoaded', async () => {
    try {
        const authResponse = await fetch('/api/check-auth');
        const authData = await authResponse.json();
        if (!authData.authenticated) {
            window.location.href = '/login';
            return;
        }
    } catch (error) {
        window.location.href = '/login';
        return;
    }

    loadStats();
    await loadModules();

    // After modules load, currentModule is set to first (LM1); refresh data for it
    refreshModuleData();

    document.querySelectorAll('.quiz-btn[data-mode="count"]').forEach(btn => {
        btn.addEventListener('click', () => {
            selectQuizMode({ count: parseInt(btn.dataset.value), module: currentModule }, btn);
        });
    });

    document.querySelectorAll('.quiz-btn[data-mode="multiple"]').forEach(btn => {
        btn.addEventListener('click', () => {
            const val = btn.dataset.value;
            const opts = { multiple_choice_only: true, module: currentModule };
            if (val !== 'all') opts.count = parseInt(val);
            selectQuizMode(opts, btn);
        });
    });

    document.querySelectorAll('.quiz-btn[data-mode="curveball"]').forEach(btn => {
        btn.addEventListener('click', () => {
            const val = btn.dataset.value;
            const opts = { curve_ball_only: true, module: currentModule };
            if (val !== 'all') opts.count = parseInt(val);
            selectQuizMode(opts, btn);
        });
    });

    document.getElementById('startQuizBtn').addEventListener('click', () => {
        if (selectedOptions) startQuiz(selectedOptions);
    });

    document.getElementById('changeSelectionBtn').addEventListener('click', clearSelection);
});

async function loadStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        document.getElementById('statTotalQuestions').textContent = data.total_questions.toLocaleString();
        document.getElementById('statModules').textContent = data.total_modules;
        document.getElementById('statQuizzes').textContent = data.quizzes_completed;
        document.getElementById('statAvgScore').textContent = data.quizzes_completed > 0 ? data.avg_score + '%' : '—';
    } catch (e) {
        console.error('Error loading stats:', e);
    }
}

async function loadModules() {
    try {
        const res = await fetch('/api/modules');
        const modules = await res.json();

        const container = document.getElementById('moduleTabs');
        container.innerHTML = '';

        if (modules.length === 0) {
            container.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">No modules. Add exam_papers/LM1 and exam_papers/LM2.</span>';
            return;
        }

        modules.forEach((mod, index) => {
            const btn = document.createElement('button');
            btn.className = 'module-tab' + (index === 0 ? ' active' : '');
            btn.dataset.module = mod.code;
            btn.textContent = mod.code;
            btn.addEventListener('click', () => selectModule(mod.code, btn));
            container.appendChild(btn);
            if (index === 0) currentModule = mod.code;
        });

        // Hide Multiple Selection section for LM1 (no multiple selection in that module)
        const multipleSection = document.getElementById('multipleSelectionSection');
        if (multipleSection) {
            if (currentModule === 'LM1') {
                multipleSection.classList.add('hidden');
            } else {
                multipleSection.classList.remove('hidden');
            }
        }
    } catch (e) {
        console.error('Error loading modules:', e);
    }
}

function selectModule(moduleCode, clickedBtn) {
    currentModule = moduleCode;
    document.querySelectorAll('.module-tab').forEach(t => t.classList.remove('active'));
    clickedBtn.classList.add('active');
    clearSelection();
    refreshModuleData();
}

function refreshModuleData() {
    if (!currentModule) return;
    const moduleParam = `?module=${encodeURIComponent(currentModule)}`;
    loadAvailableYears(moduleParam);
    loadLearningObjectives(moduleParam);
    loadMultipleChoiceCount(moduleParam);
    loadCurveBallCount(moduleParam);
    // LM1 has no multiple selection questions; only show for other modules (e.g. M05)
    const multipleSection = document.getElementById('multipleSelectionSection');
    if (multipleSection) {
        if (currentModule === 'LM1') {
            multipleSection.classList.add('hidden');
        } else {
            multipleSection.classList.remove('hidden');
        }
    }
}

async function loadAvailableYears(moduleParam = '') {
    const yearButtons = document.getElementById('yearButtons');
    yearButtons.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">Loading…</span>';

    try {
        const res = await fetch(`/api/years${moduleParam}`);
        const years = await res.json();
        yearButtons.innerHTML = '';

        if (years.length === 0) {
            yearButtons.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">No years found for this module</span>';
            return;
        }

        years.forEach(year => {
            const btn = document.createElement('button');
            btn.className = 'quiz-btn';
            btn.dataset.year = year;
            btn.textContent = year;
            btn.addEventListener('click', () => {
                selectQuizMode({ year: parseInt(year), module: currentModule }, btn);
            });
            yearButtons.appendChild(btn);
        });
    } catch (e) {
        yearButtons.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">Error loading years</span>';
    }
}

async function loadLearningObjectives(moduleParam = '') {
    const loButtons = document.getElementById('learningObjectiveButtons');
    loButtons.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">Loading…</span>';

    try {
        const res = await fetch(`/api/learning-objectives${moduleParam}`);
        const objectives = await res.json();
        loButtons.innerHTML = '';

        if (objectives.length === 0) {
            loButtons.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">No objectives found for this module</span>';
            return;
        }

        objectives.forEach(obj => {
            const btn = document.createElement('button');
            btn.className = 'quiz-btn';
            btn.dataset.lo = obj.number;
            btn.textContent = `LO ${obj.number}`;
            btn.title = `${obj.count} questions`;
            btn.addEventListener('click', () => {
                selectQuizMode({ learning_objective: obj.number, module: currentModule }, btn);
            });
            loButtons.appendChild(btn);
        });
    } catch (e) {
        loButtons.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">Error loading objectives</span>';
    }
}

async function loadMultipleChoiceCount(moduleParam = '') {
    if (!currentModule) return;
    try {
        const res = await fetch(`/api/multiple-choice-count${moduleParam}`);
        const data = await res.json();
        const count = data.count || 0;

        document.querySelectorAll('.quiz-btn[data-mode="multiple"]').forEach(btn => {
            const val = btn.dataset.value;
            if (val === 'all') {
                btn.textContent = `All (${count})`;
                btn.disabled = count === 0;
            } else {
                const max = Math.min(parseInt(val), count);
                btn.textContent = `${max} Questions`;
                btn.disabled = count === 0;
            }
        });
    } catch (e) {
        console.error('Error loading multiple choice count:', e);
    }
}

async function loadCurveBallCount(moduleParam = '') {
    if (!currentModule) return;
    try {
        const res = await fetch(`/api/curve-ball-count${moduleParam}`);
        if (!res.ok) return;
        const data = await res.json();
        const count = data.count || 0;

        document.querySelectorAll('.quiz-btn[data-mode="curveball"]').forEach(btn => {
            const val = btn.dataset.value;
            if (val === 'all') {
                btn.textContent = `All (${count})`;
                btn.disabled = count === 0;
            } else {
                const max = Math.min(parseInt(val), count);
                btn.textContent = `${max} Questions`;
                btn.disabled = count === 0;
            }
        });
    } catch (e) {
        console.error('Error loading curve ball count:', e);
    }
}

function selectQuizMode(options, clickedButton) {
    selectedOptions = options;
    document.querySelectorAll('.quiz-btn').forEach(b => b.classList.remove('selected'));
    clickedButton.classList.add('selected');
    showConfirmation(options);
}

function showConfirmation(options) {
    const confirmation = document.getElementById('selectionConfirmation');
    const selectedInfo = document.getElementById('selectedInfo');

    let modeText = '';
    let detailText = '';

    if (options.curve_ball_only) {
        modeText = 'Curve Ball Questions';
        detailText = options.count ? `${options.count} questions` : 'All available';
    } else if (options.multiple_choice_only) {
        modeText = 'Multiple Selection Questions';
        detailText = options.count ? `${options.count} questions` : 'All available';
    } else if (options.year) {
        modeText = 'Past Paper';
        detailText = `${options.year} exam`;
    } else if (options.learning_objective) {
        modeText = 'Learning Objective';
        detailText = `LO ${options.learning_objective}`;
    } else if (options.count) {
        modeText = 'Random Practice';
        detailText = `${options.count} questions`;
    }

    if (options.module) {
        detailText += ` · ${options.module}`;
    }

    selectedInfo.innerHTML = `
        <span class="selected-label">${modeText}</span>
        <span class="selected-value">${detailText}</span>
    `;

    confirmation.classList.remove('hidden');
    confirmation.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function clearSelection() {
    selectedOptions = null;
    document.querySelectorAll('.quiz-btn').forEach(b => b.classList.remove('selected'));
    document.getElementById('selectionConfirmation').classList.add('hidden');
}

function startQuiz(options) {
    sessionStorage.setItem('quizOptions', JSON.stringify(options));
    window.location.href = '/quiz';
}
