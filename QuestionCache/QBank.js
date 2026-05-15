const STORAGE_KEY = 'apphys2_qbank_v1';
let questions = [];
let editingId = null;
let correctAnswer = '';

const SKILL_HINTS = {
  '2A': {
    label: '2.A — Derive',
    stem: 'Which of the following correctly expresses [unknown] in terms of [given variables]?',
    variants: [
      'A student derives an expression for [X]. Which is correct?',
      'Using only the quantities shown, which expression gives [X]?',
      'Two students write different expressions for [X]. Which is valid?'
    ]
  },
  '2B': {
    label: '2.B — Calculate / estimate',
    stem: 'A [system] has [given values with units]. What is [unknown]?',
    variants: [
      'What is the approximate value of [X]?',
      'Which of the following is closest to [X]?',
      'Based on the diagram/table, what is [X]?'
    ]
  },
  '2C': {
    label: '2.C — Compare',
    stem: 'In Situation 1, [setup A]. In Situation 2, [setup B]. How does [quantity] compare?',
    variants: [
      'As [variable] increases from A to B, what happens to [quantity]?',
      'Rank the following [quantities] from greatest to least.',
      'What is the ratio of [X₁] to [X₂]?'
    ]
  },
  '2D': {
    label: '2.D — Predict change',
    stem: 'If [variable] is [doubled/tripled/halved], by what factor does [quantity] change?',
    variants: [
      'A student triples [X]. What happens to [Y]?',
      'Which change to [variable] would cause [Y] to double?',
      'A new planet has [mass/radius] twice Earth\'s. How does [g] compare?'
    ]
  },
  '3B': {
    label: '3.B — Apply claim',
    stem: 'Which of the following best explains why [phenomenon] occurs?',
    variants: [
      'A student claims [X]. Is the student correct, and why?',
      'Which law or principle best supports the claim that [X]?',
      'A student argues [argument]. Which identifies the flaw?'
    ]
  },
  '3C': {
    label: '3.C — Justify with evidence',
    stem: 'Which of the following [graphs / data / observations] best supports the claim that [physics claim]?',
    variants: [
      '[Data table]. Which conclusion is best supported?',
      'Which graph would be expected if [claim] is true?',
      'The data below is most consistent with which model?'
    ]
  }
};

const LATEX_FIELDS = ['stem', 'A', 'B', 'C', 'D'];

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      questions = JSON.parse(raw);
    }
  } catch (error) {
    questions = [];
  }
  updateSidebarCount();
}

function saveToStorage() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(questions));
  } catch (error) {
    // ignore storage write errors
  }
  updateSidebarCount();
}

function updateSidebarCount() {
  const countEl = document.getElementById('sidebar-total');
  if (countEl) {
    countEl.textContent = questions.length.toString();
  }
}

function showView(view) {
  ['add', 'bank', 'track', 'ref'].forEach(id => {
    const page = document.getElementById(`view-${id}`);
    const nav = document.getElementById(`nav-${id}`);
    if (page) page.classList.toggle('active', id === view);
    if (nav) nav.classList.toggle('active', id === view);
  });

  const titleMap = {
    add: 'Add a question',
    bank: 'Browse questions',
    track: 'Coverage tracker',
    ref: 'Question writing guide'
  };

  const topTitle = document.querySelector(`#view-${view} .topbar-title`);
  if (topTitle) topTitle.textContent = titleMap[view] || '';

  if (view === 'bank') {
    renderBank();
  }
  if (view === 'track') {
    renderTracker();
  }
}

function updateSkillHint() {
  const skill = document.getElementById('f-skill').value;
  const hint = document.getElementById('skill-hint');

  if (!skill || !SKILL_HINTS[skill]) {
    hint.classList.remove('visible');
    return;
  }

  const data = SKILL_HINTS[skill];
  document.getElementById('sh-label').textContent = data.label;
  document.getElementById('sh-stem').innerHTML = data.stem.replace(/\[([^\]]+)\]/g, '<em>[$1]</em>');
  document.getElementById('sh-variants').innerHTML = data.variants.map(item => `<li>${item}</li>`).join('');
  hint.classList.add('visible');
}

function renderLatexFragment(text) {
  const fragment = document.createDocumentFragment();
  const regex = /\$\$([\s\S]+?)\$\$|\$([^\$\n]+?)\$/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
    }

    const content = match[1] !== undefined ? match[1] : match[2];
    const displayMode = match[1] !== undefined;
    const span = document.createElement('span');

    try {
      katex.render(content, span, { throwOnError: false, displayMode });
    } catch (error) {
      span.textContent = match[0];
    }

    fragment.appendChild(span);
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
  }

  return fragment;
}

