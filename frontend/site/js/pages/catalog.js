import { api } from '../api.js';
import { ENUMS, can } from '../config.js';
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
  kv,
  table,
  toast,
} from '../ui.js';

const state = { q: '', category: '', channel: '' };

/** SKU 与价格活动：两页共用 table + drawer 组件；管理员可登记 SKU 与活动。 */
export const catalogPage = {
  async render(view, ctx) {
    let skus;
    let events;
    try {
      [skus, events] = await Promise.all([
        api.get('/api/skus', { q: state.q, category: state.category, channel: state.channel, limit: 100 }),
        api.get('/api/price-events', { limit: 100 }),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => catalogPage.render(view, ctx));
      return;
    }
    const categories = skus.categories || [];
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>SKU 主数据</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${fmtInt(skus.total)} 个 · 成本与牌价决定 ROI 分子分母</span>
            ${can(ctx.user.role, 'sku:write') ? '<button class="btn sm accent" id="new-sku">登记 SKU</button>' : ''}
          </div>
        </div>
        <div class="panel-body">
          <div class="filter-bar" id="sku-filters">
            ${field({ label: '搜索', name: 'q', value: state.q, placeholder: '编码 / 名称' })}
            ${field({
              label: '品类',
              name: 'category',
              value: state.category,
              options: [{ value: '', label: '全部' }, ...categories.map((item) => ({ value: item, label: item }))],
            })}
            ${field({
              label: '渠道',
              name: 'channel',
              value: state.channel,
              options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.channel).map(([value, label]) => ({ value, label }))],
            })}
            <div class="spacer"></div>
          </div>
        </div>
        ${table({
          rows: skus.items,
          columns: [
            { key: 'code', label: '编码', className: 'mono' },
            { key: 'name', label: '名称', render: (row) => `<b>${esc(row.name)}</b><div class="sub">${esc(row.spec || '')} · ${esc(row.category)}</div>` },
            { key: 'channel_label', label: '渠道' },
            { key: 'cost', label: '成本', className: 'num', render: (row) => fmtDec(row.cost, 2) },
            { key: 'list_price', label: '牌价', className: 'num', render: (row) => fmtDec(row.list_price, 2) },
            { key: 'margin_rate', label: '毛利率', className: 'num', render: (row) => fmtPct(row.margin_rate) },
            { key: 'event_count', label: '活动', className: 'num' },
          ],
          empty: { title: '没有匹配的 SKU', hint: '清空筛选条件再试。' },
        })}
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>价格活动</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${fmtInt(events.total)} 场</span>
            ${can(ctx.user.role, 'event:write') ? '<button class="btn sm accent" id="new-event">新建活动</button>' : ''}
          </div>
        </div>
        ${table({
          rows: events.items,
          columns: [
            { key: 'event_no', label: '事件号', className: 'mono' },
            { key: 'sku_name', label: 'SKU', render: (row) => `<b>${esc(row.sku_code)}</b> ${esc(row.sku_name)}` },
            { key: 'kind_label', label: '玩法' },
            { key: 'channel_label', label: '渠道' },
            { key: 'base_price', label: '牌价', className: 'num', render: (row) => fmtDec(row.base_price, 2) },
            { key: 'promo_price', label: '促销价', className: 'num', render: (row) => fmtDec(row.promo_price, 2) },
            { key: 'discount', label: '折扣', className: 'num', render: (row) => fmtPct(-row.discount, 1).replace('+', '') },
            { key: 'start_on', label: '窗口', render: (row) => `<span class="mono">${esc(row.start_on)} → ${esc(row.end_on)}</span>` },
          ],
        })}
      </section>`;

    const filters = view.querySelector('#sku-filters');
    filters?.querySelectorAll('select').forEach((node) => node.addEventListener('change', () => {
      state.category = filters.querySelector('[name=category]').value;
      state.channel = filters.querySelector('[name=channel]').value;
      catalogPage.render(view, ctx);
    }));
    filters?.querySelector('[name=q]')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        state.q = event.target.value.trim();
        catalogPage.render(view, ctx);
      }
    });

    view.querySelectorAll('section.panel table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const id = Number(row.dataset.id);
        const sku = skus.items.find((item) => item.id === id);
        const event = events.items.find((item) => item.id === id);
        if (sku) openSku(view, ctx, sku);
        else if (event) openEvent(view, ctx, event);
      });
    });

    view.querySelector('#new-sku')?.addEventListener('click', () => openCreateSku(view, ctx, categories));
    view.querySelector('#new-event')?.addEventListener('click', () => openCreateEvent(view, ctx, skus.items));
  },
};

async function openSku(view, ctx, sku) {
  let detail;
  try {
    detail = await api.get(`/api/skus/${sku.id}`);
  } catch (err) {
    toast(errorMessage(err), 'err');
    return;
  }
  const elasticityTone = detail.elasticity_state === 'ok' ? 'info' : 'warn';
  const { root } = drawer({
    title: `${detail.code} · ${detail.name}`,
    subtitle: `${detail.category} / ${detail.spec || '—'} / ${detail.channel_label}`,
    body: `${kv([
      ['成本', `<span class="mono">${fmtDec(detail.cost, 2)}</span>`],
      ['牌价', `<span class="mono">${fmtDec(detail.list_price, 2)}</span>`],
      ['毛利', `<span class="mono">${fmtDec(detail.margin, 2)}（${fmtPct(detail.margin_rate)}）</span>`],
      ['弹性', `<span class="badge ${elasticityTone}">${esc(fmtElasticity(detail.elasticity, detail.elasticity_state))}</span> <span class="mono muted">${esc(detail.elasticity_note || '')}</span>`],
      ['日销量', `<span class="mono">${fmtInt((detail.sales || {}).total_qty)} 件 / ${fmtInt((detail.sales || {}).days)} 天</span>`],
      ['促销日', `<span class="mono">${fmtInt((detail.sales || {}).promo_days)} 天，占 ${fmtInt((detail.sales || {}).promo_qty)} 件</span>`],
      ['统计区间', `<span class="mono">${esc((detail.sales || {}).first_day || '—')} → ${esc((detail.sales || {}).last_day || '—')}</span>`],
    ])}
    <h3>该 SKU 的活动</h3>
    ${
      (detail.events || []).length
        ? table({
            rows: detail.events,
            columns: [
              { key: 'event_no', label: '事件号', className: 'mono' },
              { key: 'kind', label: '玩法', render: (row) => esc(ENUMS.eventKind[row.kind] || row.kind) },
              { key: 'promo_price', label: '促销价', className: 'num', render: (row) => fmtDec(row.promo_price, 2) },
              { key: 'start_on', label: '窗口', render: (row) => `<span class="mono">${esc(row.start_on)} → ${esc(row.end_on)}</span>` },
            ],
          })
        : '<p class="muted">该 SKU 还没有活动记录。</p>'
    }`,
    footer: `<button class="btn ghost" data-series>看销量曲线</button>`,
  });
  root.querySelector('[data-series]')?.addEventListener('click', () => {
    location.hash = `#/series?sku=${detail.id}`;
  });
}

