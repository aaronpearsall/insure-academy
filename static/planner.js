// Exam Planner logic: load/save plan and update credit summaries

let plannerData = { enrolled_units: [], plan: [], exemptions: {} };
let currentView = 'modules';
let calendarDate = new Date();

document.addEventListener('DOMContentLoaded', async () => {
  // Auth check
  try {
    const authRes = await fetch('/api/check-auth');
    const auth = await authRes.json();
    if (!auth.authenticated) {
      window.location.href = '/login';
      return;
    }
  } catch (e) {
    window.location.href = '/login';
    return;
  }

  await loadPlanner();
  bindPlannerEvents();
  bindViewToggle();
  bindCalendarNav();
});

function bindViewToggle() {
  document.querySelectorAll('.planner-view-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const view = btn.getAttribute('data-view');
      setView(view);
    });
  });
}

function setView(view) {
  currentView = view;
  document.querySelectorAll('.planner-view-btn').forEach(b => b.classList.remove('active'));
  const activeBtn = document.querySelector(`.planner-view-btn[data-view="${view}"]`);
  if (activeBtn) activeBtn.classList.add('active');

  const modulesEl = document.getElementById('plannerModulesView');
  const calendarEl = document.getElementById('plannerCalendarView');
  const actionsEl = document.querySelector('.planner-actions');

  if (view === 'modules') {
    if (modulesEl) modulesEl.classList.remove('hidden');
    if (calendarEl) calendarEl.classList.add('hidden');
    if (actionsEl) actionsEl.classList.remove('hidden');
  } else {
    if (modulesEl) modulesEl.classList.add('hidden');
    if (calendarEl) calendarEl.classList.remove('hidden');
    if (actionsEl) actionsEl.classList.add('hidden');
    renderCalendar();
  }
}

function bindCalendarNav() {
  const prevBtn = document.getElementById('calendarPrev');
  const nextBtn = document.getElementById('calendarNext');
  if (prevBtn) prevBtn.addEventListener('click', () => { calendarDate.setMonth(calendarDate.getMonth() - 1); renderCalendar(); });
  if (nextBtn) nextBtn.addEventListener('click', () => { calendarDate.setMonth(calendarDate.getMonth() + 1); renderCalendar(); });
}

function renderCalendar() {
  const titleEl = document.getElementById('calendarTitle');
  const gridEl = document.getElementById('calendarGrid');
  if (!titleEl || !gridEl) return;

  const year = calendarDate.getFullYear();
  const month = calendarDate.getMonth();
  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  titleEl.textContent = `${monthNames[month]} ${year}`;

  const first = new Date(year, month, 1);
  const last = new Date(year, month + 1, 0);
  const startPad = first.getDay();
  const daysInMonth = last.getDate();
  const prevMonthLast = new Date(year, month, 0).getDate();

  const plan = plannerData.plan || [];
  const eventsByDate = {};
  plan.forEach(row => {
    if (!row.target_date) return;
    const [y, m, d] = row.target_date.split('-').map(Number);
    const key = `${y}-${m}-${d}`;
    if (!eventsByDate[key]) eventsByDate[key] = [];
    eventsByDate[key].push({ code: row.code, title: row.title, level: row.level });
  });

  let html = '';

  const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  weekdays.forEach(day => {
    html += `<div class="planner-calendar-day planner-calendar-weekday"><div class="planner-calendar-day-header">${day}</div></div>`;
  });

  for (let i = 0; i < startPad; i++) {
    const d = prevMonthLast - startPad + i + 1;
    html += `<div class="planner-calendar-day other-month"><div class="planner-calendar-day-header">${d}</div></div>`;
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const key = `${year}-${month + 1}-${d}`;
    const events = eventsByDate[key] || [];
    const eventsHtml = events.map(e => {
      const label = (e.code || e.title || 'Exam').substring(0, 12);
      const fullTitle = [e.code, e.title].filter(Boolean).join(' - ');
      return `<div class="planner-calendar-event ${e.level}" title="${fullTitle}">${label}</div>`;
    }).join('');
    html += `<div class="planner-calendar-day"><div class="planner-calendar-day-header">${d}</div>${eventsHtml}</div>`;
  }

  const totalCells = 7 * 6;
  const used = startPad + daysInMonth;
  const nextMonthDays = totalCells - weekdays.length - used;
  for (let i = 1; i <= nextMonthDays; i++) {
    html += `<div class="planner-calendar-day other-month"><div class="planner-calendar-day-header">${i}</div></div>`;
  }

  gridEl.innerHTML = html;
}