function renderFieldMath(fieldKey) {
  const input = document.getElementById(`f-${fieldKey}`);
  const preview = document.getElementById(`p-${fieldKey}`);
  if (!input || !preview) return;

  const value = input.value || '';
  const hasDollar = value.includes('$');

  if (!hasDollar) {
    preview.classList.remove('visible');
    return;
  }

  preview.innerHTML = '';
  preview.appendChild(renderLatexFragment(value));
  preview.classList.add('visible');
}

function attachLatexEditor(fieldKey) {
  const input = document.getElementById(`f-${fieldKey}`);
  const preview = document.getElementById(`p-${fieldKey}`);
  if (!input || !preview) return;

  input.addEventListener('input', () => renderFieldMath(fieldKey));
  renderFieldMath(fieldKey);
}

function selectCorrect(letter) {
  correctAnswer = letter;
  ['A', 'B', 'C', 'D'].forEach(option => {
    const button = document.getElementById(`cb-${option}`);
    if (button) {
      button.className = 'choice-letter' + (option === letter ? ' sel-ans' : '');
    }
  });
}

function clearForm() {
  ['f-unit', 'f-skill', 'f-stimulus', 'f-difficulty', 'f-stem', 'f-A', 'f-B', 'f-C', 'f-D', 'f-notes'].forEach(id => {
    const element = document.getElementById(id);
    if (element) element.value = '';
  });

  correctAnswer = '';
  editingId = null;
  ['A', 'B', 'C', 'D'].forEach(option => {
    const button = document.getElementById(`cb-${option}`);
    if (button) button.className = 'choice-letter';
  });

  const editPill = document.getElementById('edit-pill');
  if (editPill) {
    editPill.style.display = 'none';
  }

  const skillHint = document.getElementById('skill-hint');
  if (skillHint) skillHint.classList.remove('visible');

  LATEX_FIELDS.forEach(renderFieldMath);
}

function showSaveMsg(message) {
  const messageElement = document.getElementById('save-msg');
  if (!messageElement) return;
  messageElement.textContent = message;
  messageElement.classList.add('show');
  window.setTimeout(() => messageElement.classList.remove('show'), 2000);
}

function saveQuestion() {
  const unit = document.getElementById('f-unit').value;
  const skill = document.getElementById('f-skill').value;
  const stem = document.getElementById('f-stem').value.trim();
  const A = document.getElementById('f-A').value.trim();
  const B = document.getElementById('f-B').value.trim();
  const C = document.getElementById('f-C').value.trim();
  const D = document.getElementById('f-D').value.trim();
  const stimulus = document.getElementById('f-stimulus').value;
  const difficulty = document.getElementById('f-difficulty').value;
  const notes = document.getElementById('f-notes').value.trim();

  if (!unit || !skill || !stem || !A || !B || !C || !D || !correctAnswer) {
    showSaveMsg('Please fill in all required fields.');
    return;
  }

  const question = {
    id: editingId || Date.now().toString(),
    unit,
    skill,
    stimulus,
    difficulty,
    stem,
    A,
    B,
    C,
    D,
    correct: correctAnswer,
    notes,
    date: editingId ? (questions.find(item => item.id === editingId) || {}).date || new Date().toISOString() : new Date().toISOString()
  };

  if (editingId) {
    const index = questions.findIndex(item => item.id === editingId);
    if (index >= 0) {
      questions[index] = question;
    } else {
      questions.push(question);
    }
  } else {
    questions.push(question);
  }

  saveToStorage();
  showSaveMsg(editingId ? 'Updated!' : 'Saved!');
  clearForm();

  if (document.getElementById('view-bank').classList.contains('active')) {
    renderBank();
  }
}

function skillLabel(code) {
  return `${code.slice(0, 1)}.${code.slice(1)}`;
}

