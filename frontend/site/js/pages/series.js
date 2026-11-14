import { api } from '../api.js';
import { ENUMS } from '../config.js';
import {
  annotation,
  chartLegend,
  errorBox,
  errorMessage,
  esc,
  fmtDec,
  fmtElasticity,
  fmtInt,
  fmtPct,
  kv,
  lineChart,
  table,
} from '../ui.js';

/** 销量曲线：曲线是主视觉。上：日销量 + 促销窗口；下：价格阶梯；右侧：口径与弹性结论。 */
export const seriesPage = {
  async render(view, ctx) {
    view.innerHTML = '<div class="empty"><div class="mark">读取日销量…</div></div>';
    let skus;
    try {
      skus = await api.get('/api/skus', { limit: 100 });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => seriesPage.render(view, ctx));
      return;
    }
    const featured = (skus.items || []).find((item) => item.code === 'A2') || (skus.items || [])[0] || {};
    const selectedId = Number(ctx.query.sku || featured.id || 0);
    let data;
    try {
      data = await api.get('/api/sales', { sku_id: selectedId, days: 90 });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => seriesPage.render(view, ctx));
      return;
    }
    const stats = data.stats || {};
    const elas = data.elasticity || {};

    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>${esc(data.sku.code)} · ${esc(data.sku.name)}</h2>
          <div style="display:flex;gap:10px;align-items:center">
            <select id="sku-picker" style="border:1px solid var(--rule-strong);background:var(--paper);padding:5px 8px;font-family:var(--font-mono);font-size:0.76rem">
              ${skus.items
                .map((item) => `<option value="${item.id}" ${item.id === selectedId ? 'selected' : ''}>${esc(item.code)} ${esc(item.name)}</option>`)
                .join('')}
            </select>
            <span class="meta">${esc(data.channel_label)} · ${fmtInt(stats.days)} 天</span>
          </div>
        </div>
        <div class="panel-body">
          ${lineChart({
            points: data.points,
            windows: data.windows,
            valueKey: 'qty',
            height: 340,
            caption: `${data.sku.name} 日销量与促销窗口`,
          })}
          ${chartLegend([
            { label: '日销量（件）', tone: '' },
            { label: '促销窗口', tone: 'win' },
            { label: '窗口内均值', tone: 'alt' },
          ])}
          <div style="margin-top:10px">
            ${lineChart({
              points: data.points,
              windows: data.windows,
              valueKey: 'price',
              height: 150,
              showMarkers: false,
              yFormat: (value) => value.toFixed(1),
              caption: `${data.sku.name} 成交价`,
            })}
          </div>
          ${chartLegend([{ label: '当日成交价（元）', tone: 'alt' }, { label: '促销窗口', tone: 'win' }])}
        </div>
      </section>

      <div class="grid-hero">
        <section class="panel">
          <div class="panel-head"><h2>促销窗口</h2><span class="meta">${data.windows.length} 场</span></div>
          ${table({
            rows: data.windows,
            columns: [
              { key: 'event_no', label: '事件号', className: 'mono' },
              { key: 'kind_label', label: '玩法' },
              { key: 'start_on', label: '窗口', render: (row) => `<span class="mono">${esc(row.start_on)} → ${esc(row.end_on)}</span>` },
              { key: 'promo_price', label: '促销价', className: 'num', render: (row) => fmtDec(row.promo_price, 2) },
              { key: 'discount', label: '折扣', className: 'num', render: (row) => `−${(row.discount * 100).toFixed(1)}%` },
            ],
            empty: { title: '这个 SKU 没有活动', hint: '它是纯对照 SKU，正好用来做 DID 的自然增长基准。' },
          })}
        </section>

        <div style="display:grid;gap:14px;align-content:start">
          <section class="panel">
            <div class="panel-head"><h2>弹性与口径</h2><span class="meta">log-log OLS</span></div>
            <div class="panel-body">
              ${kv([
                ['弹性', `<span class="badge ${elas.state === 'ok' ? 'info' : 'warn'}">${esc(fmtElasticity(elas.beta, elas.state))}</span>`],
                ['t 值', `<span class="mono">${elas.t_value === null || elas.t_value === undefined ? '—' : fmtDec(elas.t_value, 2)}</span>`],
                ['p 值', `<span class="mono">${elas.p_value === null || elas.p_value === undefined ? '—' : elas.p_value < 0.001 ? '<0.001' : fmtDec(elas.p_value, 4)}</span>`],
                ['R²', `<span class="mono">${elas.r2 === null || elas.r2 === undefined ? '—' : fmtDec(elas.r2, 3)}</span>`],
                ['样本', `<span class="mono">${fmtInt(elas.n)} 天</span>`],
                ['促销日均', `<span class="mono">${fmtDec(stats.avg_promo_qty, 1)} 件 / 非促销 ${fmtDec(stats.avg_base_qty, 1)} 件</span>`],
                ['均价', `<span class="mono">${fmtDec(stats.avg_price, 2)} 元</span>`],
              ])}
            </div>
          </section>
          ${annotation({
            title: '记录者批注',
            children:
              elas.state === 'ok'
                ? `弹性 ${fmtDec(elas.beta, 2)}：价格每降 1%，日销量约增 ${fmtDec(Math.abs(elas.beta), 2)}%。${Math.abs(elas.beta) >= 1 ? '属于富有弹性，浅折扣也能带来明显增量。' : '弹性偏弱，靠降价拉量效率不高。'}`
                : `这个 SKU ${esc(elas.reason || '样本不足')}，不下弹性结论。`,
            figures: [
              `促销日 ${fmtInt(stats.promo_days)} 天`,
              `促销日均 ${fmtPct((stats.avg_promo_qty || 0) / (stats.avg_base_qty || 1) - 1)} 对比非促销日`,
            ],
          })}
        </div>
      </div>`;

    view.querySelector('#sku-picker')?.addEventListener('change', (event) => {
      location.hash = `#/series?sku=${event.target.value}`;
      seriesPage.render(view, { ...ctx, query: { sku: event.target.value } });
    });
    void ENUMS;
  },
};

export default seriesPage;
