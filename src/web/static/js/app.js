// PapersCrawler Web UI — i18n + utility

// ── Translations ──────────────────────────────────────────────────────────────

const I18N = {
  zh: {
    'nav.home': '主页',
    'nav.dashboard': '仪表盘',
    'nav.pipeline': '流水线',
    'nav.papers': '论文',
    'nav.report': '报告',
    'nav.logs': '日志',

    'pipeline.title': '流水线控制',
    'pipeline.live_log': '实时日志',
    'pipeline.filter': '过滤：',
    'pipeline.waiting': '等待日志输出...',
    'pipeline.success': '成功',
    'pipeline.failed': '失败',
    'pipeline.skipped': '跳过',
    'pipeline.pending': '待处理',
    'pipeline.phase': '阶段',
    'pipeline.label': '名称',
    'pipeline.status': '状态',

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

    'report.title': '报告',
    'report.choose_report': '查看报告：',
    'report.no_report': '暂无报告。',
    'report.download': '下载',
    'report.select_hint': '请选择一份报告',

    'logs.title': '流水线日志',
    'logs.description': '显示最近约 200 KB 的 <code>data/PaperCrawler.log</code>。日志文件累积所有运行记录（CLI + Web UI）。可使用下方过滤器按级别筛选。',
    'logs.filter': '过滤：',

    'home.subtitle': '学术文献自动追踪与推送系统',
    'home.intro_title': '项目介绍',
    'home.intro_text': 'PapersCrawler 自动追踪 <span class="intro-highlight">7 大出版社 21 种核心期刊</span>，通过 <span class="intro-highlight">8 阶段流水线</span> 完成从论文发现、元数据补充、LLM 相关性判断、PDF 全文解析、结构化总结到日报推送的全流程自动化。',
    'home.tech_stack': '技术栈',
    'home.quickstart': '快速开始',
    'home.quickstart_desc': '复制 .env 配置文件 → 安装 Python 依赖 → 启动 Web UI',
    'home.publishers': '出版社',
    'home.papers_count': '论文总数',
    'home.phases_count': '流水线阶段',
    'home.guide': '快速指南',
    'home.guide_page': '页面',
    'home.guide_what': '功能',
    'home.guide_notes': '注意事项',
    'home.pipeline_desc': '查看流水线状态，触发运行请用 tools/run_pipeline.py',
    'home.pipeline_notes': '只读展示。',
    'home.papers_desc': '浏览论文，支持筛选和排序',
    'home.papers_notes': '报告生成请用 tools/preview_report.py。',
    'home.report_desc': '查看已生成的报告，按来源/日期筛选',
    'home.report_notes': '报告按自动/用户来源分组，按日期降序排列。通过侧栏或下拉菜单打开。',
    'home.logs_desc': '查看流水线日志文件，按级别过滤（只读）',
    'home.logs_notes': '显示最近 ~200 KB，新日志通过 SSE 实时推送。',
    'home.dashboard_desc': '查看流水线状态图表、论文数量、待报告统计及错误分解。',
    'home.dashboard_notes': '每 10 秒自动刷新，展示流水线实时健康状况。',
    'home.visit': '前往',


    'dashboard.title': '仪表盘',
    'dashboard.total_papers': '论文总数',
    'dashboard.pending_report': '待报告 (A/B)',
    'dashboard.publishers': '出版社',
    'dashboard.phases': '流水线阶段',
    'dashboard.phase_charts': '流水线状态',
    'dashboard.breakdown_title': '失败 / 跳过原因',
    'dashboard.weekly_title': '近 7 日收集趋势',
    'dashboard.weekly_loading': '加载中...',
    'dashboard.weekly_reportable': '待报告',
    'dashboard.weekly_failed': '处理失败',
    'dashboard.weekly_other': '其他/处理中',


  },

  en: {
    'nav.home': 'Home',
    'nav.dashboard': 'Dashboard',
    'nav.pipeline': 'Pipeline',
    'nav.papers': 'Papers',
    'nav.report': 'Report',
    'nav.logs': 'Logs',

    'pipeline.title': 'Pipeline Control',
    'pipeline.live_log': 'Live Log',
    'pipeline.filter': 'Filter:',
    'pipeline.waiting': 'Waiting for log output...',
    'pipeline.success': 'Success',
    'pipeline.failed': 'Failed',
    'pipeline.skipped': 'Skipped',
    'pipeline.pending': 'Pending',
    'pipeline.phase': 'Phase',
    'pipeline.label': 'Label',
    'pipeline.status': 'Status',

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

    'report.title': 'Report',
    'report.choose_report': 'Report:',
    'report.no_report': 'No reports found.',
    'report.download': 'Download',
    'report.select_hint': 'Select a report',

    'logs.title': 'Pipeline Logs',
    'logs.description': 'Showing last ~200 KB of <code>data/PaperCrawler.log</code>. The log file accumulates across all runs (CLI + Web UI). Use filter below to narrow by level.',
    'logs.filter': 'Filter:',

    'home.subtitle': 'Academic paper auto-tracking &amp; push system',
    'home.intro_title': 'About',
    'home.intro_text': 'PapersCrawler automatically tracks <span class="intro-highlight">21 journals from 7 publishers</span> through an <span class="intro-highlight">8-phase pipeline</span> — discovery, metadata enrichment, page scraping, relevance filtering, PDF parsing, structured summarization, report generation, and email delivery.',
    'home.tech_stack': 'Tech Stack',
    'home.quickstart': 'Quick Start',
    'home.quickstart_desc': 'Copy .env → install Python deps → start Web UI',
    'home.publishers': 'Publishers',
    'home.papers_count': 'Papers in DB',
    'home.phases_count': 'Pipeline Phases',
    'home.guide': 'Quick Guide',
    'home.guide_page': 'Page',
    'home.guide_what': 'What you can do',
    'home.guide_notes': 'Notes',
    'home.pipeline_desc': 'View pipeline status, run via tools/run_pipeline.py',
    'home.pipeline_notes': 'Read-only display.',
    'home.papers_desc': 'Browse papers, filter by category, sort by date.',
    'home.papers_notes': 'Generate reports via tools/preview_report.py.',
    'home.report_desc': 'View generated reports, filter by source and date.',
    'home.report_notes': 'Reports are grouped by auto/user source and sorted by date. Use the sidebar or dropdown to open one.',
    'home.logs_desc': 'View pipeline log file, filter by severity level (read-only)',
    'home.logs_notes': 'Shows most recent ~200 KB. New log lines arrive in real time via SSE.',
    'home.dashboard_desc': 'View pipeline status charts, paper counts, pending report stats and error breakdowns.',
    'home.dashboard_notes': 'Auto-refreshes every 10s. Shows real-time pipeline health.',
    'home.visit': 'Go to',

    'dashboard.title': 'Dashboard',
    'dashboard.total_papers': 'Total Papers',
    'dashboard.pending_report': 'Pending Report (A/B)',
    'dashboard.publishers': 'Publishers',
    'dashboard.phases': 'Pipeline Phases',
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
