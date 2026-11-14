import { api } from '../api.js';
import { ENUMS, bandTone, can, statusTone } from '../config.js';
import {
  drawer,
  errorBox,
  errorMessage,
  esc,
  field,
  fmtDec,
  fmtElasticity,
  fmtInt,
  fmtPct,
  fmtRoi,
  fmtTime,
  kv,
  table,
  toast,
} from '../ui.js';

const state = { runId: '', status: '', band: '', q: '' };

function reportRow(row) {
  return {
    ...row,
    id: row.id,
  };
}

async function openReport(view, ctx, item) {
  let detail;
  try {
    detail = await api.get(`/api/lift-reports/${item.id}`);
  } catch (err) {
    toast(errorMessage(err), 'err');
    return;
  }
  const canReview = can(ctx.user.role, 'lift:review');
  const controls = (detail.control_skus || {}).codes || [];
  const { root, close } = drawer({
    title: `${detail.event_no} · ${detail.sku_name}`,
    subtitle: `${detail.kind_label || ''} / ${detail.channel_label || ''} / ${detail.start_on} → ${detail.end_on}`,
    body: `${kv([
      ['SKU', `<span class="mono">${esc(detail.sku_code)}</span> ${esc(detail.sku_name)}`],
      ['牌价 → 促销价', `<span class="mono">${fmtDec(detail.base_price, 2)} → ${fmtDec(detail.promo_price, 2)}（−${((detail.discount || 0) * 100).toFixed(1)}%）</span>`],
      ['基线日销', `<span class="mono">${fmtDec(detail.baseline_qty, 1)} 件/日</span>`],
      ['实际日销', `<span class="mono">${fmtDec(detail.actual_qty, 1)} 件/日</span>`],
      ['增量', `<span class="mono">${fmtInt(detail.incremental_qty)} 件 · ${fmtPct(detail.lift_pct)}</span>`],
      ['弹性', `<span class="mono">${esc(fmtElasticity(detail.elasticity, detail.elasticity === null ? 'unknown' : 'ok'))}</span> <span class="mono muted">p=${detail.p_value === null ? '—' : detail.p_value < 0.001 ? '<0.001' : fmtDec(detail.p_value, 4)} · R²=${fmtDec(detail.r2, 3)}</span>`],
      ['ROI', `<span class="badge ${bandTone(detail.roi_band)}">${fmtRoi(detail.roi)} · ${esc(detail.roi_band_label)}</span>`],
      ['平行趋势', detail.parallel_ok ? '<span class="badge ok">通过</span>' : `<span class="badge warn">存疑 ${fmtDec(detail.trend_gap, 3)}</span>`],
      ['对照 SKU', `<span class="mono">${esc(controls.join(' / ') || '—')}</span>`],
      ['结论', esc(detail.note || '—')],
      ['复盘', `<span class="badge ${statusTone(detail.status)}">${esc(detail.status_label)}</span> ${esc(detail.reviewer || '')} ${esc(detail.review_note || '')}`],
    ])}
    <h3>算法明细</h3>
    <pre class="code">${esc(
      JSON.stringify(
        {
          算法: 'DID：Δtreat − Δcontrol（同品类 3 个对照 SKU，按活动前日均销量匹配）',
          基线: detail.baseline_qty,
          实际: detail.actual_qty,
          增量件数: detail.incremental_qty,
          增量率: detail.lift_pct,
          弹性: detail.elasticity,
          p值: detail.p_value,
          ROI: '增量毛利 / 增量单元让利',
          ROI值: detail.roi,
          对照: controls,
        },
        null,
        2,
      ),
    )}</pre>`,
    footer: canReview
      ? `<form id="review-form" style="display:grid;gap:10px">
          ${field({ label: '复盘结论', name: 'status', value: detail.status, options: Object.entries(ENUMS.reportStatus).map(([value, label]) => ({ value, label })) })}
          ${field({ label: '备注', name: 'note', value: detail.review_note || '', placeholder: '写一句结论，例如：折扣过深，建议下期回到 9 折' })}
          <button class="btn accent" type="submit">提交复盘</button>
        </form>`
      : '<span class="mono muted">只读角色可以查看，但不能提交复盘（后端 403）</span>',
  });
  root.querySelector('[data-series]')?.addEventListener('click', () => {
    location.hash = `#/series?sku=${detail.sku_id}`;
  });
  root.querySelector('#review-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
      await api.patch(`/api/lift-reports/${detail.id}/review`, {
        status: form.status.value,
        note: form.note.value.trim() || null,
      });
      toast('复盘结论已保存');
      close();
      await liftPage.render(view, ctx);
    } catch (err) {
      toast(errorMessage(err), 'err');
    }
  });
}

