export type ReportRecord = Record<string, unknown>;

export interface PublicReport {
	schemaVersion: 1 | 2;
	summarySchemaVersion?: number;
	id: string;
	source: 'papers';
	title: string;
	publishedAt: string;
	generatedAt?: string;
	summary: string;
	tags: readonly string[];
	downloadUrl?: string;
	scope?: ReportRecord;
	content: ReportRecord;
}

import generatedReports from '../generated-reports';

function isRecord(value: unknown): value is ReportRecord {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isPublicReport(value: unknown): value is PublicReport {
	return (
		isRecord(value) &&
		(value.schemaVersion === 1 || value.schemaVersion === 2) &&
		value.source === 'papers' &&
		typeof value.id === 'string' &&
		typeof value.title === 'string' &&
		typeof value.publishedAt === 'string' &&
		typeof value.summary === 'string' &&
		(value.downloadUrl === undefined || typeof value.downloadUrl === 'string') &&
		Array.isArray(value.tags) &&
		value.tags.every((tag) => typeof tag === 'string') &&
		isRecord(value.content)
	);
}

const reports = generatedReports.filter(isPublicReport);

export function getReports(): PublicReport[] {
	return [...reports].sort((left, right) => right.publishedAt.localeCompare(left.publishedAt));
}

export function getReport(id: string): PublicReport | undefined {
	return reports.find((report) => report.id === id);
}

export function reportUrl(report: Pick<PublicReport, 'id'>): string {
	return `/reports/${report.id}/`;
}

export function formatDate(value: string): string {
	return new Intl.DateTimeFormat('zh-CN', {
		year: 'numeric',
		month: 'long',
		day: 'numeric',
	}).format(new Date(value));
}

export function reportDisplayTitle(report: Pick<PublicReport, 'publishedAt'>): string {
	const date = new Date(report.publishedAt);
	if (Number.isNaN(date.valueOf())) return '文献报告';
	const parts = new Intl.DateTimeFormat('zh-CN', {
		year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'UTC',
	}).formatToParts(date);
	const value = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value;
	return `${value('year')}-${value('month')}-${value('day')} 文献周报`;
}

export function contentItems(content: ReportRecord, key: string): ReportRecord[] {
	const value = content[key];
	return Array.isArray(value) ? value.filter(isRecord) : [];
}

export function contentText(item: ReportRecord, key: string): string | undefined {
	const value = item[key];
	if (typeof value !== 'string') return undefined;
	const text = value.trim();
	return text && !['未提供', '暂无', '无'].includes(text) ? text : undefined;
}

export function contentTextList(item: ReportRecord, key: string): string[] {
	const value = item[key];
	return Array.isArray(value)
		? value.filter((entry): entry is string => (
			typeof entry === 'string' && Boolean(entry.trim()) &&
			!['未提供', '暂无', '无'].includes(entry.trim())
		))
		: [];
}

export function recordValue(value: unknown): ReportRecord {
	return isRecord(value) ? value : {};
}
