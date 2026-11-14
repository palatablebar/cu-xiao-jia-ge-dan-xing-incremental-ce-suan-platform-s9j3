/**
 * 项目品牌、导航、角色权限与枚举文案（前端唯一定义处）。
 * 后端对应：backend/src/constants/{roles,enums}.py；README 列出全部出现位置。
 */
export const BRAND = {
  short: 'pricelift',
  title: '促销价格弹性与增量测算台',
  org: '牧原乳品 · 区域销售部',
  edition: 'LAB NOTE · 2026-11',
  subject: 'A2 酸奶 950ml / ε=−1.80 / ROI 1.24',
  subtitle: '90 天日销量 + 活动价 → log-log 弹性 → DID 增量 → ROI → 复盘',
  loginLead:
    '促销前后对比会把自然增长算成自己的功劳。这里先估弹性、再扣对照组，最后只留能覆盖让利的活动。',
  loginPoints: [
    ['01', '48 个 SKU × 90 天 = 4,320 行日销量，促销窗口逐日落库。'],
    ['02', '弹性用 ln(销量) ~ ln(价) + 星期 + 促销哑变量 的最小二乘估，样本不足不下结论。'],
    ['03', '增量用同品类 3 个对照 SKU 做 DID，ROI 按边际让利口径算，亏损活动直接标出来。'],
  ],
};

export const NAV = [
  { to: '#/overview', no: '01', label: '总览', permission: 'overview:read' },
  { to: '#/catalog', no: '02', label: 'SKU 与活动', permission: 'sku:read' },
  { to: '#/series', no: '03', label: '销量曲线', permission: 'sales:read' },
  { to: '#/lift', no: '04', label: '弹性测算与复盘', permission: 'lift:read' },
  { to: '#/export', no: '05', label: '导出与口径', permission: 'export:read' },
  { to: '#/audit', no: '06', label: '审计日志', permission: 'audit:read' },
];

export const ROLE_LABELS = {
  admin: '平台管理员',
  analyst: '价格分析师',
  viewer: '销售只读',
};

export const ROLE_DUTIES = {
  admin: '维护 SKU 成本与活动、导出、看审计',
  analyst: '跑测算、提复盘结论',
  viewer: '只读曲线与复盘',
};

export const PERMISSIONS = {
  admin: [
    'overview:read',
    'sku:read',
    'sku:write',
    'event:read',
    'event:write',
    'sales:read',
    'lift:read',
    'lift:create',
    'lift:review',
    'export:read',
    'audit:read',
  ],
  analyst: ['overview:read', 'sku:read', 'event:read', 'sales:read', 'lift:read', 'lift:create', 'lift:review', 'export:read'],
  viewer: ['overview:read', 'sku:read', 'event:read', 'sales:read', 'lift:read'],
};

/** 共享枚举副本（后端 constants/enums.py）：渠道 / 玩法 / 批次状态 / 复盘状态 / ROI 分档。 */
export const ENUMS = {
  channel: {
    hypermarket: '商超',
    convenience: '便利店',
    groupbuy: '社区团购',
    distributor: '二批商',
  },
  eventKind: {
    discount: '直接降价',
    threshold: '满减',
    second_half: '第二件半价',
    member_day: '会员日',
  },
  runStatus: {
    queued: '排队中',
    running: '测算中',
    success: '完成',
    partial: '部分完成',
    failed: '失败',
  },
  reportStatus: {
    pending: '待复盘',
    confirmed: '复盘通过',
    dismissed: '复盘驳回',
  },
  roiBand: {
    profit: '增利',
    breakeven: '打平',
    loss: '亏损',
  },
  trigger: {
    manual: '手动',
    schedule: '定时',
    seed: '初始化',
  },
  elasticityState: {
    ok: '已估计',
    unknown: '不可估计',
  },
};

export function can(role, permission) {
  return (PERMISSIONS[role] || []).includes(permission);
}

export function bandTone(band) {
  return { profit: 'ok', breakeven: 'warn', loss: 'danger' }[band] || 'info';
}

export function statusTone(status) {
  return { confirmed: 'ok', dismissed: 'danger', pending: 'pending warn' }[status] || 'info';
}
