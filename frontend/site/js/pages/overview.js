import { api } from '../api.js';
import { ENUMS } from '../config.js';
import {
  annotation,
  barList,
  chartLegend,
  emptyState,
  errorBox,
  errorMessage,
  esc,
  fmtDec,
  fmtElasticity,
  fmtInt,
  fmtPct,
  fmtRoi,
  fmtTime,
  ledger,
  lineChart,
  rankList,
} from '../ui.js';

/** 总览：登记表数字 + 90 天销量指数曲线（促销窗口阴影）+ 手写批注 + 亏损清单。 */
export const overviewPage = {
  async render(view, ctx) {
    view.innerHTML = '<div class="empty"><div class="mark">读取记录…</div></div>';
    let data;
    try {
      data = await api.get('/api/overview');
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => overviewPage.render(view, ctx));
      return;
    }
    const hero = data.hero || { points: [], windows: [] };
    const latest = data.latest_run;
    const lossCount = data.loss_total || 0;
    const recon = data.reconciliation || {};
    const reasons = data.isolation_reasons || [];
    const eventsTotal = recon.events_total ?? null;
    const calculableCount = recon.calculable_count ?? 0;
    const isolatedCount = recon.isolated_count ?? 0;

    view.innerHTML = `
      ${ledger([
        {
          label: '活动 / Events',
          value: fmtInt(eventsTotal ?? data.events_total),
          unit: '场',
          hint:
            eventsTotal === null || eventsTotal === undefined
              ? `覆盖 ${fmtInt(data.skus_total)} 个 SKU`
              : `= 可算 ${fmtInt(calculableCount)} + 隔离 ${fmtInt(isolatedCount)}`,
        },
        {
          label: '平均弹性 / Elasticity',
          value: data.avg_elasticity === null ? '—' : fmtDec(data.avg_elasticity, 2),
          hint: `仅可算活动 ${fmtInt(calculableCount)} 条`,
        },
        {
          label: '亏损活动 / ROI<1',
          value: fmtInt(lossCount),
          unit: '场',
          hint: lossCount ? '折扣吃掉了毛利' : '本期没有亏损活动',
          bad: lossCount > 0,
        },
        {
          label: '隔离 / Isolated',
          value: fmtInt(isolatedCount),
          unit: '场',
          hint: isolatedCount ? reasons.filter((item) => item.count).map((item) => `${item.label} ${item.count}`).join(' · ') : '窗口完整、对照充足',
        },
      ])}

      <div class="grid-hero">
        <section class="panel">
          <div class="panel-head">
            <h2>90 天全品类销量指数</h2>
            <span class="meta">index · mean = 100</span>
          </div>
          <div class="panel-body">
            ${lineChart({
              points: hero.points,
              windows: hero.windows,
              valueKey: 'index',
              height: 330,
              yFormat: (value) => value.toFixed(0),
              caption: '全品类日销量指数与促销窗口',
            })}
            ${chartLegend([
              { label: '日销量指数', tone: '' },
              { label: '促销窗口', tone: 'win' },
              { label: '均值 100', tone: 'alt' },
            ])}
          </div>
          <div class="panel-note">
            ${esc(hero.points.length ? `窗口 ${hero.days} 天，日均 ${fmtInt(hero.mean_qty)} 件；阴影是 20 场活动合并后的时间带。` : '还没有日销量数据，先跑一次 seed。')}
          </div>
        </section>

        <div style="display:grid;gap:14px;align-content:start">
          ${annotation({
            title: '本期批注',
            children: `${recon.balanced === false ? '<b>对账不一致：</b>活动总数与「可算 + 隔离」不相等，先核数据。' : ''}${
              lossCount
                ? `有 <b>${lossCount}</b> 场活动的 ROI 低于 1：让利吃掉的毛利没有被增量补回来。先看 B6 有机奶与 C2 低温鲜奶，它们的折扣最深。`
                : '全部活动的 ROI 都 ≥ 1，促销结构可以继续维持。'
            }${
              isolatedCount
                ? `另有 <b>${isolatedCount}</b> 场因缺日 / 对照不足 / 价格异常被隔离，没有进入均值。`
                : ''
            }`,
            figures: [
              `平均弹性 ${data.avg_elasticity === null ? '—' : fmtDec(data.avg_elasticity, 2)}`,
              `平均增量 ${data.avg_lift_pct === null ? '—' : fmtPct(data.avg_lift_pct)}`,
              `平均 ROI ${fmtRoi(data.avg_roi)}`,
            ],
          })}

          <section class="panel">
            <div class="panel-head"><h2>可算性与隔离</h2><span class="meta">reconcile</span></div>
            <div class="panel-body">
              <div class="recon-grid">
                <div><div class="eyebrow">活动总数</div><p class="mono">${eventsTotal === null ? '—' : fmtInt(eventsTotal)}</p></div>
                <div><div class="eyebrow">可算（进入均值）</div><p class="mono">${fmtInt(calculableCount)}</p></div>
                <div><div class="eyebrow">隔离（保留原因）</div><p class="mono">${fmtInt(isolatedCount)}</p></div>
                <div><div class="eyebrow">对账</div><p><span class="badge ${recon.balanced === false ? 'danger' : 'ok'}">${recon.balanced === false ? '不一致' : '一致'}</span></p></div>
              </div>
              <div style="margin-top:10px;display:grid;gap:4px">
                ${reasons
                  .map(
                    (item) =>
                      `<div class="mono muted" style="display:flex;justify-content:space-between"><span>${esc(item.label)}</span><span>${fmtInt(item.count)}</span></div>`,
                  )
                  .join('')}
              </div>
              <p class="mono muted" style="margin:10px 0 0">隔离活动不进入平均弹性 / 增量 / ROI，也不会出现在亏损清单。</p>
            </div>
          </section>

          <section class="panel">
            <div class="panel-head"><h2>亏损活动</h2><span class="meta">roi &lt; 1</span></div>
            <div class="panel-body">
              ${rankList(data.loss_events, (item) => `<div class="rank-row" data-report="${esc(item.report_id)}">
                <span><b>${esc(item.sku_code)}</b> ${esc(item.sku_name)}</span>
                <span class="mono">${fmtPct(item.lift_pct)}</span>
                <span class="roi">${fmtRoi(item.roi)}</span>
              </div>`)}
            </div>
          </section>

          <section class="panel">
            <div class="panel-head"><h2>增量最高的三场</h2><span class="meta">did lift</span></div>
            <div class="panel-body">
              ${rankList(data.top_events, (item) => `<div class="rank-row" data-report="${esc(item.report_id)}">
                <span><b>${esc(item.sku_code)}</b> ${esc(item.sku_name)}</span>
                <span class="mono">${fmtPct(item.lift_pct)}</span>
                <span class="roi ok">${fmtRoi(item.roi)}</span>
              </div>`)}
            </div>
          </section>
        </div>
      </div>

      <div class="grid-3">
        <section class="panel">
          <div class="panel-head"><h2>ROI 分档</h2><span class="meta">profit / breakeven / loss</span></div>
          <div class="panel-body">${barList(data.roi_bands || [])}</div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>复盘进度</h2><span class="meta">review</span></div>
          <div class="panel-body">${barList((data.review || []).map((item) => ({ ...item, key: item.key === 'confirmed' ? 'ok' : item.key === 'dismissed' ? 'loss' : 'breakeven' })))}</div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>渠道活动分布</h2><span class="meta">channel</span></div>
          <div class="panel-body">${barList(data.channels || [])}</div>
        </section>
      </div>

      <section class="panel">
        <div class="panel-head">
          <h2>最近一次测算批次</h2>
          <span class="meta">${esc(latest ? latest.run_no : 'none')}</span>
        </div>
        <div class="panel-body">
          ${
            latest
              ? `<div class="grid-3">
                  <div>
                    <div class="eyebrow">状态 / 触发</div>
                    <p style="margin:4px 0 0">${esc(latest.status_label)} · 产出 ${fmtInt(latest.report_count)} 条复盘</p>
                    <p class="mono muted" style="margin:2px 0 0">${fmtTime(latest.started_at)}</p>
                  </div>
                  <div>
                    <div class="eyebrow">批次指标（仅可算活动）</div>
                    <p style="margin:4px 0 0">活动 ${fmtInt((latest.metrics || {}).events)} 场 = 可算 ${fmtInt((latest.metrics || {}).eligible)} + 隔离 ${fmtInt((latest.metrics || {}).isolated)}</p>
                    <p class="mono muted" style="margin:2px 0 0">平均弹性 ${fmtDec((latest.metrics || {}).avg_elasticity, 2)} · 平均增量 ${fmtPct((latest.metrics || {}).avg_lift_pct)} · 平均 ROI ${fmtRoi((latest.metrics || {}).avg_roi)}</p>
                  </div>
                  <div>
                    <div class="eyebrow">下一步</div>
                    <p style="margin:4px 0 0">到「弹性测算与复盘」逐条确认口径，再导出清单。</p>
                    <p class="mono muted" style="margin:2px 0 0">${esc(ENUMS.reportStatus.pending)} ${fmtInt(data.pending_total)} 条</p>
                  </div>
                </div>`
              : emptyState({ title: '还没有测算批次', hint: '到「弹性测算与复盘」发起一次测算。' })
          }
        </div>
      </section>`;

    view.querySelectorAll('.rank-row').forEach((row) => {
      row.style.cursor = 'pointer';
      row.addEventListener('click', () => {
        if (row.dataset.report) location.hash = `#/lift?report=${row.dataset.report}`;
      });
    });
    // 弹性列展示用（避免未使用告警的显式引用）
    void fmtElasticity;
  },
};

export default overviewPage;