function renderExemptions() {
  const ex = plannerData.exemptions || {};
  const certEl = document.getElementById('exemptionCert');
  const dipEl = document.getElementById('exemptionDip');
  const advEl = document.getElementById('exemptionAdv');
  if (certEl) certEl.value = ex.certificate != null ? ex.certificate : '';
  if (dipEl) dipEl.value = ex.diploma != null ? ex.diploma : '';
  if (advEl) advEl.value = ex.advanced != null ? ex.advanced : '';
}

function bindPlannerEvents() {
  populateAddModuleDropdown();
  ['exemptionCert', 'exemptionDip', 'exemptionAdv'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('input', () => {
        const level = id === 'exemptionCert' ? 'certificate' : id === 'exemptionDip' ? 'diploma' : 'advanced';
        const val = parseInt(el.value, 10);
        plannerData.exemptions = plannerData.exemptions || {};
        plannerData.exemptions[level] = isNaN(val) ? 0 : Math.max(0, val);
        updateSummaries();
      });
    }
  });
  const addSelect = document.getElementById('addModuleSelect');
  if (addSelect) {
    addSelect.addEventListener('change', (e) => {
      const val = e.target.value;
      if (!val) return;
      const [level, code] = val.split(':');
      if (level && code) {
        addPlannerRow(level, code);
        e.target.value = '';
      }
    });
  }

  const saveBtn = document.getElementById('savePlannerBtn');
  if (saveBtn) {
    saveBtn.addEventListener('click', savePlanner);
  }
}

function populateAddModuleDropdown() {
  if (typeof CII_UNITS === 'undefined') return;
  const select = document.getElementById('addModuleSelect');
  if (!select) return;

  const certGroup = select.querySelector('optgroup[label="Certificate (Level 3)"]');
  const dipGroup = select.querySelector('optgroup[label="Diploma (Level 4)"]');
  const advGroup = select.querySelector('optgroup[label="Advanced Diploma (Level 6+)"]');

  [certGroup, dipGroup, advGroup].forEach(g => { if (g) g.innerHTML = ''; });

  (CII_UNITS.certificate || []).forEach(u => {
    const opt = document.createElement('option');
    opt.value = `certificate:${u.code}`;
    opt.textContent = `${u.code} – ${u.title} (${u.credits} cr)`;
    if (certGroup) certGroup.appendChild(opt);
  });
  (CII_UNITS.diploma || []).forEach(u => {
    const opt = document.createElement('option');
    opt.value = `diploma:${u.code}`;
    opt.textContent = `${u.code} – ${u.title} (${u.credits} cr)`;
    if (dipGroup) dipGroup.appendChild(opt);
  });
  (CII_UNITS.advanced || []).forEach(u => {
    const opt = document.createElement('option');
    opt.value = `advanced:${u.code}`;
    opt.textContent = `${u.code} – ${u.title} (${u.credits} cr)`;
    if (advGroup) advGroup.appendChild(opt);
  });
}

async function loadPlanner() {
  try {
    const res = await fetch('/api/planner');
    plannerData = await res.json();
    plannerData.exemptions = plannerData.exemptions || {};
  } catch (e) {
    plannerData = { enrolled_units: [], plan: [], exemptions: {} };
  }
  renderPlanner();
  renderExemptions();
}

function getUnitByCode(level, code) {
  if (typeof CII_UNITS === 'undefined') return null;
  const list = CII_UNITS[level] || [];
  return list.find(u => u.code === code);
}

