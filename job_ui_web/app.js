const token = document.querySelector('meta[name="csrf-token"]').content;
const jobSelect = document.querySelector('#job');
const message = document.querySelector('#message');
const buttons = [...document.querySelectorAll('button[data-action]')];
let busy = false;
const cloudDashboard = document.body.dataset.dashboard === 'cloud';

function renderTable(id, rows) {
  const container = document.getElementById(id);
  container.replaceChildren();
  if (!rows.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = '暂无记录';
    container.append(empty);
    return;
  }

  const table = document.createElement('table');
  const columns = Object.keys(rows[0]);
  const header = table.createTHead().insertRow();
  for (const column of columns) {
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.textContent = column;
    header.append(cell);
  }
  const body = table.createTBody();
  for (const row of rows) {
    const line = body.insertRow();
    for (const column of columns) {
      line.insertCell().textContent = row[column] ?? '—';
    }
  }
  container.append(table);
}

async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error);
  return data;
}

async function refresh(preferredJob = jobSelect.value) {
  const state = await request('/api/state');
  if (cloudDashboard) {
    for (const section of ['jobs', 'alerts', 'notifications']) {
      renderTable(section, state[section]);
    }
    document.querySelector('#foot').textContent = 'Aiven · 每类展示最近 100 条记录';
    return;
  }
  const options = state.jobs.map(job =>
    new Option(job.JOB_NAME + ' · ' + job.STATUS, job.EXECUTION_ID)
  );
  jobSelect.replaceChildren(...(options.length ? options : [new Option('先创建一个测试 JOB', '')]));
  if (state.jobs.some(job => job.EXECUTION_ID === preferredJob)) {
    jobSelect.value = preferredJob;
  }
  for (const section of ['jobs', 'alerts', 'notifications']) {
    renderTable(section, state[section]);
  }
  document.querySelector('#foot').textContent =
    '独立 checkpoint：' + state.checkpoint + ' · 通知通过 CONSOLE 输出。';
}

async function runAction(action) {
  if (busy) return;
  busy = true;
  buttons.forEach(button => { button.disabled = true; });
  try {
    let preferredJob = jobSelect.value;
    if (action !== 'refresh') {
      const result = await request('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
        body: JSON.stringify({ action, execution_id: jobSelect.value }),
      });
      preferredJob = result.execution_id ?? preferredJob;
      message.textContent = result.message;
    }
    await refresh(preferredJob);
  } catch (error) {
    message.textContent = error.message;
  } finally {
    busy = false;
    buttons.forEach(button => { button.disabled = false; });
  }
}

for (const button of buttons) {
  button.addEventListener('click', () => runAction(button.dataset.action));
}
if (cloudDashboard) {
  refresh().catch(error => {
    document.querySelector('#foot').textContent = error.message;
  });
} else {
  runAction('refresh');
}