function renderBank() {
  const unitFilter = document.getElementById('fil-unit').value;
  const skillFilter = document.getElementById('fil-skill').value;
  const difficultyFilter = document.getElementById('fil-diff').value;
  const query = (document.getElementById('fil-search').value || '').toLowerCase();

  const filtered = questions.filter(item => {
    if (unitFilter && item.unit !== unitFilter) return false;
    if (skillFilter && item.skill !== skillFilter) return false;
    if (difficultyFilter && item.difficulty !== difficultyFilter) return false;
    if (query && !item.stem.toLowerCase().includes(query) && !(item.notes || '').toLowerCase().includes(query)) return false;
    return true;
  });

  const countElement = document.getElementById('bank-count');
  if (countElement) {
    countElement.textContent = `${filtered.length} of ${questions.length}`;
  }

  const bankList = document.getElementById('bank-list');
  if (!bankList) return;

  if (!filtered.length) {
    bankList.innerHTML = `<div class="empty-state"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="9" x2="9" y2="21"/></svg><p>${questions.length ? 'No questions match your filters.' : 'No questions yet — add your first one!'}</p></div>`;
    return;
  }

  bankList.innerHTML = filtered.map(item => {
    const difficultyDots = [1, 2, 3].map(level => `<div class="pip${level <= parseInt(item.difficulty, 10) ? ' on' : ''}"></div>`).join('');
    const choicesMarkup = ['A', 'B', 'C', 'D'].map(letter => {
      const isCorrect = item.correct === letter;
      return `<div class="q-choice${isCorrect ? ` correct correct-${letter}` : ''}">${isCorrect ? '✓' : '◦'} (${letter}) ${item[letter] || ''}</div>`;
    }).join('');

    const notesHtml = item.notes ? `<div class="q-notes">🚩 ${item.notes}</div>` : '';
    const stimulusHtml = item.stimulus !== 'None' ? `<span class="stim-chip">${item.stimulus}</span>` : '';

    return `<div class="q-card">
      <div class="q-header">
        <span class="unit-chip">Unit ${item.unit}</span>
        <span class="badge badge-${item.skill}">${skillLabel(item.skill)}</span>
        ${stimulusHtml}
        <div class="diff-pips">${difficultyDots}</div>
        <span class="q-meta-date">${new Date(item.date).toLocaleDateString()}</span>
      </div>
      <div class="q-stem">${item.stem}</div>
      <div class="q-choices">${choicesMarkup}</div>
      ${notesHtml}
      <div class="q-actions">
        <button type="button" class="btn-sm" data-action="edit" data-id="${item.id}">Edit</button>
        <button type="button" class="btn-sm del" data-action="delete" data-id="${item.id}">Delete</button>
      </div>
    </div>`;
  }).join('');
}

function editQ(id) {
  const question = questions.find(item => item.id === id);
  if (!question) return;

  ['unit', 'skill', 'stimulus', 'difficulty', 'stem', 'A', 'B', 'C', 'D', 'notes'].forEach(key => {
    const element = document.getElementById(`f-${key}`);
    if (element) element.value = question[key] || '';
  });

  editingId = id;
  selectCorrect(question.correct);
  updateSkillHint();
  LATEX_FIELDS.forEach(renderFieldMath);

  const editPill = document.getElementById('edit-pill');
  if (editPill) editPill.style.display = '';

  showView('add');
  window.scrollTo(0, 0);
}

function deleteQ(id) {
  if (!window.confirm('Delete this question?')) return;
  questions = questions.filter(item => item.id !== id);
  saveToStorage();
  renderBank();
}