function openEvent(view, ctx, event) {
  const { root } = drawer({
    title: `${event.event_no} · ${event.sku_name}`,
    subtitle: `${event.kind_label} / ${event.channel_label} / ${event.days} 天`,
    body: `${kv([
      ['牌价', `<span class="mono">${fmtDec(event.base_price, 2)}</span>`],
      ['促销价', `<span class="mono">${fmtDec(event.promo_price, 2)}</span>`],
      ['折扣', `<span class="mono">${fmtPct(-event.discount, 1).replace('+', '')}</span>`],
      ['窗口', `<span class="mono">${esc(event.start_on)} → ${esc(event.end_on)}</span>`],
      ['备注', esc(event.note || '—')],
    ])}`,
    footer: `<button class="btn ghost" data-series>看销量曲线</button>`,
  });
  root.querySelector('[data-series]')?.addEventListener('click', () => {
    location.hash = `#/series?sku=${event.sku_id}`;
  });
}

function openCreateSku(view, ctx, categories) {
  const { root, close } = drawer({
    title: '登记 SKU',
    subtitle: '成本与牌价决定 ROI，写错会让复盘失真',
    body: `<form id="sku-form" style="display:grid;gap:11px">
      ${field({ label: '编码（大写字母+数字）', name: 'code', placeholder: 'G1' })}
      ${field({ label: '名称', name: 'name', placeholder: '例如：燕麦奶 250ml×12' })}
      ${field({ label: '品类', name: 'category', value: categories[0] || '酸奶', options: categories.map((item) => ({ value: item, label: item })) })}
      ${field({ label: '规格', name: 'spec', placeholder: '250ml×12' })}
      ${field({ label: '渠道', name: 'channel', value: 'hypermarket', options: Object.entries(ENUMS.channel).map(([value, label]) => ({ value, label })) })}
      ${field({ label: '成本（元）', name: 'cost', type: 'number', value: '0', attrs: 'step="0.01" min="0"' })}
      ${field({ label: '牌价（元）', name: 'list_price', type: 'number', value: '0', attrs: 'step="0.01" min="0.01"' })}
      <div class="form-error" id="sku-error"></div>
      <button class="btn accent" type="submit">保存</button>
    </form>`,
  });
  root.querySelector('#sku-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
      await api.post('/api/skus', {
        code: form.code.value.trim().toUpperCase(),
        name: form.name.value.trim(),
        category: form.category.value,
        spec: form.spec.value.trim() || null,
        channel: form.channel.value,
        cost: Number(form.cost.value),
        list_price: Number(form.list_price.value),
      });
      toast('SKU 已登记');
      close();
      await catalogPage.render(view, ctx);
    } catch (err) {
      root.querySelector('#sku-error').textContent = err.code === 'CONFLICT' ? '编码已存在' : errorMessage(err);
    }
  });
}

