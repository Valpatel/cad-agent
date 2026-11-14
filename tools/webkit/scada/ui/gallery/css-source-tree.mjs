import {UI} from '../../paths.mjs';
/** Original CSS rule slices for the gallery's browser selector pass.
 * Chromium CSSRule.cssText can lose a var()-based shorthand after a longhand
 * override. Never use that serialization to write the image stylesheet.
 */
import {parse} from 'rrweb-cssom';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export function sourceTree(css) {
  function copy(rule) {
    if (!Number.isInteger(rule.__starts) || !Number.isInteger(rule.__ends)) {
      throw new Error(`CSS rule ${rule.type} has no source offsets`);
    }
    const result = {type: rule.type, source: css.slice(rule.__starts, rule.__ends)};
    if (rule.type === 1) {
      result.selector = rule.selectorText;
      // This parser's rule start omits a leading ':' selector. Its declaration
      // offset is reliable; preserve the parsed selector and original block.
      result.source = rule.selectorText + css.slice(rule.style.__starts, rule.__ends);
    }
    if (rule.type === 7) result.name = rule.name;
    if ([4, 12].includes(rule.type)) {
      if (!rule.cssRules.length) throw new Error('Empty CSS grouping rule');
      result.before = rule.type === 4 ? `@media ${rule.media.mediaText}{` : `@supports ${rule.conditionText}{`;
      result.after = '}';
      result.children = rule.cssRules.map(copy);
    } else if (![1, 7].includes(rule.type)) {
      throw new Error(`Unsupported CSS rule ${rule.type}; explicitly review gallery export support`);
    }
    return result;
  }
  return parse(css).cssRules.map(copy);
}

export function bundleCss(entry, packageRoot) {
  const root = fs.realpathSync(packageRoot), sources = new Map();
  function read(file, stack = new Set()) {
    const resolved = fs.realpathSync(file);
    if (!resolved.startsWith(root + path.sep)) throw new Error('CSS dependency escapes package');
    if (stack.has(resolved)) throw new Error('Circular CSS import');
    const css = fs.readFileSync(resolved, 'utf8'); sources.set(path.relative(root, resolved), css);
    const next = new Set([...stack, resolved]);
    // Parse imports, then retain all original declaration text including comments.
    // Import rules have no offsets in rrweb-cssom, so require the package's existing
    // explicit quoted import grammar and validate every removal against the parser.
    const imports = [...parse(css).cssRules].filter(rule => rule.type === 3).map(rule => rule.href);
    let index = 0;
    const expanded = css.replace(/@import\s+url\(['"]([^'"]+)['"]\);/g, (text, href) => {
      if (href !== imports[index++]) throw new Error('Unsupported CSS import syntax');
      if (/^(?:[a-z]+:|\/\/)/i.test(href)) throw new Error('External CSS dependency');
      return read(path.resolve(path.dirname(resolved), href), next);
    });
    if (index !== imports.length || /@import\b/.test(expanded)) throw new Error('Unexpanded CSS import');
    return expanded;
  }
  const css = read(entry);
  return {css, sourceTree: sourceTree(css), sources: Object.fromEntries(sources)};
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = UI;
  process.stdout.write(JSON.stringify(bundleCss(path.join(root, 'src/symbols/components.css'), root)));
}
