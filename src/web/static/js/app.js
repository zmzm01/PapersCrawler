// PapersCrawler Web UI — i18n + utility

// ── Translations ──────────────────────────────────────────────────────────────

const I18N = {
  zh: {
    'nav.home': '主页',
    'nav.pipeline': '流水线',
    'nav.papers': '论文',
    'nav.report': '报告',
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

    'papers.title': '按语义相似度排序的论文',
    'papers.desc': '前 {n} 篇有语义相似度得分的论文',
    'papers.score': '得分',
    'papers.title_col': '标题',
    'papers.journal': '期刊',
    'papers.date': '日期',
    'papers.doi': 'DOI',

    'report.title': '生成报告',
    'report.publisher': '出版社：',
    'report.select_all': '全选',
    'report.deselect_all': '取消全选',
    'report.generate': '生成报告',
    'report.doi': 'DOI',
    'report.title_col': '标题',
    'report.publisher_col': '出版社',
    'report.summary_date': '总结日期',
    'report.preview': '报告预览',
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
    'config.publishers': 'publishers.yaml',
    'config.keywords': 'keywords.yaml',
    'config.save_confirm': '即将保存到 {file}，确定覆盖吗？',
    'config.syntax_error': 'YAML 语法错误：{msg}',
    'config.saved': '已保存到 {path}',

    'home.title': '项目介绍',
    'home.subtitle': '学术文献自动追踪与推送系统',
    'home.publishers': '出版社数量',
    'home.papers_count': '论文总数',
    'home.phases_count': '流水线阶段数',
    'home.guide': '快速指南',
    'home.guide_page': '页面',
    'home.guide_what': '功能',
    'home.guide_notes': '注意事项',
    'home.pipeline_desc': '独立运行各阶段、查看实时日志、重置阶段状态、查看进度图表',
    'home.pipeline_notes': '按钮始终运行阶段，不受 SKIP_PHASE 配置限制。重置时有影响范围确认弹窗。',
    'home.papers_desc': '按与研究领域语义相似度排序的论文',
    'home.papers_notes': '仅显示经过 Phase D（语义过滤）处理的论文。',
    'home.report_desc': '选择有 LLM 总结的论文，生成 Markdown 报告，浏览器内预览和下载',
    'home.report_notes': '仅 llm_summary_status = success 的论文出现在列表中。使用复选框选择特定论文。',
    'home.logs_desc': '查看流水线日志文件，按级别过滤',
    'home.logs_notes': '显示最近 ~200 KB，新日志通过 SSE 实时推送。',
    'home.config_desc': '切换 SKIP 开关（持久化到文件）、编辑 publishers.yaml 和 keywords.yaml',
    'home.config_notes_skip': 'SKIP 开关影响 CLI 行为；Web UI 不受限制（点击 Run 即可执行）。',
    'home.config_notes_yaml': 'YAML 编辑器保存时做语法校验，需要二次确认。',
    'home.visit': '前往',
  },

  en: {
    'nav.home': 'Home',
    'nav.pipeline': 'Pipeline',
    'nav.papers': 'Papers',
    'nav.report': 'Report',
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

    'papers.title': 'Papers by Semantic Similarity',
    'papers.desc': 'Top {n} papers with semantic similarity scores',
    'papers.score': 'Score',
    'papers.title_col': 'Title',
    'papers.journal': 'Journal',
    'papers.date': 'Date',
    'papers.doi': 'DOI',

    'report.title': 'Generate Report',
    'report.publisher': 'Publisher:',
    'report.select_all': 'Select All',
    'report.deselect_all': 'Deselect All',
    'report.generate': 'Generate Report',
    'report.doi': 'DOI',
    'report.title_col': 'Title',
    'report.publisher_col': 'Publisher',
    'report.summary_date': 'Summary Date',
    'report.preview': 'Report Preview',
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
    'config.publishers': 'publishers.yaml',
    'config.keywords': 'keywords.yaml',
    'config.save_confirm': 'Save to {file}? This will overwrite the file.',
    'config.syntax_error': 'YAML syntax error: {msg}',
    'config.saved': 'Saved to {path}',

    'home.title': null,
    'home.subtitle': 'Academic paper auto-tracking &amp; push system',
    'home.publishers': 'Publishers',
    'home.papers_count': 'Papers in DB',
    'home.phases_count': 'Pipeline Phases',
    'home.guide': 'Quick Guide',
    'home.guide_page': 'Page',
    'home.guide_what': 'What you can do',
    'home.guide_notes': 'Notes',
    'home.pipeline_desc': 'Run individual phases, watch live logs with level filter, reset phase states, view progress charts',
    'home.pipeline_notes': 'Buttons always run phases regardless of SKIP_PHASE config. Reset shows confirmation with impact details.',
    'home.papers_desc': 'Browse papers sorted by semantic similarity to your research domain',
    'home.papers_notes': 'Only shows papers processed by Phase D (Semantic Filter).',
    'home.report_desc': 'Select papers with LLM summaries, generate Markdown reports, preview in-browser and download',
    'home.report_notes': 'Only papers with llm_summary_status = success appear in the list. Use checkboxes to select specific papers.',
    'home.logs_desc': 'View pipeline log file, filter by severity level',
    'home.logs_notes': 'Shows most recent ~200 KB. New log lines arrive in real time via SSE.',
    'home.config_desc': 'Toggle SKIP switches (persisted to file), edit publishers.yaml and keywords.yaml',
    'home.config_notes_skip': 'SKIP toggles affect CLI behavior; Web UI ignores them (click Run to execute).',
    'home.config_notes_yaml': 'YAML editors validate syntax on save and require second confirmation.',
    'home.visit': 'Go to',
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
