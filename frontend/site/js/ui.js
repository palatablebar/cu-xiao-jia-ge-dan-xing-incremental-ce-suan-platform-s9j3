/** 无框架 UI 组件：登记表 / 表格 / 徽标 / 抽屉 / SVG 曲线 / 空态 / toast。 */

export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

export function fmtTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return esc(iso);
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

const nf = new Intl.NumberFormat('zh-CN');
const nf1 = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function fmtInt(value) {
  return Number.isFinite(Number(value)) ? nf.format(Number(value)) : '—';
}

export function fmtDec(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  if (digits === 1) return nf1.format(Number(value));
  return Number(value).toFixed(digits);
}

export function fmtPct(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const pct = Number(value) * 100;
  return `${pct > 0 ? '+' : ''}${pct.toFixed(digits)}%`;
}

export function fmtRoi(value) {
  if (value === null || value === undefined) return '—';
  return Number(value).toFixed(2);
}

export function fmtElasticity(value, state) {
  if (state === 'unknown' || value === null || value === undefined) return '不可估计';
  return Number(value).toFixed(2);
}

export function badge(tone, text) {
  return `<span class="badge ${esc(tone)}">${esc(text)}</span>`;
}

export function ledger(items) {
  return `<div class="ledger">${items
    .map(
      (item) => `<div class="ledger-cell">
        <span class="k">${esc(item.label)}</span>
        <span class="v">${item.value}${item.unit ? `<small>${esc(item.unit)}</small>` : ''}</span>
        <span class="hint ${item.bad ? 'bad' : ''}">${esc(item.hint || '')}</span>
      </div>`,
    )
    .join('')}</div>`;
}

export function emptyState({ title, hint, actionText, actionId }) {
  return `<div class="empty" data-testid="empty-state">
    <div class="mark">${esc(title)}</div>
    <p>${esc(hint || '')}</p>
    ${actionText ? `<button class="btn ghost" id="${esc(actionId || 'empty-action')}">${esc(actionText)}</button>` : ''}
  </div>`;
}

export function errorBox(message, retryId = 'retry-btn') {
  return `<div class="error-box"><span>${esc(message)}</span><button class="btn sm ghost" id="${esc(retryId)}">重试</button></div>`;
}