export const liftPage = {
  async render(view, ctx) {
    if (ctx.query.run_id) state.runId = ctx.query.run_id;
    let runs;
    let reports;
    try {
      [runs, reports] = await Promise.all([
        api.get('/api/lift-runs', { limit: 20 }),
        api.get('/api/lift-reports', {
          run_id: state.runId,
          status: state.status,
          band: state.band,
          q: state.q,
          limit: 50,
        }),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => liftPage.render(view, ctx));
      return;
    }
    const latest = runs.items[0];

    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>测算批次</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${fmtInt(runs.total)} 个批次</span>
            ${can(ctx.user.role, 'export:read') ? '<button class="btn sm ghost" id="export-reports">导出复盘 CSV</button>' : ''}
            ${can(ctx.user.role, 'lift:create') ? '<button class="btn sm accent" id="new-run">发起测算</button>' : ''}
          </div>
        </div>
        ${table({
          rows: runs.items,
          columns: [
            { key: 'run_no', label: '批次号', className: 'mono' },
            { key: 'status', label: '状态', render: (row) => `<span class="badge ${row.status === 'success' ? 'ok' : row.status === 'failed' ? 'danger' : 'warn'}">${esc(ENUMS.runStatus[row.status] || row.status)}</span>` },
            { key: 'trigger', label: '触发', render: (row) => esc(ENUMS.trigger[row.trigger] || row.trigger) },
            { key: 'event_count', label: '活动', className: 'num' },
            { key: 'report_count', label: '复盘', className: 'num' },
            { key: 'metrics', label: '平均弹性', className: 'num', render: (row) => fmtDec((row.metrics || {}).avg_elasticity, 2) },
            { key: 'metrics', label: '平均增量', className: 'num', render: (row) => fmtPct((row.metrics || {}).avg_lift_pct) },
            { key: 'started_at', label: '开始', render: (row) => `<span class="mono">${fmtTime(row.started_at)}</span>` },
          ],
        })}
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>复盘清单 ${state.runId ? `<span class="mono muted">· 批次 #${esc(state.runId)}</span>` : ''}</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${fmtInt(reports.total)} 条</span>
            ${state.runId ? '<button class="btn sm ghost" id="clear-run">全部批次</button>' : ''}
          </div>
        </div>
        <div class="panel-body">
          <div class="filter-bar" id="report-filters">
            ${field({ label: '搜索', name: 'q', value: state.q, placeholder: 'SKU / 事件号' })}
            ${field({ label: '复盘状态', name: 'status', value: state.status, options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.reportStatus).map(([value, label]) => ({ value, label }))] })}
            ${field({ label: 'ROI 分档', name: 'band', value: state.band, options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.roiBand).map(([value, label]) => ({ value, label }))] })}
            <div class="spacer"></div>
            ${
              latest
                ? `<span class="mono muted">最近批次 ${esc(latest.run_no)}：${esc(latest.log_text || '')}</span>`
                : ''
            }
          </div>
        </div>
        ${table({
          rows: reports.items.map(reportRow),
          columns: [
            { key: 'event_no', label: '事件', render: (row) => `<b class="mono">${esc(row.event_no)}</b><div class="sub">${esc(row.kind_label || '')}</div>` },
            { key: 'sku_name', label: 'SKU', render: (row) => `<b>${esc(row.sku_code)}</b> ${esc(row.sku_name)}<div class="sub">${esc(row.channel_label || '')}</div>` },
            { key: 'discount', label: '折扣', className: 'num', render: (row) => `−${((row.discount || 0) * 100).toFixed(1)}%` },
            { key: 'baseline_qty', label: '基线/实际', className: 'num', render: (row) => `${fmtDec(row.baseline_qty, 0)}/${fmtDec(row.actual_qty, 0)}` },
            { key: 'lift_pct', label: '增量', className: 'num', render: (row) => fmtPct(row.lift_pct) },
            { key: 'elasticity', label: '弹性', className: 'num', render: (row) => esc(fmtElasticity(row.elasticity, row.elasticity === null ? 'unknown' : 'ok')) },
            { key: 'roi', label: 'ROI', className: 'num', render: (row) => `<span class="badge ${bandTone(row.roi_band)}">${fmtRoi(row.roi)}</span>` },
            { key: 'status', label: '复盘', render: (row) => `<span class="badge ${statusTone(row.status)}">${esc(ENUMS.reportStatus[row.status] || row.status)}</span>` },
          ],
          empty: { title: '这个筛选下没有复盘条目', hint: '清空筛选或先发起一次测算。' },
        })}
      </section>`;

    const filters = view.querySelector('#report-filters');
    filters?.addEventListener('change', () => {
      state.status = filters.querySelector('[name=status]').value;
      state.band = filters.querySelector('[name=band]').value;
      liftPage.render(view, ctx);
    });
    filters?.querySelector('[name=q]')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        state.q = event.target.value.trim();
        liftPage.render(view, ctx);
      }
    });
    view.querySelectorAll('section.panel table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const id = Number(row.dataset.id);
        const run = runs.items.find((item) => item.id === id);
        if (run) {
          state.runId = String(run.id);
          liftPage.render(view, ctx);
          return;
        }
        const report = reports.items.find((item) => item.id === id);
        if (report) openReport(view, ctx, report);
      });
    });
    view.querySelector('#new-run')?.addEventListener('click', async () => {
      const button = view.querySelector('#new-run');
      button.disabled = true;
      button.textContent = '测算中…';
      try {
        const run = await api.post('/api/lift-runs', { trigger: 'manual' });
        toast(`批次 ${run.run_no} 完成：${run.report_count} 条复盘，亏损 ${(run.metrics || {}).loss_events} 场`);
        state.runId = String(run.id);
        await liftPage.render(view, ctx);
      } catch (err) {
        toast(errorMessage(err), 'err');
        button.disabled = false;
        button.textContent = '发起测算';
      }
    });
    view.querySelector('#clear-run')?.addEventListener('click', () => {
      state.runId = '';
      liftPage.render(view, ctx);
    });
    view.querySelector('#export-reports')?.addEventListener('click', async () => {
      try {
        await api.download(`/api/exports/reports.csv${state.runId ? `?run_id=${state.runId}` : ''}`, 'lift-reports.csv');
        toast('已开始下载复盘清单');
      } catch (err) {
        toast(errorMessage(err), 'err');
      }
    });
  },
};

export default liftPage;