function renderPlanner() {
  if (typeof CII_UNITS === 'undefined') {
    console.error('CII_UNITS not loaded - ensure cii_units.js loads before planner.js');
    return;
  }
  ['certificate', 'diploma', 'advanced'].forEach(level => {
    const bodyId = level === 'certificate' ? 'plannerCertBody'
      : level === 'diploma' ? 'plannerDipBody'
      : 'plannerAdvBody';
    const tbody = document.getElementById(bodyId);
    if (!tbody) return;
    tbody.innerHTML = '';

    const units = CII_UNITS[level] || [];
    const rows = (plannerData.plan || []).filter(row => row.level === level);

    rows.forEach((row, index) => {
      const unit = getUnitByCode(level, row.code);
      const tr = document.createElement('tr');
      tr.dataset.level = level;
      tr.dataset.index = index.toString();

      const unitOptions = units.map(u =>
        `<option value="${u.code}" ${row.code === u.code ? 'selected' : ''}>${u.code} – ${u.title} (${u.credits} cr, ${u.studyHours} hrs)</option>`
      ).join('');
      const selectHtml = `<select class="planner-input planner-unit-select">
        <option value="">-- Select unit --</option>
        ${unitOptions}
      </select>`;

      const credits = unit ? unit.credits : (row.credits != null ? row.credits : '');
      const studyHours = unit ? unit.studyHours : (row.study_hours != null ? row.study_hours : '');
      const isDone = row.status === 'passed';

      tr.classList.toggle('planner-row-done', isDone);

      const tickHtml = `<button type="button" class="planner-tick ${isDone ? 'planner-tick-done' : ''}" title="${isDone ? 'Mark incomplete' : 'Mark complete'}">
        <svg class="planner-tick-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          ${isDone ? '<polyline points="9 12 11 14 15 10"/>' : ''}
        </svg>
      </button>`;

      tr.innerHTML = `
        <td>${selectHtml}</td>
        <td class="planner-cell-credits">${credits}</td>
        <td class="planner-cell-hours">${studyHours}</td>
        <td><input type="date" class="planner-input" value="${row.target_date || ''}"></td>
        <td class="planner-cell-center">${tickHtml}</td>
        <td class="planner-cell-center">
          <button type="button" class="planner-remove-row" title="Remove row">×</button>
        </td>
      `;
      tbody.appendChild(tr);

      tr.querySelector('.planner-tick').addEventListener('click', () => {
        row.status = row.status === 'passed' ? 'planned' : 'passed';
        tr.classList.toggle('planner-row-done', row.status === 'passed');
        tr.querySelector('.planner-tick').classList.toggle('planner-tick-done', row.status === 'passed');
        tr.querySelector('.planner-tick-svg').innerHTML = row.status === 'passed' ? '<circle cx="12" cy="12" r="10"/><polyline points="9 12 11 14 15 10"/>' : '<circle cx="12" cy="12" r="10"/>';
        updateSummaries();
      });

      tr.querySelector('.planner-unit-select').addEventListener('change', (e) => {
        const code = e.target.value;
        const u = getUnitByCode(level, code);
        if (u) {
          tr.querySelector('.planner-cell-credits').textContent = u.credits;
          tr.querySelector('.planner-cell-hours').textContent = u.studyHours;
        }
        row.code = code;
        row.credits = u ? u.credits : null;
        row.title = u ? u.title : '';
        row.study_hours = u ? u.studyHours : null;
        updateSummaries();
      });

      tr.querySelector('.planner-remove-row').addEventListener('click', () => {
        removePlannerRow(level, index);
      });
    });
  });

  updateSummaries();
}

function addPlannerRow(level, code) {
  if (!plannerData.plan) plannerData.plan = [];
  const unit = getUnitByCode(level, code || '');
  plannerData.plan.push({
    level,
    code: code || '',
    title: unit ? unit.title : '',
    credits: unit ? unit.credits : null,
    study_hours: unit ? unit.studyHours : null,
    target_date: '',
    status: 'planned',  // ticked = 'passed'
  });
  renderPlanner();
}

