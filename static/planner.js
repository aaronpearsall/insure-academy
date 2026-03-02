// Exam Planner logic: load/save plan and update credit summaries

let plannerData = { enrolled_units: [], plan: [] };

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
});

function bindPlannerEvents() {
  document.querySelectorAll('button[data-add-row]').forEach(btn => {
    btn.addEventListener('click', () => {
      const level = btn.getAttribute('data-add-row');
      addPlannerRow(level);
    });
  });

  const saveBtn = document.getElementById('savePlannerBtn');
  if (saveBtn) {
    saveBtn.addEventListener('click', savePlanner);
  }
}

async function loadPlanner() {
  try {
    const res = await fetch('/api/planner');
    plannerData = await res.json();
  } catch (e) {
    plannerData = { enrolled_units: [], plan: [] };
  }
  renderPlanner();
}

function renderPlanner() {
  ['certificate', 'diploma', 'advanced'].forEach(level => {
    const bodyId = level === 'certificate' ? 'plannerCertBody'
      : level === 'diploma' ? 'plannerDipBody'
      : 'plannerAdvBody';
    const tbody = document.getElementById(bodyId);
    if (!tbody) return;
    tbody.innerHTML = '';

    const rows = (plannerData.plan || []).filter(row => row.level === level);
    rows.forEach((row, index) => {
      const tr = document.createElement('tr');
      tr.dataset.level = level;
      tr.dataset.index = index.toString();
      tr.innerHTML = `
        <td><input type="text" class="planner-input" value="${row.code || ''}" placeholder="e.g. LM1"></td>
        <td><input type="text" class="planner-input" value="${row.title || ''}" placeholder="Unit title"></td>
        <td><input type="number" min="0" class="planner-input planner-input-small" value="${row.credits != null ? row.credits : ''}"></td>
        <td class="planner-cell-center"><input type="checkbox" ${row.compulsory ? 'checked' : ''}></td>
        <td><input type="date" class="planner-input" value="${row.target_date || ''}"></td>
        <td>
          <select class="planner-input">
            <option value="planned" ${row.status === 'planned' ? 'selected' : ''}>Planned</option>
            <option value="studying" ${row.status === 'studying' ? 'selected' : ''}>Studying</option>
            <option value="booked" ${row.status === 'booked' ? 'selected' : ''}>Booked</option>
            <option value="passed" ${row.status === 'passed' ? 'selected' : ''}>Passed</option>
          </select>
        </td>
        <td class="planner-cell-center">
          <button type="button" class="planner-remove-row" title="Remove row">×</button>
        </td>
      `;
      tbody.appendChild(tr);

      tr.querySelector('.planner-remove-row').addEventListener('click', () => {
        removePlannerRow(level, index);
      });
    });
  });

  updateSummaries();
}

function addPlannerRow(level) {
  if (!plannerData.plan) plannerData.plan = [];
  plannerData.plan.push({
    level,
    code: '',
    title: '',
    credits: null,
    compulsory: false,
    target_date: '',
    status: 'planned',
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
      const code = cells[0].querySelector('input').value.trim();
      const title = cells[1].querySelector('input').value.trim();
      const creditsStr = cells[2].querySelector('input').value.trim();
      const compulsory = cells[3].querySelector('input[type="checkbox"]').checked;
      const targetDate = cells[4].querySelector('input').value;
      const status = cells[5].querySelector('select').value;

      if (!code && !title && !creditsStr && !targetDate) {
        return;
      }

      const credits = creditsStr ? parseInt(creditsStr, 10) : null;
      updatedPlan.push({
        level,
        code,
        title,
        credits: Number.isNaN(credits) ? null : credits,
        compulsory,
        target_date: targetDate,
        status,
      });
    });
  });

  plannerData.plan = updatedPlan;

  // Derive enrolled_units from rows that are actively being studied or booked
  plannerData.enrolled_units = updatedPlan
    .filter(row => row.status === 'studying' || row.status === 'booked')
    .map(row => ({
      code: row.code,
      title: row.title,
      level: row.level,
      credits: row.credits,
      compulsory: row.compulsory,
      target_date: row.target_date,
      status: row.status,
    }));
}

function updateSummaries() {
  const plan = plannerData.plan || [];
  let certCredits = 0;
  let dipTotal = 0;
  let dipLevel4Plus = 0;
  let advCredits = 0;

  plan.forEach(row => {
    const c = row.credits || 0;
    if (!c) return;
    if (row.level === 'certificate') {
      certCredits += c;
    } else if (row.level === 'diploma') {
      dipTotal += c;
      // Treat all diploma entries as diploma-level or above for now
      dipLevel4Plus += c;
    } else if (row.level === 'advanced') {
      advCredits += c;
    }
  });

  const certEl = document.getElementById('summaryCertCredits');
  const dipEl = document.getElementById('summaryDipCredits');
  const advEl = document.getElementById('summaryAdvCredits');

  if (certEl) certEl.textContent = certCredits.toString();
  if (dipEl) dipEl.textContent = `${dipTotal} / ${dipLevel4Plus}`;
  if (advEl) advEl.textContent = advCredits.toString();
}

async function savePlanner() {
  collectPlannerFromDOM();
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

