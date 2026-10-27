/* 数独前端控制器：负责棋盘交互、键盘快捷键、笔记、计时和接口同步。 */
(() => {
  // 页面不是数独游戏页时立即退出，避免全站加载该脚本后访问不存在的元素。
  const app = document.getElementById('game-app');
  if (!app) return;

  // original 永远保存题面给定数字；board 只保存已确认正确的数字。
  // wrongValues 单独保存待改正的错误数字，避免它们干扰提示与完成判定。
  // highlightedDigit 单独记录当前强调的数字，让正式数字和候选小数字使用同一套高亮规则。
  const original = JSON.parse(document.getElementById('puzzle-data').textContent);
  let board = JSON.parse(document.getElementById('board-data').textContent);
  let wrongValues = JSON.parse(document.getElementById('wrong-values-data').textContent);
  let notes = JSON.parse(document.getElementById('notes-data').textContent);
  let selected = null, noteMode = false, paused = false, locked = app.dataset.status !== 'playing';
  let highlightedDigit = 0;
  let notesVisible = app.dataset.notesVisible === 'true';
  const isAuthenticated = app.dataset.auth === 'true';
  let elapsed = Number(app.dataset.elapsed), saveTimer;
  const boardEl = document.getElementById('sudoku-board');
  const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

  // 所有游戏写操作都经过同一 POST 封装，统一携带 CSRF 令牌并转成可读错误。
  const post = async (url, data = {}) => {
    const response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrftoken}, body: JSON.stringify(data)});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || '操作未完成');
    return payload;
  };
  const cellAt = (r, c) => boardEl.querySelector(`[data-row="${r}"][data-col="${c}"]`);
  const formatTime = value => `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;

  // 只重绘一个格子：正式数字直接显示；空格固定生成 3×3 候选数位置，防止布局跳动。
  function renderCell(r, c) {
    const cell = cellAt(r, c); if (!cell) return;
    cell.innerHTML = '';
    cell.classList.toggle('given', original[r][c] !== 0);
    cell.classList.toggle('filled', board[r][c] !== 0 && original[r][c] === 0);
    cell.classList.toggle('wrong', wrongValues[r][c] !== 0);
    const visibleValue = wrongValues[r][c] || board[r][c];
    if (visibleValue) cell.textContent = visibleValue;
    else {
      const grid = document.createElement('span'); grid.className = 'notes-grid';
      for (let n = 1; n <= 9; n++) {
        const s = document.createElement('i');
        const isVisibleNote = notes[r][c].includes(n);
        s.textContent = isVisibleNote ? n : '';
        // 仅给真实存在的候选数字设置 data-note，点击空白位置不会误触高亮。
        if (isVisibleNote) s.dataset.note = n;
        s.classList.toggle('note-match', isVisibleNote && n === highlightedDigit);
        grid.appendChild(s);
      }
      cell.appendChild(grid);
    }
  }

  // 首次进入页面时按行列生成 81 个按钮；格子坐标放在 dataset 中供后续快速定位。
  function buildBoard() {
    for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) {
      const cell = document.createElement('button'); cell.className = 'sudoku-cell'; cell.dataset.row = r; cell.dataset.col = c;
      cell.setAttribute('role', 'gridcell');
      // 点击候选小数字时用它作为高亮目标；点击格子其他位置则按格内正式数字决定。
      cell.addEventListener('click', event => selectCell(r, c, Number(event.target.dataset.note) || 0));
      boardEl.appendChild(cell); renderCell(r, c);
    }
    if (locked) boardEl.classList.add('locked');
    boardEl.classList.toggle('notes-hidden', !notesVisible);
  }
  // 统一刷新选格、同行/同列/同宫、相同正式数字和相同候选数字四类高亮。
  function selectCell(r, c, noteDigit = 0) {
    if (paused) return;
    selected = [r, c];
    highlightedDigit = wrongValues[r][c] || board[r][c] || noteDigit;
    document.querySelectorAll('.sudoku-cell').forEach(cell => {
      const cr = Number(cell.dataset.row), cc = Number(cell.dataset.col);
      const related = cr === r || cc === c || (Math.floor(cr / 3) === Math.floor(r / 3) && Math.floor(cc / 3) === Math.floor(c / 3));
      cell.classList.toggle('related', related); cell.classList.toggle('selected', cr === r && cc === c);
      const visibleValue = wrongValues[cr][cc] || board[cr][cc];
      cell.classList.toggle('same-value', highlightedDigit > 0 && visibleValue === highlightedDigit && !(cr === r && cc === c));
      cell.querySelectorAll('.notes-grid i').forEach(note => {
        note.classList.toggle('note-match', highlightedDigit > 0 && note.textContent === String(highlightedDigit));
      });
    });
  }
  // 高频操作合并后再保存，减少连续输入产生的重复请求。
  function scheduleSave() {
    clearTimeout(saveTimer); document.getElementById('save-status').textContent = isAuthenticated ? '正在保存…' : '游客进度不会保存';
    saveTimer = setTimeout(async () => { try { const data = await post(app.dataset.saveUrl, {notes, notes_visible: notesVisible, elapsed}); document.getElementById('save-status').textContent = isAuthenticated ? `已自动保存 · ${data.saved_at}` : '游客进度不会保存'; } catch (e) { document.getElementById('save-status').textContent = e.message; } }, 450);
  }
  // noteOverride 只供删除键强制输入正式值 0；其他输入由当前小数字模式决定。
  async function enterNumber(value, noteOverride = null) {
    if (!selected || locked || paused) return;
    const [r, c] = selected; if (original[r][c]) return;
    const useNotes = noteOverride === null ? noteMode : noteOverride;
    if (useNotes && value) {
      if (board[r][c] || wrongValues[r][c]) return;
      const set = new Set(notes[r][c]);
      set.has(value) ? set.delete(value) : set.add(value);
      notes[r][c] = [...set].sort();
      renderCell(r, c);
      // 即使本次操作是删除候选数，也继续强调这个数字，方便检查全盘同值候选。
      selectCell(r, c, value);
      scheduleSave();
      return;
    }
    if (board[r][c] && value) { toast('这个数字已经确认；如需修改请先删除'); return; }
    try {
      const data = await post(app.dataset.moveUrl, {row: r, col: c, value, elapsed});
      board[r][c] = data.value;
      wrongValues[r][c] = data.wrong_value;
      if (!data.is_error) {
        notes = data.notes;
        renderAllCells();
      } else renderCell(r, c);
      selectCell(r, c);
      if (data.is_error) document.getElementById('error-count').textContent = data.errors;
      if (data.status !== 'playing') finish(data.status, data.reward);
    } catch (e) { toast(e.message); }
  }
  // 完成或失败后锁住整个棋盘，结果弹窗只负责展示服务端确认的最终状态。
  function finish(status, reward = 0) {
    locked = true; boardEl.classList.add('locked');
    document.getElementById('result-mark').textContent = status === 'completed' ? '✓' : '!';
    document.getElementById('result-title').textContent = status === 'completed' ? '漂亮，完成了！' : '三次错误，本局结束';
    document.getElementById('result-copy').textContent = status === 'completed' ? `用时 ${formatTime(elapsed)}${reward ? `，获得 ${reward} 金币。` : '。'}` : '棋盘已锁定。重新开始后再试一次吧。';
    document.getElementById('result-modal').classList.remove('hidden');
  }
  function toast(message) { const el = document.getElementById('save-status'); el.textContent = message; el.classList.add('error-text'); setTimeout(() => el.classList.remove('error-text'), 1800); }
  function renderAllCells() {
    for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) renderCell(r, c);
  }
  // 自动候选数只做基础行、列、宫排除；后续正确落子会实时删去相关同值小数字。
  function fillAutoNotes() {
    if (locked) return;
    for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) if (!board[r][c]) {
      const used = new Set([...board[r], ...board.map(row => row[c])]);
      for (let rr = Math.floor(r/3)*3; rr < Math.floor(r/3)*3+3; rr++) for (let cc = Math.floor(c/3)*3; cc < Math.floor(c/3)*3+3; cc++) used.add(board[rr][cc]);
      notes[r][c] = [1,2,3,4,5,6,7,8,9].filter(n => !used.has(n)); renderCell(r,c);
    }
    scheduleSave(); toast('已计算候选数；正确落子后会实时清除相关同值小数字');
  }
  // Shift 与工具按钮共用此函数，保证按钮状态、角标文字和实际模式同步。
  function setNoteMode(enabled) {
    noteMode = enabled;
    document.getElementById('note-button').classList.toggle('active', noteMode);
    document.getElementById('note-mode-badge').textContent = noteMode ? 'ON' : 'OFF';
  }
  // Tab 只改变候选数可见性，不会删除 notes 中已经保存的数据。
  function setNotesVisible(visible) {
    notesVisible = visible;
    boardEl.classList.toggle('notes-hidden', !notesVisible);
    document.getElementById('visibility-button').classList.toggle('active', notesVisible);
    document.getElementById('visibility-badge').textContent = notesVisible ? 'ON' : 'OFF';
    scheduleSave();
  }

  // 页面初始化完成后再绑定工具栏、数字键盘和撤销操作。
  buildBoard();
  document.getElementById('visibility-button').classList.toggle('active', notesVisible);
  document.querySelectorAll('[data-number]').forEach(button => button.addEventListener('click', () => enterNumber(Number(button.dataset.number))));
  document.getElementById('erase-button').addEventListener('click', () => enterNumber(0));
  document.getElementById('note-button').addEventListener('click', () => setNoteMode(!noteMode));
  document.getElementById('visibility-button').addEventListener('click', () => setNotesVisible(!notesVisible));
  document.getElementById('auto-notes').addEventListener('click', fillAutoNotes);
  document.getElementById('undo-button').addEventListener('click', async () => { try { const data = await post(app.dataset.undoUrl); board[data.row][data.col] = data.value; wrongValues[data.row][data.col] = 0; notes = data.notes; renderAllCells(); selectCell(data.row, data.col); } catch (e) { toast(e.message); } });
  // Tab 只控制笔记可见性；Shift 每按一次切换一次小数字输入模式。
  document.addEventListener('keydown', e => {
    if (e.key === 'Tab') { e.preventDefault(); if (!e.repeat) setNotesVisible(!notesVisible); return; }
    if (e.key === 'Shift') { e.preventDefault(); if (!e.repeat) setNoteMode(!noteMode); return; }
    const directions = {ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1]};
    if (directions[e.key]) {
      e.preventDefault();
      const [dr, dc] = directions[e.key];
      const [row, col] = selected || [0, 0];
      selectCell(Math.max(0, Math.min(8, row + dr)), Math.max(0, Math.min(8, col + dc)));
      cellAt(selected[0], selected[1]).focus({preventScroll: true});
      return;
    }
    const digitCode = /^Digit([1-9])$/.exec(e.code || '') || /^Numpad([1-9])$/.exec(e.code || '');
    const digitKey = /^([1-9])$/.exec(e.key || '') || /^Digit([1-9])$/.exec(e.key || '') || /^Numpad([1-9])$/.exec(e.key || '');
    const shiftedDigits = {'!': 1, '@': 2, '#': 3, '$': 4, '%': 5, '^': 6, '&': 7, '*': 8, '(': 9};
    const digit = digitKey ? Number(digitKey[1]) : (digitCode ? Number(digitCode[1]) : (shiftedDigits[e.key] || 0));
    if (digit) { e.preventDefault(); enterNumber(digit); return; }
    if (['Backspace', 'Delete', '0'].includes(e.key)) { e.preventDefault(); enterNumber(0, false); }
  });

  // 暂停仅冻结前端计时与输入，恢复后继续使用同一局数据。
  const pauseOverlay = document.getElementById('pause-overlay');
  document.getElementById('pause-button').addEventListener('click', () => { if (locked) return; paused = true; pauseOverlay.classList.remove('hidden'); });
  document.getElementById('resume-button').addEventListener('click', () => { paused = false; pauseOverlay.classList.add('hidden'); });
  setInterval(() => { if (!paused && !locked) { elapsed++; document.getElementById('timer').textContent = formatTime(elapsed); } }, 1000);
  setInterval(() => { if (!locked) scheduleSave(); }, 30000);

  // 提示由服务端决定免费额度或金币扣费，前端只展示返回的解释与余额。
  const hintModal = document.getElementById('hint-modal');
  const closeHint = () => hintModal.classList.add('hidden');
  document.querySelector('.modal-close').addEventListener('click', closeHint); document.getElementById('hint-close').addEventListener('click', closeHint);
  document.getElementById('hint-button').addEventListener('click', async e => {
    if (e.currentTarget.dataset.guest) { window.location.href = '/accounts/login/?next=' + encodeURIComponent(location.pathname); return; }
    hintModal.classList.remove('hidden'); document.getElementById('hint-title').textContent = '正在观察盘面…'; document.getElementById('hint-content').innerHTML = '<p>我们会先寻找最清楚、最容易理解的一步。</p>';
    try {
      const h = await post(app.dataset.hintUrl, {level: 'auto'}); document.getElementById('hint-level').textContent = `${h.level} · ${h.technique}`; document.getElementById('hint-title').textContent = h.title;
      const actions = [...(h.eliminations || [])]; if (h.placement) actions.push(`下一步：在 ${h.placement.cell} 填入 ${h.placement.value}`);
      document.getElementById('hint-content').innerHTML = `<p>${h.explanation}</p>${h.cells.length ? `<div class="involved"><b>涉及格子</b><span>${h.cells.join(' · ')}</span></div>` : ''}${actions.length ? `<ol>${actions.map(a=>`<li>${a}</li>`).join('')}</ol>` : ''}<small>本次消耗：${h.payment === 'free' ? '每日免费提示' : `${h.cost} 金币`}</small>`;
      document.getElementById('coin-count').textContent = `◉ ${h.coins}`;
      document.getElementById('free-hints').textContent = h.free_hints;
      document.getElementById('hint-badge').textContent = h.free_hints > 0 ? h.free_hints : '100金币';
    } catch (e) { document.getElementById('hint-title').textContent = '暂时不能提示'; document.getElementById('hint-content').innerHTML = `<p>${e.message}</p>`; }
  });
  // 登录用户离开页面前做最后一次轻量保存；游客不持久化进度。
  window.addEventListener('beforeunload', () => { if (isAuthenticated && !locked) fetch(app.dataset.saveUrl, {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':csrftoken}, body:JSON.stringify({notes, notes_visible:notesVisible, elapsed}), keepalive:true}); });
})();