export function table({ columns, rows, empty, testid }) {
  if (!rows || rows.length === 0) return emptyState(empty || { title: '暂无记录', hint: '调整筛选条件或先跑一次测算。' });
  const head = columns.map((col) => `<th>${esc(col.label)}</th>`).join('');
  const body = rows
    .map(
      (row) => `<tr data-id="${esc(row.id)}" ${testid ? `data-testid="${esc(testid)}-${esc(row.id)}"` : ''}>
        ${columns.map((col) => `<td class="${esc(col.className || '')}">${col.render ? col.render(row) : esc(row[col.key])}</td>`).join('')}
      </tr>`,
    )
    .join('');
  return `<div class="table-wrap"><table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function drawer({ title, subtitle, body, footer }) {
  const backdrop = document.createElement('div');
  backdrop.className = 'drawer-backdrop';
  backdrop.innerHTML = `<aside class="drawer" role="dialog" aria-modal="true" data-testid="drawer">
    <div class="drawer-head">
      <div>
        <h2>${esc(title)}</h2>
        <div class="mono muted">${esc(subtitle || '')}</div>
      </div>
      <button class="btn sm ghost" data-close>关闭</button>
    </div>
    <div class="drawer-body">${body}</div>
    ${footer ? `<div class="drawer-foot">${footer}</div>` : ''}
  </aside>`;
  const close = () => {
    backdrop.remove();
    document.removeEventListener('keydown', onKey);
  };
  const onKey = (event) => {
    if (event.key === 'Escape') close();
  };
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop || event.target.closest('[data-close]')) close();
  });
  document.addEventListener('keydown', onKey);
  document.body.appendChild(backdrop);
  return { root: backdrop, close };
}

export function kv(items) {
  return `<dl class="kv">${items
    .map(([key, value]) => `<dt>${esc(key)}</dt><dd>${value === undefined || value === null ? '—' : value}</dd>`)
    .join('')}</dl>`;
}

export function barList(items) {
  const max = Math.max(1, ...items.map((item) => item.count));
  return `<div class="bars">${items
    .map(
      (item) => `<div class="bar-row">
        <span class="lbl">${esc(item.label)}</span>
        <div class="bar-track"><div class="bar-fill ${esc(item.key || '')}" style="width:${Math.round((item.count / max) * 100)}%"></div></div>
        <span class="mono">${esc(item.count)}</span>
      </div>`,
    )
    .join('')}</div>`;
}

export function rankList(items, render) {
  if (!items || items.length === 0) return '<p class="muted" style="margin:0">暂无记录</p>';
  return `<div class="rank">${items.map((item) => render(item)).join('')}</div>`;
}

/* ------------------------------------------------------------------ SVG 曲线 */

function toIndex(dates, iso) {
  const needle = String(iso).slice(0, 10);
  return dates.indexOf(needle);
}

/**
 * 折线图（方格纸底 + 促销窗口阴影 + 均值虚线）。
 * points: [{date, [valueKey], is_promo}]；windows: [{start_on, end_on}]
 */
export function lineChart({
  points,
  windows = [],
  valueKey = 'qty',
  height = 320,
  width = 1080,
  showMean = true,
  showMarkers = true,
  yFormat = (value) => fmtInt(value),
  caption = '',
  minFloor = 0,
} = {}) {
  if (!points || points.length === 0) {
    return emptyState({ title: '没有可绘制的日销量', hint: '换一个 SKU 或先跑 seed。' });
  }
  const margin = { top: 14, right: 14, bottom: 26, left: 52 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const values = points.map((point) => Number(point[valueKey] ?? 0));
  const dates = points.map((point) => String(point.date).slice(0, 10));
  const rawMax = Math.max(...values, 1);
  const rawMin = Math.min(...values, minFloor);
  const span = Math.max(rawMax - rawMin, 1);
  const yMax = rawMax + span * 0.12;
  const yMin = Math.max(minFloor, rawMin - span * 0.12);
  const x = (index) => margin.left + (dates.length <= 1 ? 0 : (index / (dates.length - 1)) * plotW);
  const y = (value) => margin.top + plotH - ((value - yMin) / (yMax - yMin || 1)) * plotH;

  const mean = values.reduce((acc, value) => acc + value, 0) / values.length;

  const gridCount = 4;
  const grid = Array.from({ length: gridCount + 1 }, (_, i) => {
    const value = yMin + ((yMax - yMin) / gridCount) * i;
    return `<line class="gridline" x1="${margin.left}" x2="${width - margin.right}" y1="${y(value)}" y2="${y(value)}"></line>
      <text x="${margin.left - 8}" y="${y(value) + 3}" text-anchor="end">${esc(yFormat(value))}</text>`;
  }).join('');

  const bands = windows
    .map((win) => {
      const start = toIndex(dates, win.start_on);
      const end = toIndex(dates, win.end_on);
      if (start < 0 && end < 0) return '';
      const from = Math.max(0, start < 0 ? 0 : start);
      const to = end < 0 ? dates.length - 1 : end;
      const x1 = x(from) - (plotW / Math.max(dates.length - 1, 1)) * 0.4;
      const x2 = x(to) + (plotW / Math.max(dates.length - 1, 1)) * 0.4;
      return `<rect class="win" x="${x1.toFixed(1)}" y="${margin.top}" width="${Math.max(2, x2 - x1).toFixed(1)}" height="${plotH}"></rect>`;
    })
    .join('');

  const path = values.map((value, index) => `${index === 0 ? 'M' : 'L'}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(' ');

  const markers = showMarkers
    ? points
        .map((point, index) =>
          point.is_promo
            ? `<circle class="marker" cx="${x(index).toFixed(1)}" cy="${y(Number(point[valueKey] ?? 0)).toFixed(1)}" r="2.4"></circle>`
            : '',
        )
        .join('')
    : '';

  const tickEvery = Math.max(1, Math.round(dates.length / 8));
  const xTicks = dates
    .map((date, index) =>
      index % tickEvery === 0
        ? `<text x="${x(index).toFixed(1)}" y="${height - 8}" text-anchor="middle">${esc(date.slice(5))}</text>`
        : '',
    )
    .join('');

  const meanLine = showMean
    ? `<line class="mean" x1="${margin.left}" x2="${width - margin.right}" y1="${y(mean)}" y2="${y(mean)}"></line>`
    : '';

  return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(caption || '销量曲线')}">
    ${bands}
    ${grid}
    ${meanLine}
    <line class="axis" x1="${margin.left}" x2="${width - margin.right}" y1="${height - margin.bottom}" y2="${height - margin.bottom}"></line>
    <path class="line" d="${path}"></path>
    ${markers}
    ${xTicks}
  </svg>`;
}

export function chartLegend(items) {
  return `<div class="chart-legend">${items
    .map((item) => `<span><i class="${esc(item.tone || '')}"></i>${esc(item.label)}</span>`)
    .join('')}</div>`;
}

export function annotation({ title, children, figures = [] }) {
  return `<div class="annotation" data-testid="annotation">
    <h3>${esc(title)}</h3>
    <p>${children}</p>
    ${
      figures.length
        ? `<p style="margin-top:6px">${figures.map((item) => `<span class="fig">${esc(item)}</span>`).join(' · ')}</p>`
        : ''
    }
  </div>`;
}

export function field({ label, name, type = 'text', value = '', placeholder = '', options = null, attrs = '' }) {
  const control = options
    ? `<select name="${esc(name)}" id="${esc(name)}" ${attrs}>${options
        .map((opt) => `<option value="${esc(opt.value)}" ${String(opt.value) === String(value) ? 'selected' : ''}>${esc(opt.label)}</option>`)
        .join('')}</select>`
    : `<input name="${esc(name)}" id="${esc(name)}" type="${esc(type)}" value="${esc(value)}" placeholder="${esc(placeholder)}" ${attrs} />`;
  return `<div class="field"><label for="${esc(name)}">${esc(label)}</label>${control}</div>`;
}

export function toast(message, tone = '') {
  const stack = document.getElementById('toast-stack');
  const node = document.createElement('div');
  node.className = `toast ${tone}`;
  node.textContent = message;
  stack.appendChild(node);
  setTimeout(() => node.remove(), 3600);
}

export function errorMessage(err) {
  if (!err) return '未知错误';
  if (err.code === 'FORBIDDEN') return '当前角色没有这个操作的权限（后端返回 403）';
  if (err.code === 'AUTH_MISSING') return '登录已过期，请重新登录';
  return err.message || '请求失败';
}