function openCreateEvent(view, ctx, skus) {
  const { root, close } = drawer({
    title: '新建价格活动',
    subtitle: '促销价必须低于牌价，否则后端返回 422',
    body: `<form id="event-form" style="display:grid;gap:11px">
      ${field({ label: '事件号', name: 'event_no', placeholder: 'PE-2621' })}
      ${field({ label: 'SKU', name: 'sku_id', options: skus.map((item) => ({ value: item.id, label: `${item.code} ${item.name}` })) })}
      ${field({ label: '玩法', name: 'kind', value: 'discount', options: Object.entries(ENUMS.eventKind).map(([value, label]) => ({ value, label })) })}
      ${field({ label: '促销价（元）', name: 'promo_price', type: 'number', value: '0', attrs: 'step="0.01" min="0.01"' })}
      ${field({ label: '开始日', name: 'start_on', type: 'date', value: '2026-09-10' })}
      ${field({ label: '结束日', name: 'end_on', type: 'date', value: '2026-09-16' })}
      ${field({ label: '备注', name: 'note' })}
      <div class="form-error" id="event-error"></div>
      <button class="btn accent" type="submit">保存</button>
    </form>`,
  });
  root.querySelector('#event-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    try {
      await api.post('/api/price-events', {
        event_no: form.event_no.value.trim().toUpperCase(),
        sku_id: Number(form.sku_id.value),
        promo_price: Number(form.promo_price.value),
        start_on: form.start_on.value,
        end_on: form.end_on.value,
        kind: form.kind.value,
        note: form.note.value.trim() || null,
      });
      toast('活动已创建');
      close();
      await catalogPage.render(view, ctx);
    } catch (err) {
      root.querySelector('#event-error').textContent = errorMessage(err);
    }
  });
}

export default catalogPage;
