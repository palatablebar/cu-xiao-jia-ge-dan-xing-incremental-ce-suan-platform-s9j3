import { api } from '../api.js';
import { can } from '../config.js';
import { errorBox, errorMessage, esc, field, fmtInt, kv, toast } from '../ui.js';

/** 导出与口径：两份 CSV + 算法口径 + 字段说明（只读角色看不到这一页）。 */
export const exportPage = {
  async render(view, ctx) {
    const allowed = can(ctx.user.role, 'export:read');
    let reports;
    try {
      reports = await api.get('/api/lift-reports', { limit: 1 });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => exportPage.render(view, ctx));
      return;
    }
    view.innerHTML = `
      ${!allowed ? '<div class="error-box"><span>只读角色没有导出权限（后端 403）。</span></div>' : ''}
      <div class="grid-2">
        <section class="panel">
          <div class="panel-head"><h2>复盘清单 CSV</h2><span class="meta">lift-reports.csv</span></div>
          <div class="panel-body">
            ${kv([
              ['行数', `<span class="mono">${fmtInt(reports.total)} 行（一场活动一行）</span>`],
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
      </div>

      <section class="panel">
        <div class="panel-head"><h2>导出自检</h2><span class="meta">before you send</span></div>
        <div class="panel-body">
          <div class="filter-bar">
            ${field({ label: '批次（可选）', name: 'run_id', placeholder: '留空导出全部批次' })}
            <div class="spacer"></div>
            <span class="mono muted">导出动作会写一条 audit：export.reports</span>
          </div>
          <p class="mono muted" style="margin:10px 0 0">下载后请核对：事件号 20 行、亏损 3 行（B6 / C2 / B1）、A2 的 ROI 为 1.24。</p>
        </div>
      </section>`;

    const runInput = view.querySelector('[name=run_id]');
    view.querySelector('#dl-reports')?.addEventListener('click', async () => {
      try {
        const runId = (runInput?.value || '').trim();
        await api.download(`/api/exports/reports.csv${runId ? `?run_id=${runId}` : ''}`, 'lift-reports.csv');
        toast('已开始下载复盘清单');
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
    void esc;
  },
};

export default exportPage;
