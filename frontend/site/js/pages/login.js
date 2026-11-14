import { api } from '../api.js';
import { session } from '../store.js';
import { BRAND } from '../config.js';
import { errorMessage, esc, toast } from '../ui.js';

/** 登录：一页摊开的实验记录（方格纸 + 手写标题 + 示意图），右侧是贴了胶带的登录卡。 */
export const loginPage = {
  async render(root, ctx) {
    root.className = 'login-host';
    root.innerHTML = `
      <div class="login">
        <section class="login-brief">
          <div class="login-stamp">${esc(BRAND.edition)} ·  elasticity &amp; lift lab</div>
          <div class="eyebrow">牧原乳品 / 区域销售部 · 促销复盘</div>
          <h1>促销做完了<br /><em>增量到底是谁的</em>？</h1>
          <p class="tagline">${esc(BRAND.loginLead)}</p>
          <figure class="login-sketch" aria-label="促销窗口与销量的示意图">
            <svg viewBox="0 0 520 168" width="100%" height="168" role="img">
              <g stroke="oklch(0.885 0.03 118)" stroke-width="1">
                ${Array.from({ length: 7 }, (_, i) => `<line x1="34" x2="506" y1="${18 + i * 22}" y2="${18 + i * 22}" />`).join('')}
                ${Array.from({ length: 9 }, (_, i) => `<line y1="18" y2="150" x1="${34 + i * 59}" x2="${34 + i * 59}" />`).join('')}
              </g>
              <line x1="34" y1="150" x2="506" y2="150" stroke="oklch(0.68 0.04 116)" stroke-width="1.2" />
              <line x1="34" y1="18" x2="34" y2="150" stroke="oklch(0.68 0.04 116)" stroke-width="1.2" />
              <rect x="196" y="18" width="88" height="132" fill="oklch(0.63 0.12 76 / 0.16)" stroke="oklch(0.63 0.12 76 / 0.5)" stroke-dasharray="3 3" />
              <rect x="372" y="18" width="60" height="132" fill="oklch(0.63 0.12 76 / 0.16)" stroke="oklch(0.63 0.12 76 / 0.5)" stroke-dasharray="3 3" />
              <path d="M34,112 L70,108 L106,114 L140,104 L168,110 L196,86 L226,64 L256,74 L284,96 L320,108 L356,104 L372,88 L404,70 L432,92 L470,100 L506,96"
                    fill="none" stroke="oklch(0.44 0.085 128)" stroke-width="2" stroke-linejoin="round" />
              <line x1="34" y1="104" x2="506" y2="104" stroke="oklch(0.68 0.04 116)" stroke-width="1" stroke-dasharray="6 4" />
              <text x="204" y="30" font-family="Courier Prime, monospace" font-size="9" fill="oklch(0.42 0.02 120)">促销窗口</text>
              <text x="382" y="30" font-family="Courier Prime, monospace" font-size="9" fill="oklch(0.42 0.02 120)">窗口</text>
              <text x="440" y="140" font-family="Courier Prime, monospace" font-size="9" fill="oklch(0.575 0.018 118)">日</text>
              <text x="40" y="34" font-family="Courier Prime, monospace" font-size="9" fill="oklch(0.575 0.018 118)">件</text>
            </svg>
            <figcaption>示意图：实线是日销量，虚线是 90 天均值，色块是促销窗口。</figcaption>
          </figure>
          <div class="brief-points">
            ${BRAND.loginPoints
              .map(([no, text]) => `<div class="brief-point"><i>${esc(no)}</i><span>${esc(text)}</span></div>`)
              .join('')}
          </div>
          <div class="eyebrow" style="margin-top:auto">${esc(BRAND.org)} · 内部工作台 · 4,320 行日销量</div>
        </section>
        <section class="login-form-wrap">
          <form class="login-card" id="login-form" novalidate>
            <div>
              <div class="brand">${esc(BRAND.short)} / 记录本</div>
              <div class="sub">${esc(BRAND.title)}。三个演示账号权限不同，页面与按钮随角色变化。</div>
            </div>
            <div class="field">
              <label for="email">邮箱</label>
              <input id="email" name="email" type="email" autocomplete="username" value="admin@${esc(BRAND.short)}.io" required />
            </div>
            <div class="field">
              <label for="password">密码</label>
              <input id="password" name="password" type="password" autocomplete="current-password" value="Demo@2026" required />
            </div>
            <div class="form-error" id="login-error" role="alert"></div>
            <button class="btn accent" id="login-submit" type="submit">进入记录本</button>
            <div class="login-hint">
              演示账号（密码 <code>Demo@2026</code>）：<br />
              <code>admin@pricelift.io</code> 平台管理员 · <code>analyst@pricelift.io</code> 价格分析师 ·
              <code>viewer@pricelift.io</code> 销售只读
            </div>
            <div class="login-note">只读角色看不到「发起测算 / 导出」按钮，后端也会返回 403。</div>
          </form>
        </section>
      </div>`;

    const form = root.querySelector('#login-form');
    const errorNode = root.querySelector('#login-error');
    const submit = root.querySelector('#login-submit');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      errorNode.textContent = '';
      submit.disabled = true;
      submit.textContent = '正在验证…';
      try {
        const result = await api.post('/api/auth/login', {
          email: form.email.value.trim(),
          password: form.password.value,
        });
        session.set(result.access_token, result.user);
        toast(`欢迎回来，${result.user.display_name}`);
        location.hash = '#/overview';
        await ctx.reload();
      } catch (err) {
        errorNode.textContent = err.code === 'AUTH_INVALID' ? '账号或密码不正确' : errorMessage(err);
      } finally {
        submit.disabled = false;
        submit.textContent = '进入记录本';
      }
    });
  },
};

export default loginPage;