function removePlannerRow(level, index) {
  if (!plannerData.plan) return;
  let seen = -1;
  plannerData.plan = plannerData.plan.filter(row => {
    if (row.level !== level) return true;
    seen += 1;
    return seen !== index;
  });
  renderPlanner();
}

function collectExemptions() {
  const certEl = document.getElementById('exemptionCert');
  const dipEl = document.getElementById('exemptionDip');
  const advEl = document.getElementById('exemptionAdv');
  plannerData.exemptions = plannerData.exemptions || {};
  plannerData.exemptions.certificate = Math.max(0, parseInt(certEl?.value || '0', 10) || 0);
  plannerData.exemptions.diploma = Math.max(0, parseInt(dipEl?.value || '0', 10) || 0);
  plannerData.exemptions.advanced = Math.max(0, parseInt(advEl?.value || '0', 10) || 0);
}

function collectPlannerFromDOM() {
  const updatedPlan = [];

  ['certificate', 'diploma', 'advanced'].forEach(level => {
    const bodyId = level === 'certificate' ? 'plannerCertBody'
      : level === 'diploma' ? 'plannerDipBody'
      : 'plannerAdvBody';
    const tbody = document.getElementById(bodyId);
    if (!tbody) return;

    tbody.querySelectorAll('tr').forEach(tr => {
      const cells = tr.querySelectorAll('td');
      const code = (cells[0].querySelector('select')?.value || '').trim();
      const creditsEl = cells[1];
      const hoursEl = cells[2];
      const credits = parseInt(creditsEl?.textContent || '0', 10) || null;
      const studyHours = parseInt(hoursEl?.textContent || '0', 10) || null;
      const targetDate = cells[3]?.querySelector('input')?.value || '';
      const isDone = tr.querySelector('.planner-tick')?.classList.contains('planner-tick-done');
      const status = isDone ? 'passed' : 'planned';

      const unit = getUnitByCode(level, code);
      updatedPlan.push({
        level,
        code,
        title: unit ? unit.title : '',
        credits: unit ? unit.credits : credits,
        study_hours: unit ? unit.studyHours : studyHours,
        target_date: targetDate,
        status,
      });
    });
  });

  plannerData.plan = updatedPlan;

  plannerData.enrolled_units = updatedPlan
    .filter(row => row.status !== 'passed' && row.code)
    .map(row => ({
      code: row.code,
      title: row.title,
      level: row.level,
      credits: row.credits,
      target_date: row.target_date,
      status: row.status,
    }));
}

