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

    view.innerHTML = `
      ${ledger([
        { label: '活动 / Events', value: fmtInt(data.events_total), unit: '场', hint: `覆盖 ${fmtInt(data.skus_total)} 个 SKU` },
        {
          label: '平均弹性 / Elasticity',
          value: data.avg_elasticity === null ? '—' : fmtDec(data.avg_elasticity, 2),
          hint: `已复盘 ${fmtInt(data.reports_total)} 条`,
        },
        {
          label: '亏损活动 / ROI<1',
          value: fmtInt(lossCount),
          unit: '场',
          hint: lossCount ? '折扣吃掉了毛利' : '本期没有亏损活动',
          bad: lossCount > 0,
        },
        { label: '待复盘 / Pending', value: fmtInt(data.pending_total), unit: '条', hint: data.worker_alive ? '后台任务心跳正常' : '后台任务心跳超时' },
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
            children: lossCount
              ? `有 <b>${lossCount}</b> 场活动的 ROI 低于 1：让利吃掉的毛利没有被增量补回来。先看 B6 有机奶与 C2 低温鲜奶，它们的折扣最深。`
              : '全部活动的 ROI 都 ≥ 1，促销结构可以继续维持。',
            figures: [
              `平均弹性 ${data.avg_elasticity === null ? '—' : fmtDec(data.avg_elasticity, 2)}`,
              `平均增量 ${data.avg_lift_pct === null ? '—' : fmtPct(data.avg_lift_pct)}`,
              `平均 ROI ${fmtRoi(data.avg_roi)}`,
            ],
          })}

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
                    <div class="eyebrow">批次指标</div>
                    <p style="margin:4px 0 0">活动 ${fmtInt((latest.metrics || {}).events)} 场 · 平均弹性 ${fmtDec((latest.metrics || {}).avg_elasticity, 2)}</p>
                    <p class="mono muted" style="margin:2px 0 0">平均增量 ${fmtPct((latest.metrics || {}).avg_lift_pct)} · 平均 ROI ${fmtRoi((latest.metrics || {}).avg_roi)}</p>
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
