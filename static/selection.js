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
    loadDashboardSummary();
    loadCurrentUnits();
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

    const wrongBtn = document.getElementById('wrongQuestionsBtn');
    if (wrongBtn) {
        wrongBtn.addEventListener('click', () => {
            selectQuizMode({ wrong_questions_only: true, module: currentModule }, wrongBtn);
        });
    }

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

async function loadDashboardSummary() {
  const designationEl = document.getElementById('dashboardDesignation');
  const enrolledEl = document.getElementById('dashboardEnrolled');
  const daysEl = document.getElementById('dashboardDaysUntil');
  if (!designationEl && !enrolledEl && !daysEl) return;

  try {
    const res = await fetch('/api/planner');
    const data = await res.json();
    const plan = data.plan || [];
    const enrolled = (data.enrolled_units || []).filter(u => u && (u.code || u.title));

    // Designation: highest achieved (ACII > DipCII > Cert CII)
    let designation = '—';
    if (typeof QUALIFICATION_RULES !== 'undefined') {
      const passed = plan.filter(r => r.status === 'passed' && r.code);
      const certPassed = passed.filter(r => r.level === 'certificate');
      const dipPassed = passed.filter(r => r.level === 'diploma');
      const advPassed = passed.filter(r => r.level === 'advanced');
      const ex = data.exemptions || {};
      const certExempt = parseInt(ex.certificate, 10) || 0;
      const dipExempt = parseInt(ex.diploma, 10) || 0;
      const advExempt = parseInt(ex.advanced, 10) || 0;

      const certCredits = certPassed.reduce((s, r) => s + (r.credits || 0), 0);
      const dipCredits = dipPassed.reduce((s, r) => s + (r.credits || 0), 0);
      const advCredits = advPassed.reduce((s, r) => s + (r.credits || 0), 0);
      const certTotal = certCredits + certExempt;
      const dipTotal = certTotal + dipCredits + dipExempt;
      const advTotal = dipTotal + advCredits + advExempt;
      const dipLevel4Plus = dipCredits + advCredits + dipExempt + advExempt;
      const advLevel6Credits = advCredits + advExempt;

      const certMet = certTotal >= QUALIFICATION_RULES.certificate.minCredits && QUALIFICATION_RULES.certificate.checkCore(certPassed);
      const dipMet = dipTotal >= QUALIFICATION_RULES.diploma.minTotal && dipLevel4Plus >= QUALIFICATION_RULES.diploma.minDiplomaPlus && QUALIFICATION_RULES.diploma.checkCore([...dipPassed, ...advPassed]);
      const allPassed = [...certPassed, ...dipPassed, ...advPassed];
      const advMet = advTotal >= QUALIFICATION_RULES.advanced.minTotal && advLevel6Credits >= QUALIFICATION_RULES.advanced.minAdvanced && dipLevel4Plus >= QUALIFICATION_RULES.advanced.minDiplomaPlus && QUALIFICATION_RULES.advanced.checkCore(allPassed);

      if (advMet) designation = 'ACII';
      else if (dipMet) designation = 'DipCII';
      else if (certMet) designation = 'Cert CII';
    }

    if (designationEl) designationEl.textContent = designation;

    // Currently enrolled: unit codes (e.g. LM1, LM2)
    if (enrolledEl) {
      enrolledEl.textContent = enrolled.length ? enrolled.map(u => u.code || u.title).join(', ') : '—';
    }

    // Days until next assessment: soonest future target_date among plan items
    if (daysEl) {
      const dates = plan.filter(r => r.target_date).map(r => r.target_date);
      if (!dates.length) {
        daysEl.textContent = '—';
      } else {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        let minDays = null;
        dates.forEach(dStr => {
          const d = new Date(dStr);
          d.setHours(0, 0, 0, 0);
          const diff = Math.ceil((d - today) / (1000 * 60 * 60 * 24));
          if (diff >= 0 && (minDays === null || diff < minDays)) minDays = diff;
          else if (diff < 0 && minDays === null) minDays = diff;
        });
        if (minDays === null) daysEl.textContent = '—';
        else if (minDays < 0) daysEl.textContent = 'Past due';
        else if (minDays === 0) daysEl.textContent = 'Today';
        else if (minDays === 1) daysEl.textContent = '1 day';
        else daysEl.textContent = `${minDays} days`;
      }
    }
  } catch (e) {
    if (designationEl) designationEl.textContent = '—';
    if (enrolledEl) enrolledEl.textContent = '—';
    if (daysEl) daysEl.textContent = '—';
  }
}

async function loadCurrentUnits() {
  const container = document.getElementById('currentUnitsList');
  if (!container) return;
  try {
    const res = await fetch('/api/planner');
    const data = await res.json();
    const units = (data.enrolled_units || []).filter(u => u && (u.code || u.title));
    if (!units.length) {
      container.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">No units marked as studying or booked yet. Use the Exam Planner to add your units.</span>';
      return;
    }
    container.innerHTML = units.map(u => {
      const code = u.code || '';
      const title = u.title || '';
      const level = u.level || '';
      const credits = u.credits != null ? `${u.credits} credits` : '';
      const when = u.target_date ? `Target: ${u.target_date}` : '';
      const meta = [level, credits, when].filter(Boolean).join(' · ');
      return `<div class="current-unit-row">
        <div class="current-unit-main">
          <div class="current-unit-code">${code}</div>
          <div class="current-unit-title">${title}</div>
        </div>
        <div class="current-unit-meta">${meta}</div>
      </div>`;
    }).join('');
  } catch (e) {
    container.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">Unable to load units.</span>';
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
    loadWrongQuestionsCount(moduleParam);
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

async function loadWrongQuestionsCount(moduleParam = '') {
    if (!currentModule) return;
    try {
        const res = await fetch(`/api/wrong-questions-count${moduleParam}`);
        if (!res.ok) return;
        const data = await res.json();
        const count = data.count || 0;

        const wrongBtn = document.getElementById('wrongQuestionsBtn');
        if (wrongBtn) {
            wrongBtn.textContent = count === 0 ? '0 in stack' : `Practice ${count} in stack`;
            wrongBtn.disabled = count === 0;
        }
    } catch (e) {
        console.error('Error loading wrong questions count:', e);
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

    if (options.wrong_questions_only) {
        modeText = 'Review Stack';
        detailText = 'Questions you got wrong';
    } else if (options.curve_ball_only) {
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
