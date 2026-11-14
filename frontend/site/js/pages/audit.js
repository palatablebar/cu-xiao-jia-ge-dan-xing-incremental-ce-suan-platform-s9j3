import { api } from '../api.js';
import { errorBox, errorMessage, esc, field, fmtTime, table } from '../ui.js';

const state = { action: '' };

const ACTIONS = [
  ['', '全部动作'],
  ['auth.login', '登录'],
  ['lift.create', '发起测算'],
  ['lift.review', '提交复盘'],
  ['sku.update', '修改 SKU'],
  ['event.create', '新建活动'],
  ['export.reports', '导出复盘清单'],
];

/** 审计日志（仅 admin）：谁能改成本、谁导出了清单，都留痕。 */
export const auditPage = {
  async render(view, ctx) {
    let data;
    try {
      data = await api.get('/api/audit', { limit: 100, action: state.action });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => auditPage.render(view, ctx));
      return;
    }
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>审计日志</h2>
          <span class="meta">${data.total} 条 · 最近 100 条</span>
        </div>
        <div class="panel-body">
          <div class="filter-bar" id="audit-filters">
            ${field({ label: '动作', name: 'action', value: state.action, options: ACTIONS.map(([value, label]) => ({ value, label })) })}
            <div class="spacer"></div>
            <span class="mono muted">domain = 业务动作，http = 写请求，worker = 定时任务，seed = 初始化</span>
          </div>
        </div>
        ${table({
          rows: data.items,
          columns: [
            { key: 'created_at', label: '时间', render: (row) => `<span class="mono">${fmtTime(row.created_at)}</span>` },
            { key: 'actor_email', label: '操作人', className: 'mono' },
            { key: 'actor_role', label: '角色' },
            { key: 'action_label', label: '动作' },
            { key: 'entity', label: '对象' },
            { key: 'layer', label: '层', render: (row) => `<span class="badge">${esc(row.layer)}</span>` },
            { key: 'detail', label: '详情', render: (row) => `<span class="mono muted">${esc(JSON.stringify(row.detail || {}))}</span>` },
          ],
          empty: { title: '还没有审计记录', hint: '登录、发起测算、提交复盘都会留痕。' },
        })}
      </section>`;

    view.querySelector('#audit-filters select')?.addEventListener('change', (event) => {
      state.action = event.target.value;
      auditPage.render(view, ctx);
    });
  },
};

export default auditPage;