function updateSummaries() {
  if (typeof QUALIFICATION_RULES === 'undefined') return;
  const plan = plannerData.plan || [];
  const withCode = plan.filter(r => r.code);
  const passed = plan.filter(r => r.status === 'passed' && r.code);

  const certPassed = passed.filter(r => r.level === 'certificate');
  const dipPassed = passed.filter(r => r.level === 'diploma');
  const advPassed = passed.filter(r => r.level === 'advanced');

  const ex = plannerData.exemptions || {};
  const certExempt = parseInt(ex.certificate, 10) || 0;
  const dipExempt = parseInt(ex.diploma, 10) || 0;
  const advExempt = parseInt(ex.advanced, 10) || 0;

  // Total credits from ALL added units + exemptions
  const certUnitCredits = withCode.filter(r => r.level === 'certificate').reduce((s, r) => s + (r.credits || 0), 0);
  const dipPlanCredits = withCode.filter(r => r.level === 'diploma').reduce((s, r) => s + (r.credits || 0), 0);
  const advPlanCredits = withCode.filter(r => r.level === 'advanced').reduce((s, r) => s + (r.credits || 0), 0);
  const certTotalCredits = certUnitCredits + certExempt;
  const dipTotalCredits = certTotalCredits + dipPlanCredits + dipExempt;
  const advTotalCredits = certTotalCredits + dipPlanCredits + advPlanCredits + advExempt;

  // Criteria met: passed units + exemptions
  const certPassedCredits = certPassed.reduce((s, r) => s + (r.credits || 0), 0);
  const dipPassedCredits = dipPassed.reduce((s, r) => s + (r.credits || 0), 0);
  const advPassedCredits = advPassed.reduce((s, r) => s + (r.credits || 0), 0);
  const certTotalForCriteria = certPassedCredits + certExempt;
  const dipTotalForCriteria = certTotalForCriteria + dipPassedCredits + dipExempt;
  const advTotalForCriteria = dipTotalForCriteria + advPassedCredits + advExempt;
  const dipLevel4PlusCredits = dipPassedCredits + advPassedCredits + dipExempt + advExempt;
  const advLevel4PlusCredits = dipPassedCredits + advPassedCredits + dipExempt + advExempt;
  const advLevel6Credits = advPassedCredits + advExempt;

  const certMet = QUALIFICATION_RULES.certificate;
  const certCoreOk = certMet.checkCore(certPassed);
  const certCriteriaMet = certTotalForCriteria >= certMet.minCredits && certCoreOk;

  const dipMet = QUALIFICATION_RULES.diploma;
  const dipCoreOk = dipMet.checkCore([...dipPassed, ...advPassed]); // 530 is in advanced
  const dipCriteriaMet = dipTotalForCriteria >= dipMet.minTotal && dipLevel4PlusCredits >= dipMet.minDiplomaPlus && dipCoreOk;

  const advMet = QUALIFICATION_RULES.advanced;
  const allPassed = [...certPassed, ...dipPassed, ...advPassed];
  const advCoreOk = advMet.checkCore(allPassed);
  const advCriteriaMet = advTotalForCriteria >= advMet.minTotal && advLevel6Credits >= advMet.minAdvanced && advLevel4PlusCredits >= advMet.minDiplomaPlus && advCoreOk;

  const certEl = document.getElementById('summaryCertCredits');
  const dipEl = document.getElementById('summaryDipCredits');
  const advEl = document.getElementById('summaryAdvCredits');
  const certMetEl = document.getElementById('summaryCertMet');
  const dipMetEl = document.getElementById('summaryDipMet');
  const advMetEl = document.getElementById('summaryAdvMet');

  if (certEl) certEl.textContent = `${certTotalCredits}/40`;
  if (dipEl) dipEl.textContent = `${dipTotalCredits}/120`;
  if (advEl) advEl.textContent = `${advTotalCredits}/290`;

  if (certMetEl) {
    certMetEl.innerHTML = certCriteriaMet
      ? '<span class="planner-met planner-met-yes">✓ Criteria met</span>'
      : '<span class="planner-met planner-met-no">✗ Criteria not met</span>';
  }
  if (dipMetEl) {
    dipMetEl.innerHTML = dipCriteriaMet
      ? '<span class="planner-met planner-met-yes">✓ Criteria met</span>'
      : '<span class="planner-met planner-met-no">✗ Criteria not met</span>';
  }
  if (advMetEl) {
    advMetEl.innerHTML = advCriteriaMet
      ? '<span class="planner-met planner-met-yes">✓ Criteria met</span>'
      : '<span class="planner-met planner-met-no">✗ Criteria not met</span>';
  }
}

async function savePlanner() {
  collectPlannerFromDOM();
  collectExemptions();
  const statusEl = document.getElementById('plannerSaveStatus');
  if (statusEl) {
    statusEl.textContent = 'Saving...';
  }
  try {
    const res = await fetch('/api/planner', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(plannerData),
    });
    if (!res.ok) throw new Error('Save failed');
    if (statusEl) {
      statusEl.textContent = 'Saved';
      setTimeout(() => { statusEl.textContent = ''; }, 2000);
    }
  } catch (e) {
    if (statusEl) {
      statusEl.textContent = 'Error saving plan';
    }
  }
}

