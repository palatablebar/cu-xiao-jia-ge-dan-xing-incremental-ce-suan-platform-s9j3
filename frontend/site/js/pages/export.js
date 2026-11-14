import { api } from '../api.js';
import { can } from '../config.js';
import { errorBox, errorMessage, esc, field, fmtInt, kv, toast } from '../ui.js';

/** 导出与口径：三份 CSV（复盘 / 隔离 / 批次）+ 算法与可算性口径 + 对账自检（只读角色看不到这一页）。 */
export const exportPage = {
  async render(view, ctx) {
    const allowed = can(ctx.user.role, 'export:read');
    let reports;
    let isolations;
    let overview;
    try {
      [reports, isolations, overview] = await Promise.all([
        api.get('/api/lift-reports', { limit: 1 }),
        api.get('/api/lift-isolations', { limit: 1 }),
        api.get('/api/overview'),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => exportPage.render(view, ctx));
      return;
    }
    const recon = overview.reconciliation || {};
    const reasons = overview.isolation_reasons || [];
    view.innerHTML = `
      ${!allowed ? '<div class="error-box"><span>只读角色没有导出权限（后端 403）。</span></div>' : ''}
      <div class="grid-2">
        <section class="panel">
          <div class="panel-head"><h2>复盘清单 CSV</h2><span class="meta">lift-reports.csv</span></div>
          <div class="panel-body">
            ${kv([
              ['行数', `<span class="mono">${fmtInt(reports.total)} 行（只有可算活动，一场一行）</span>`],
              ['列', '<span class="mono">27 列：事件 / SKU / 折扣 / 基线 / 增量 / 弹性 / p / ROI / 复盘状态</span>'],
              ['编码', '<span class="mono">UTF-8 + BOM，Excel 直接打开不乱码</span>'],
              ['来源', '<span class="mono">后端 GET /api/exports/reports.csv（真实 CSV 流）</span>'],
            ])}
            <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
              <button class="btn accent" id="dl-reports" ${allowed ? '' : 'disabled'}>下载复盘清单</button>
              <button class="btn ghost" id="dl-runs" ${allowed ? '' : 'disabled'}>下载测算批次</button>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head"><h2>隔离清单 CSV</h2><span class="meta">lift-isolations.csv</span></div>
          <div class="panel-body">
            ${kv([
              ['行数', `<span class="mono">${fmtInt(isolations.total)} 行（不可算活动，逐条保留原因）</span>`],
              ['列', '<span class="mono">18 列：事件 / SKU / 隔离原因 / 缺日明细 / 对照可用/需要 / 价格异常项 / 检查明细 / 原因说明</span>'],
              ['用途', '<span class="mono">与复盘清单相加 = 活动总数；导出后与页面计数对账</span>'],
              ['来源', '<span class="mono">后端 GET /api/exports/isolations.csv</span>'],
            ])}
            <div style="margin-top:12px">
              <button class="btn accent" id="dl-isolations" ${allowed ? '' : 'disabled'}>下载隔离清单</button>
            </div>
          </div>
        </section>
      </div>

      <div class="grid-2">
        <section class="panel">
          <div class="panel-head"><h2>算法口径</h2><span class="meta">read me first</span></div>
          <div class="panel-body">
            <h3 style="font-size:0.86rem;margin-bottom:6px">弹性（算法 A）</h3>
            <pre class="code">ln(qty) = b0 + b1·ln(price) + Σγw·weekday_w + b2·promo + ε
b1 即价格弹性；正规方程 (X'X)β = X'y 手写高斯消元求解
t = β/se(β)，p 值用 t 分布双侧；R² = 1 − RSS/TSS
样本 &lt; 30 或 ln(price) 方差≈0 → 弹性不可估计</pre>
            <h3 style="font-size:0.86rem;margin:12px 0 6px">增量（算法 B）</h3>
            <pre class="code">对照组 = 同品类、窗口内无活动、按活动前日均销量匹配的 3 个 SKU
baseline = pre_treat × (post_ctrl / pre_ctrl)
lift     = post_treat / baseline − 1
平行趋势：前 14 天归一斜率差 &lt; 0.1 视为通过
ROI      = 增量毛利 / 增量单元让利 = (promo−cost) / (base−promo)</pre>
            <p class="mono muted" style="margin:8px 0 0">ROI 采用边际口径：让利只算在增量单元上；若按全量让利计算，ROI 会被 1+lift 稀释。</p>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head"><h2>可算性口径</h2><span class="meta">before you compute</span></div>
          <div class="panel-body">
            <pre class="code">1. 先核对窗口：活动前窗 + 活动窗逐日必须有销量行
   零销量(qty=0)是真实观测，不算缺日；缺日不会被静默跳过
2. 缺日 / 对照不足 / 价格异常分别隔离，保留原因与明细
3. 只有可算活动进入计算与总览均值；隔离记录可查可导出
4. 对账：活动总数 = 可算数 + 隔离数
        隔离数 = 缺日 + 对照不足 + 价格异常 + 无法测算</pre>
            <p class="mono muted" style="margin:8px 0 0">对照不足：同品类可用对照少于 3 个；价格异常：活动价非法或活动日成交价与活动价偏差 &gt; 2%。</p>
          </div>
        </section>
      </div>

      <section class="panel">
        <div class="panel-head"><h2>导出自检</h2><span class="meta">reconcile before you send</span></div>
        <div class="panel-body">
          <div class="filter-bar">
            ${field({ label: '批次（可选）', name: 'run_id', placeholder: '留空导出全部批次' })}
            <div class="spacer"></div>
            <span class="mono muted">导出动作会写一条 audit：export.reports / export.isolations</span>
          </div>
          <div class="recon-grid" style="margin-top:10px">
            <div><div class="eyebrow">活动总数</div><p class="mono">${recon.events_total === null || recon.events_total === undefined ? '—' : fmtInt(recon.events_total)}</p></div>
            <div><div class="eyebrow">可算（复盘 CSV 行数）</div><p class="mono">${fmtInt(recon.calculable_count ?? reports.total)}</p></div>
            <div><div class="eyebrow">隔离（隔离 CSV 行数）</div><p class="mono">${fmtInt(recon.isolated_count ?? isolations.total)}</p></div>
            <div><div class="eyebrow">对账</div><p><span class="badge ${recon.balanced === false ? 'danger' : 'ok'}">${recon.balanced === false ? '不一致' : '一致'}</span></p></div>
          </div>
          <div style="margin-top:8px;display:flex;gap:16px;flex-wrap:wrap">
            ${reasons.map((item) => `<span class="mono muted">${esc(item.label)} <b>${fmtInt(item.count)}</b></span>`).join('')}
          </div>
          <p class="mono muted" style="margin:10px 0 0">下载后请核对：两份 CSV 的行数之和等于活动总数，隔离原因计数之和等于隔离行数。</p>
        </div>
      </section>`;

    const runInput = view.querySelector('[name=run_id]');
    const suffix = () => {
      const runId = (runInput?.value || '').trim();
      return runId ? `?run_id=${runId}` : '';
    };
    view.querySelector('#dl-reports')?.addEventListener('click', async () => {
      try {
        await api.download(`/api/exports/reports.csv${suffix()}`, 'lift-reports.csv');
        toast('已开始下载复盘清单');
      } catch (err) {
        toast(errorMessage(err), 'err');
      }
    });
    view.querySelector('#dl-isolations')?.addEventListener('click', async () => {
      try {
        await api.download(`/api/exports/isolations.csv${suffix()}`, 'lift-isolations.csv');
        toast('已开始下载隔离清单');
      } catch (err) {
        toast(errorMessage(err), 'err');
      }
    });
    view.querySelector('#dl-runs')?.addEventListener('click', async () => {
      try {
        await api.download('/api/exports/runs.csv', 'lift-runs.csv');
        toast('已开始下载批次记录');
      } catch (err) {
        toast(errorMessage(err), 'err');
      }
    });
  },
};

export default exportPage;
