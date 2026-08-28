// PapersCrawler Web UI — i18n + utility

// ── Translations ──────────────────────────────────────────────────────────────

const I18N = {
  zh: {
    'nav.dashboard': '仪表盘',
    'nav.papers': '论文',
    'nav.report': '报告',
    'nav.review': '人工审核',

    'pipeline.success': '成功',
    'pipeline.failed': '失败',
    'pipeline.skipped': '跳过',

    'papers.title': '论文',
    'papers.sort_label': '排序：',
    'papers.sort_created': '入库日期',
    'papers.sort_published': '发表日期',
    'papers.sort_summary': '总结生成时间',
    'papers.relevance': 'LLM',
    'papers.skipped': '已跳过',
    'papers.pending': '待处理',
    'papers.title_col': '标题',
    'papers.journal': '期刊',
    'papers.date': '日期',
    'papers.doi': 'DOI',
    'papers.pub_warning': '发表日期来自多个数据源（出版社页 > CrossRef > RSS），精度可能有限。',
    'papers.category_label': 'LLM 分类：',
    'papers.category_a': '仅 A',
    'papers.category_b': '仅 B',
    'papers.category_ab': 'A/B',
    'papers.category_all': '全部',
    'papers.empty': '当前筛选下没有匹配的论文。',
    'papers.page_info': '共 {total} 篇 · 第 {page} / {pages} 页',
    'papers.per_page': '每页',
    'papers.prev': '上一页',
    'papers.next': '下一页',
    'papers.has_summary': '已生成总结',

    'report.title': '报告',
    'report.choose_report': '查看报告：',
    'report.no_report': '暂无报告。',
    'report.download': '下载',
    'report.select_hint': '请选择一份报告',

    'dashboard.title': '仪表盘',
    'dashboard.total_papers': '论文总数',
    'dashboard.pending_report': '待报告 (A/B)',
    'dashboard.publishers': '出版社',
    'dashboard.phase_charts': '流水线状态',
    'dashboard.breakdown_title': '失败 / 跳过原因',
    'dashboard.weekly_title': '近 7 日收集趋势',
    'dashboard.weekly_loading': '加载中...',
    'dashboard.weekly_reportable': '可报告',
    'dashboard.weekly_failed': '处理失败',
    'dashboard.weekly_other': '其他 / 待处理',
  },

  en: {
    'nav.dashboard': 'Dashboard',
    'nav.papers': 'Papers',
    'nav.report': 'Report',
    'nav.review': 'Manual Review',

    'pipeline.success': 'Success',
    'pipeline.failed': 'Failed',
    'pipeline.skipped': 'Skipped',

    'papers.title': 'Papers',
    'papers.sort_label': 'Sort by:',
    'papers.sort_created': 'Created Date',
    'papers.sort_published': 'Published Date',
    'papers.sort_summary': 'Summary Date',
    'papers.relevance': 'LLM',
    'papers.skipped': 'Skipped',
    'papers.pending': 'Pending',
    'papers.title_col': 'Title',
    'papers.journal': 'Journal',
    'papers.date': 'Date',
    'papers.doi': 'DOI',
    'papers.pub_warning': 'Published dates come from multiple sources (publisher page > CrossRef > RSS) and may be inaccurate.',
    'papers.category_label': 'LLM Category:',
    'papers.category_a': 'A Only',
    'papers.category_b': 'B Only',
    'papers.category_ab': 'A/B',
    'papers.category_all': 'All',
    'papers.empty': 'No papers match the current filter.',
    'papers.page_info': '{total} total · page {page} / {pages}',
    'papers.per_page': 'Per page',
    'papers.prev': 'Prev',
    'papers.next': 'Next',
    'papers.has_summary': 'Has summary',

    'report.title': 'Report',
    'report.choose_report': 'Report:',
    'report.no_report': 'No reports found.',
    'report.download': 'Download',
    'report.select_hint': 'Select a report',

    'dashboard.title': 'Dashboard',
    'dashboard.total_papers': 'Total Papers',
    'dashboard.pending_report': 'Pending Report (A/B)',
    'dashboard.publishers': 'Publishers',
    'dashboard.phase_charts': 'Pipeline Status',
    'dashboard.breakdown_title': 'Failed / Skipped reasons',
    'dashboard.weekly_title': 'Weekly Collection (Last 7 Days)',
    'dashboard.weekly_loading': 'Loading...',
    'dashboard.weekly_reportable': 'Reportable',
    'dashboard.weekly_failed': 'Processing Failed',
    'dashboard.weekly_other': 'Other / Pending',
  },
};

// ── i18n engine ──────────────────────────────────────────────────────────────

let currentLang = localStorage.getItem('paperscrawler_lang') || 'zh';

function getI18n(key, vars) {
  const text = I18N[currentLang]?.[key];
  if (text === null || text === undefined) return '';
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? `{${k}}`);
}

function switchLanguage(lang) {
  currentLang = lang;
  localStorage.setItem('paperscrawler_lang', lang);
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const varsAttr = el.getAttribute('data-i18n-vars');
    const vars = varsAttr ? JSON.parse(varsAttr) : undefined;
    const text = getI18n(key, vars);
    if (text) {
      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
        el.placeholder = text;
      } else {
        el.innerHTML = text;
      }
    }
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    const key = el.getAttribute('data-i18n-title');
    const varsAttr = el.getAttribute('data-i18n-vars');
    const vars = varsAttr ? JSON.parse(varsAttr) : undefined;
    const text = getI18n(key, vars);
    if (text) el.title = text;
  });
  // update toggle button text
  const btn = document.getElementById('lang-toggle');
  if (btn) btn.textContent = currentLang === 'zh' ? 'EN' : '中';
}

// ── Modal ─────────────────────────────────────────────────────────────────────

let modalCallback = null;

function showModal(title, bodyHTML, confirmText, callback) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHTML;
  document.getElementById('modal-confirm').textContent = confirmText || 'Confirm';
  document.getElementById('modal-overlay').style.display = 'flex';
  modalCallback = callback;
}

function closeModal() {
  document.getElementById('modal-overlay').style.display = 'none';
  modalCallback = null;
}

document.getElementById('modal-confirm')?.addEventListener('click', function() {
  if (modalCallback) modalCallback();
  closeModal();
});

// ── Toast notifications ─────────────────────────────────────────────────────

function _getToastContainer() {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  return container;
}

function showToast(message, actions) {
  const container = _getToastContainer();
  const toast = document.createElement('div');
  toast.className = 'toast';
  const messageEl = document.createElement('div');
  messageEl.className = 'toast-message';
  messageEl.textContent = message;
  toast.appendChild(messageEl);
  if (actions && actions.length) {
    const actionsEl = document.createElement('div');
    actionsEl.className = 'toast-actions';
    actions.forEach(action => {
      const a = document.createElement('a');
      a.href = action.href;
      a.textContent = action.text;
      a.className = action.primary ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
      a.addEventListener('click', () => toast.remove());
      actionsEl.appendChild(a);
    });
    toast.appendChild(actionsEl);
  }
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'toast-out 0.2s ease-in forwards';
    toast.addEventListener('animationend', () => toast.remove());
  }, 8000);
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  switchLanguage(currentLang);
});
