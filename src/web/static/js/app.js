// PapersCrawler Web UI — i18n + utility

// ── Translations ──────────────────────────────────────────────────────────────

const I18N = {
  zh: {
    'nav.home': '主页',
    'nav.pipeline': '流水线',
    'nav.papers': '论文',
    'nav.report': '报告',
    'nav.datasources': '数据源',
    'nav.subscriptions': '订阅',
    'nav.logs': '日志',
    'nav.config': '配置',

    'pipeline.title': '流水线控制',
    'pipeline.run_all': '运行全部阶段',
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
    'pipeline.actions': '操作',
    'pipeline.run': '运行',
    'pipeline.reset': '重置',

    'papers.title': '论文',
    'papers.sort_label': '排序：',
    'papers.sort_created': '入库日期',
    'papers.sort_published': '发表日期',
    'papers.score': '语义分',
    'papers.relevance': 'LLM 相关性',
    'papers.skipped': '已跳过',
    'papers.pending': '待处理',
    'papers.title_col': '标题',
    'papers.journal': '期刊',
    'papers.date': '日期',
    'papers.doi': 'DOI',
    'papers.pub_warning': '发表日期来自多个数据源（出版社页 > CrossRef > RSS），精度可能有限。',

    'report.title': '报告',
    'report.choose_report': '查看报告：',
    'report.choose_hint': '从上方选择一个报告查看渲染内容。',
    'report.no_report': '暂无报告。可在下方生成。',
    'report.generate_title': '生成自定义报告',
    'report.publisher': '出版社：',
    'report.select_all': '全选',
    'report.deselect_all': '取消全选',
    'report.generate': '生成报告',
    'report.doi': 'DOI',
    'report.title_col': '标题',
    'report.publisher_col': '出版社',
    'report.summary_date': '总结日期',
    'report.preview': '预览',
    'report.download': '下载',
    'report.generated': '已生成：',
    'report.select_hint': '请至少选择一篇论文',

    'logs.title': '流水线日志',
    'logs.description': '显示最近约 200 KB 的 <code>data/PaperCrawler.log</code>。日志文件累积所有运行记录（CLI + Web UI）。可使用下方过滤器按级别筛选。',
    'logs.filter': '过滤：',

    'config.title': '配置',
    'config.phase_switches': '阶段开关',
    'config.phase': '阶段',
    'config.default': '默认',
    'config.override': '覆盖',
    'config.action': '操作',
    'config.toggle': '切换',
    'config.save': '保存',
    'config.test': '测试',
    'config.domain_desc': '研究领域描述',
    'config.domain_desc_hint': '此描述用于 LLM 相关性判断（Phase E），帮助理解你的研究重点。',
    'config.connectivity': '连通性测试',
    'config.connectivity_hint': '测试外部服务的可达性。发送轻量请求并返回结果。',
    'config.publishers': 'publishers.yaml',
    'config.keywords': 'keywords.yaml',
    'config.save_confirm': '即将保存到 {file}，确定覆盖吗？',
    'config.syntax_error': 'YAML 语法错误：{msg}',
    'config.saved': '已保存到 {path}',

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
    'home.pipeline_desc': '独立运行各阶段、查看实时日志、重置阶段状态、查看进度图表',
    'home.pipeline_notes': 'Config 页面切换 SKIP 后，Pipeline 页面对应按钮会灰显禁用。重置时有影响范围确认弹窗。',
    'home.papers_desc': '浏览论文，可按入库日期或发表日期排序。',
    'home.report_desc': '选择有 LLM 总结的论文，生成 Markdown 报告，浏览器内预览和下载',
    'home.report_notes': '仅 llm_summary_status = success 的论文出现在列表中。使用复选框选择特定论文。',
    'home.logs_desc': '查看流水线日志文件，按级别过滤',
    'home.logs_notes': '显示最近 ~200 KB，新日志通过 SSE 实时推送。',
    'home.config_desc': '切换 SKIP 开关（持久化到文件）、编辑 publishers.yaml 和 keywords.yaml',
    'home.config_notes_skip': 'SKIP 开关影响 Web UI Pipeline 页面按钮状态；CLI 使用 config.py 默认值。',
    'home.config_notes_yaml': 'YAML 编辑器保存时做语法校验，需要二次确认。',
    'home.datasources_desc': '启用或禁用期刊及其 RSS / CrossRef 数据源。',
    'datasources.title': '数据源',
    'datasources.desc': '启用或禁用期刊及其数据源（RSS / CrossRef）。更改保存到独立的覆写文件，下次运行流水线时生效。',
    'datasources.enabled': '启用',
    'datasources.publisher': '出版社',
    'datasources.journal': '期刊',
    'datasources.issn': 'ISSN',
    'datasources.rss': 'RSS',
    'datasources.crossref': 'CrossRef',
    'datasources.save': '保存更改',
    'datasources.saved': '已保存',
    'home.visit': '前往',
    'subscriptions.title': '邮件订阅',
    'subscriptions.desc': '管理邮件订阅者。启用状态的订阅者会在 Phase H（邮件推送）时收到日报。',
    'subscriptions.add_title': '添加订阅者',
    'subscriptions.email': '邮箱地址',
    'subscriptions.name': '姓名（可选）',
    'subscriptions.add_btn': '添加',
    'subscriptions.import_env': '从 .env 导入',
    'subscriptions.import_env_done': '已从 .env 导入 {n} 个订阅者',
    'subscriptions.table_email': '邮箱',
    'subscriptions.table_name': '姓名',
    'subscriptions.table_status': '状态',
    'subscriptions.table_actions': '操作',
    'subscriptions.active': '启用',
    'subscriptions.inactive': '停用',
    'subscriptions.test': '测试',
    'subscriptions.disable': '停用',
    'subscriptions.enable': '启用',
    'subscriptions.delete': '删除',
    'subscriptions.test_sent': '测试邮件已发送到 {email}',
    'subscriptions.test_failed': '测试邮件发送失败: {msg}',
    'subscriptions.delete_confirm': '确定要删除 {email} 吗？',
    'subscriptions.empty': '暂无订阅者。添加一个或从 .env 导入。',
  },

  en: {
    'nav.home': 'Home',
    'nav.pipeline': 'Pipeline',
    'nav.papers': 'Papers',
    'nav.report': 'Report',
    'nav.datasources': 'Data Sources',
    'nav.subscriptions': 'Subscriptions',
    'nav.logs': 'Logs',
    'nav.config': 'Config',

    'pipeline.title': 'Pipeline Control',
    'pipeline.run_all': 'Run All Phases',
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
    'pipeline.actions': 'Actions',
    'pipeline.run': 'Run',
    'pipeline.reset': 'Reset',

    'papers.title': 'Papers',
    'papers.sort_label': 'Sort by:',
    'papers.sort_created': 'Created Date',
    'papers.sort_published': 'Published Date',
    'papers.score': 'Semantic',
    'papers.relevance': 'LLM Relevance',
    'papers.skipped': 'Skipped',
    'papers.pending': 'Pending',
    'papers.title_col': 'Title',
    'papers.journal': 'Journal',
    'papers.date': 'Date',
    'papers.doi': 'DOI',
    'papers.pub_warning': 'Published dates come from multiple sources (publisher page > CrossRef > RSS) and may be inaccurate.',

    'report.title': 'Report',
    'report.choose_report': 'Report:',
    'report.choose_hint': 'Select a report above to view rendered content.',
    'report.no_report': 'No reports found. Generate one below.',
    'report.generate_title': 'Generate Custom Report',
    'report.publisher': 'Publisher:',
    'report.select_all': 'Select All',
    'report.deselect_all': 'Deselect All',
    'report.generate': 'Generate Report',
    'report.doi': 'DOI',
    'report.title_col': 'Title',
    'report.publisher_col': 'Publisher',
    'report.summary_date': 'Summary Date',
    'report.preview': 'Preview',
    'report.download': 'Download',
    'report.generated': 'Generated: ',
    'report.select_hint': 'Select at least one paper',

    'logs.title': 'Pipeline Logs',
    'logs.description': 'Showing last ~200 KB of <code>data/PaperCrawler.log</code>. The log file accumulates across all runs (CLI + Web UI). Use filter below to narrow by level.',
    'logs.filter': 'Filter:',

    'config.title': 'Configuration',
    'config.phase_switches': 'Phase Switches',
    'config.phase': 'Phase',
    'config.default': 'Default',
    'config.override': 'Override',
    'config.action': 'Action',
    'config.toggle': 'Toggle',
    'config.save': 'Save',
    'config.test': 'Test',
    'config.domain_desc': 'Research Domain Description',
    'config.domain_desc_hint': 'This description is used by the LLM relevance checker (Phase E) to understand your research focus.',
    'config.connectivity': 'Connectivity Tests',
    'config.connectivity_hint': 'Test reachability of external services. These send lightweight requests and report back.',
    'config.publishers': 'publishers.yaml',
    'config.keywords': 'keywords.yaml',
    'config.save_confirm': 'Save to {file}? This will overwrite the file.',
    'config.syntax_error': 'YAML syntax error: {msg}',
    'config.saved': 'Saved to {path}',

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
    'home.pipeline_desc': 'Run individual phases, watch live logs with level filter, reset phase states, view progress charts',
    'home.pipeline_notes': 'SKIP toggles in Config page disable Pipeline buttons. Reset shows confirmation with impact details.',
    'home.papers_desc': 'Browse papers, sort by created or published date.',
    'home.report_desc': 'Select papers with LLM summaries, generate Markdown reports, preview in-browser and download',
    'home.report_notes': 'Only papers with llm_summary_status = success appear in the list. Use checkboxes to select specific papers.',
    'home.logs_desc': 'View pipeline log file, filter by severity level',
    'home.logs_notes': 'Shows most recent ~200 KB. New log lines arrive in real time via SSE.',
    'home.config_desc': 'Toggle SKIP switches (persisted to file), edit publishers.yaml and keywords.yaml',
    'home.config_notes_skip': 'SKIP toggles affect Web UI Pipeline buttons; CLI uses config.py defaults.',
    'home.config_notes_yaml': 'YAML editors validate syntax on save and require second confirmation.',
    'home.datasources_desc': 'Enable or disable journals and their RSS / CrossRef data sources.',
    'home.visit': 'Go to',
    'subscriptions.title': 'Email Subscriptions',
    'subscriptions.desc': 'Manage email subscribers. Active subscribers receive the daily report when Phase H (Email) runs.',
    'subscriptions.add_title': 'Add Subscriber',
    'subscriptions.email': 'Email',
    'subscriptions.name': 'Name (optional)',
    'subscriptions.add_btn': 'Add',
    'subscriptions.import_env': 'Import from .env',
    'subscriptions.import_env_done': 'Imported {n} subscribers from .env',
    'subscriptions.table_email': 'Email',
    'subscriptions.table_name': 'Name',
    'subscriptions.table_status': 'Status',
    'subscriptions.table_actions': 'Actions',
    'subscriptions.active': 'Active',
    'subscriptions.inactive': 'Inactive',
    'subscriptions.test': 'Test',
    'subscriptions.disable': 'Disable',
    'subscriptions.enable': 'Enable',
    'subscriptions.delete': 'Delete',
    'subscriptions.test_sent': 'Test email sent to {email}',
    'subscriptions.test_failed': 'Test email failed: {msg}',
    'subscriptions.delete_confirm': 'Delete {email}?',
    'subscriptions.empty': 'No subscribers yet. Add one or import from .env.',
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

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  switchLanguage(currentLang);
});