function renderTracker() {
  const total = questions.length;
  const skills = ['2A', '2B', '2C', '2D', '3B', '3C'];
  const units = [9, 10, 11, 12, 13, 14, 15];

  const recentCount = questions.filter(item => {
    const date = new Date(item.date);
    return (Date.now() - date.getTime()) < 7 * 86400000;
  }).length;

  const statsRow = document.getElementById('stats-row');
  if (statsRow) {
    statsRow.innerHTML = [
      ['Total questions', total, ''],
      ['Units covered', new Set(questions.map(item => item.unit)).size, '/ 7'],
      ['Sub-skills used', new Set(questions.map(item => item.skill)).size, '/ 6'],
      ['This week', recentCount, questions.length ? `${Math.round(recentCount / Math.max(1, total) * 100)}%` : '']
    ].map(([label, value, sub]) => `
      <div class="stat-card">
        <div class="stat-label">${label}</div>
        <div class="stat-value">${value}</div>
        ${sub ? `<div class="stat-sub">${sub}</div>` : ''}
      </div>
    `).join('');
  }

  const heatmap = document.getElementById('heatmap');
  if (heatmap) {
    let html = `<tr><th class="row-h">Unit</th>${skills.map(skill => `<th>${skillLabel(skill)}</th>`).join('')}</tr>`;
    units.forEach(unit => {
      html += `<tr><th class="row-h">U${unit}</th>`;
      html += skills.map(skill => {
        const count = questions.filter(item => item.unit == unit && item.skill === skill).length;
        const tier = count === 0 ? 0 : count === 1 ? 1 : count <= 3 ? 2 : count <= 5 ? 3 : 4;
        return `<td class="hm-${tier}">${count || '—'}</td>`;
      }).join('');
      html += '</tr>';
    });
    heatmap.innerHTML = html;
  }

  const skillBars = document.getElementById('skill-bars');
  if (skillBars) {
    const maxCount = Math.max(1, ...skills.map(skill => questions.filter(item => item.skill === skill).length));
    const skillColors = {
      '2A': '#1e6fa8',
      '2B': '#1a7a52',
      '2C': '#6b3fa0',
      '2D': '#b83a1a',
      '3B': '#8a5c10',
      '3C': '#1a5478'
    };
    skillBars.innerHTML = skills.map(skill => {
      const count = questions.filter(item => item.skill === skill).length;
      const width = Math.max(Math.round(count / maxCount * 100), 2);
      return `
        <div class="bar-row">
          <div class="bar-lbl">${skillLabel(skill)}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${width}%;background:${skillColors[skill]};">${count > 0 ? count : ''}</div></div>
          <div class="bar-n">${count}</div>
        </div>`;
    }).join('');
  }

  const stimBars = document.getElementById('stim-bars');
  if (stimBars) {
    const stimulusTypes = ['None', 'Diagram', 'Graph', 'Data table', 'Two-student scenario'];
    const maxStim = Math.max(1, ...stimulusTypes.map(type => questions.filter(item => item.stimulus === type).length));
    stimBars.innerHTML = stimulusTypes.map(type => {
      const count = questions.filter(item => item.stimulus === type).length;
      const width = Math.max(Math.round(count / maxStim * 100), 2);
      return `
        <div class="bar-row">
          <div class="bar-name" title="${type}">${type}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${width}%;background:#78716c;">${count > 0 ? count : ''}</div></div>
          <div class="bar-n">${count}</div>
        </div>`;
    }).join('');
  }
}

function exportCSV() {
  const headers = ['id', 'date', 'unit', 'skill', 'stimulus', 'difficulty', 'stem', 'A', 'B', 'C', 'D', 'correct', 'notes'];
  const rows = questions.map(item => headers.map(field => `"${String(item[field] || '').replace(/"/g, '""')}"`).join(','));
  const csvText = [headers.join(','), ...rows].join('\n');
  const link = document.createElement('a');
  link.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csvText);
  link.download = 'ap_physics2_questions.csv';
  link.click();
}

function handleBankActions(event) {
  const actionButton = event.target.closest('button[data-action]');
  if (!actionButton) return;

  const action = actionButton.dataset.action;
  const id = actionButton.dataset.id;
  if (action === 'edit') {
    editQ(id);
  } else if (action === 'delete') {
    deleteQ(id);
  }
}

function initEventListeners() {
  document.querySelectorAll('.nav-btn').forEach(button => {
    button.addEventListener('click', () => showView(button.dataset.view));
  });

  const skillSelect = document.getElementById('f-skill');
  if (skillSelect) {
    skillSelect.addEventListener('change', updateSkillHint);
  }

  document.querySelectorAll('.choice-letter').forEach(button => {
    button.addEventListener('click', () => selectCorrect(button.dataset.choice));
  });

  const saveButton = document.getElementById('save-btn');
  if (saveButton) saveButton.addEventListener('click', saveQuestion);

  const clearButton = document.getElementById('clear-btn');
  if (clearButton) clearButton.addEventListener('click', clearForm);

  const exportButton = document.getElementById('export-btn');
  if (exportButton) exportButton.addEventListener('click', exportCSV);

  LATEX_FIELDS.forEach(attachLatexEditor);

  ['fil-unit', 'fil-skill', 'fil-diff'].forEach(id => {
    const element = document.getElementById(id);
    if (element) element.addEventListener('change', renderBank);
  });

  const searchField = document.getElementById('fil-search');
  if (searchField) searchField.addEventListener('input', renderBank);

  const bankList = document.getElementById('bank-list');
  if (bankList) bankList.addEventListener('click', handleBankActions);
}

function init() {
  initEventListeners();
  loadFromStorage();
}

window.addEventListener('DOMContentLoaded', init);
