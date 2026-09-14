#!/usr/bin/env node
/**
 * Render PapersCrawler Markdown into self-contained static KaTeX HTML.
 *
 * Usage:
 *   node render-markdown-katex.mjs INPUT.md OUTPUT.html
 *   node render-markdown-katex.mjs --validate < text-with-formulas
 */

import { cpSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import katex from "katex";
import { marked } from "marked";

const INLINE_OR_DISPLAY_MATH = /\\\(([\s\S]*?)\\\)|\\\[([\s\S]*?)\\\]/g;

/**
 * @typedef {{
 *   formula: string,
 *   display_mode: boolean,
 *   offset: number,
 *   message: string,
 * }} FormulaError
 */

/**
 * @typedef {{token: string, formula: string, displayMode: boolean}} FormulaToken
 */

/**
 * Find formulas that KaTeX cannot parse.
 *
 * @param {string} markdown Markdown containing formulas.
 * @returns {FormulaError[]} Validation errors with source offsets.
 */
function findFormulaErrors(markdown) {
  /** @type {FormulaError[]} */
  const errors = [];
  /** @type {RegExpExecArray | null} */
  let match;
  INLINE_OR_DISPLAY_MATH.lastIndex = 0;
  while ((match = INLINE_OR_DISPLAY_MATH.exec(markdown)) !== null) {
    const displayMode = match[2] !== undefined;
    const formula = displayMode ? match[2] : match[1];
    try {
      katex.renderToString(formula, { displayMode, throwOnError: true, strict: "warn" });
    } catch (error) {
      errors.push({
        formula,
        display_mode: displayMode,
        offset: match.index,
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }
  return errors;
}

/**
 * Render Markdown after replacing protected formulas with static KaTeX HTML.
 *
 * @param {string} markdown Source Markdown.
 * @returns {string} Rendered HTML fragment.
 */
function renderMarkdown(markdown) {
  /** @type {FormulaToken[]} */
  const formulas = [];
  const protectedMarkdown = markdown.replace(
    INLINE_OR_DISPLAY_MATH,
    (_whole, inlineFormula, displayFormula) => {
      const displayMode = displayFormula !== undefined;
      const formula = displayMode ? displayFormula : inlineFormula;
      const token = `@@PAPERSCRAWLER_FORMULA_${formulas.length}@@`;
      formulas.push({ token, formula, displayMode });
      return token;
    },
  );
  let html = /** @type {string} */ (
    marked.parse(protectedMarkdown, { async: false, breaks: true, gfm: true })
  );
  for (const { token, formula, displayMode } of formulas) {
    const rendered = katex.renderToString(formula, {
      displayMode,
      throwOnError: true,
      strict: "warn",
    });
    html = html.split(token).join(rendered);
  }
  return html;
}

/**
 * Wrap a rendered report fragment in a standalone printable document.
 *
 * @param {string} content Rendered report HTML.
 * @returns {string} Complete HTML document.
 */
function staticDocument(content) {
  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="katex-assets/katex.min.css">
<style>
@page { margin: 18mm; }
body { color: #1e293b; font-family: sans-serif; font-size: 11pt; line-height: 1.7; }
h1 { font-size: 20pt; } h2 { font-size: 16pt; border-bottom: 1px solid #e2e8f0; }
h3 { font-size: 13pt; } pre, code { background: #f1f5f9; } pre { padding: 0.75em; }
table { border-collapse: collapse; } th, td { border: 1px solid #cbd5e1; padding: 0.35em; }
.katex-display { overflow: visible; }
</style></head><body>${content}</body></html>`;
}

if (process.argv[2] === "--validate") {
  const input = readFileSync(0, "utf8");
  process.stdout.write(`${JSON.stringify({ valid: findFormulaErrors(input).length === 0, errors: findFormulaErrors(input) })}\n`);
} else {
  const [inputPath, outputPath] = process.argv.slice(2);
  if (!inputPath || !outputPath) {
    console.error("Usage: node render-markdown-katex.mjs INPUT.md OUTPUT.html");
    process.exit(64);
  }
  const markdown = readFileSync(inputPath, "utf8");
  const errors = findFormulaErrors(markdown);
  if (errors.length) {
    console.error(JSON.stringify({ valid: false, errors }));
    process.exit(2);
  }
  const outputDir = dirname(outputPath);
  mkdirSync(outputDir, { recursive: true });
  cpSync(join(dirname(new URL(import.meta.url).pathname), "../node_modules/katex/dist"),
    join(outputDir, "katex-assets"), { recursive: true });
  writeFileSync(outputPath, staticDocument(renderMarkdown(markdown)), "utf8");
}
