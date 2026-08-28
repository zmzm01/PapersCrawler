function escapeHtml(value: string): string {
	return value
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('"', '&quot;')
		.replaceAll("'", '&#039;');
}

function inlineMarkdown(value: string): string {
	return escapeHtml(value)
		.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
		.replace(/`([^`]+)`/g, '<code>$1</code>');
}

function normalizeMarkdownLines(value: string): string {
	return value
		.replace(/\\n\\n/g, '\n\n')
		.replace(/\\n(?=(?:#{1,6}\s|[-*]\s|\d+[.)]\s|[\u3400-\u9fff]))/g, '\n');
}

/** Render the constrained Markdown emitted by the report summarizer. */
export function renderReportMarkdown(markdown: string): string {
	const lines = normalizeMarkdownLines(markdown).replace(/\r\n/g, '\n').split('\n');
	const output: string[] = [];
	let paragraph: string[] = [];
	let listType: 'ul' | 'ol' | undefined;
	let listItems: string[] = [];

	const flushParagraph = () => {
		if (paragraph.length > 0) {
			output.push(`<p>${paragraph.map(inlineMarkdown).join('<br />')}</p>`);
			paragraph = [];
		}
	};
	const flushList = () => {
		if (listType) {
			output.push(`<${listType}>${listItems.map((item) => `<li>${inlineMarkdown(item)}</li>`).join('')}</${listType}>`);
			listType = undefined;
			listItems = [];
		}
	};

	for (const line of lines) {
		const heading = /^(#{1,6})\s+(.+)$/.exec(line);
		const unordered = /^\s*[-*]\s+(.+)$/.exec(line);
		const ordered = /^\s*\d+[.)]\s+(.+)$/.exec(line);
		if (heading) {
			flushParagraph();
			flushList();
			const level = Math.min(6, heading[1].length + 2);
			output.push(`<h${level} class="report-markdown-heading report-markdown-heading-${level}">${inlineMarkdown(heading[2])}</h${level}>`);
		} else if (unordered || ordered) {
			flushParagraph();
			const nextType = unordered ? 'ul' : 'ol';
			if (listType && listType !== nextType) flushList();
			listType = nextType;
			listItems.push((unordered ?? ordered)![1]);
		} else if (line.trim() === '') {
			flushParagraph();
			flushList();
		} else {
			flushList();
			paragraph.push(line);
		}
	}
	flushParagraph();
	flushList();
	return output.join('\n');
}
