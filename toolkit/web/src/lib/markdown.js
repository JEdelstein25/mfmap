// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// The small Markdown the server and the agent write (headings, lists one level deep, code, bold,
// italics, links), as HTML. A file:line reference to a source becomes a .mf-src span with
// data-path and data-line, which <Markdown> and <Inline> open in the source viewer.

export const esc = (s) =>
	String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])

const SOURCE = /([\w./@-]+\.(?:cbl|cob|cpy|dcl|jcl|prc|proc|bms|ddl|csd|ctl|sql|dbd|psb|md|json)):(\d+)/gi

export function inline(text, root = '') {
	const code = []
	let s = esc(text).replace(/`([^`]+)`/g, (_, c) => `\u0000${code.push(c) - 1}\u0000`)
	s = s
		.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
		.replace(/(^|\W)_(.+?)_(?=\W|$)/g, '$1<em>$2</em>')
		.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
		.replace(SOURCE, (m, p, l) =>
			`<span class="mf-src" role="link" tabindex="0" data-path="${esc(p.startsWith('/') || !root ? p : root + '/' + p)}" data-line="${l}">${m}</span>`)
	return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${code[i]}</code>`)
}

export function markdown(md, root = '') {
	const out = []
	const lines = String(md ?? '').split('\n')
	const item = /^\s*([-*]|\d+\.) /
	for (let i = 0; i < lines.length; i++) {
		const line = lines[i]
		if (line.startsWith('```')) {
			const body = []
			while (++i < lines.length && !lines[i].startsWith('```')) body.push(lines[i])
			out.push(`<pre><code>${esc(body.join('\n'))}</code></pre>`)
		} else if (/^#{1,4} /.test(line)) {
			const n = line.match(/^#+/)[0].length
			out.push(`<h${n}>${inline(line.slice(n + 1), root)}</h${n}>`)
		} else if (item.test(line)) {
			// One level of nesting: items indented by two or more spaces belong to the item above.
			const ordered = /^\s*\d+\./.test(line)
			const items = []
			for (; i < lines.length && item.test(lines[i]); i++) {
				const text = lines[i].replace(item, '')
				if (/^\s{2,}/.test(lines[i]) && items.length) items[items.length - 1].children.push(text)
				else items.push({ text, children: [] })
			}
			i--
			const li = (x) => `<li>${inline(x.text, root)}${x.children.length ? `<ul>${x.children.map((c) => `<li>${inline(c, root)}</li>`).join('')}</ul>` : ''}</li>`
			out.push(`<${ordered ? 'ol' : 'ul'}>${items.map(li).join('')}</${ordered ? 'ol' : 'ul'}>`)
		} else if (line.trim()) {
			const para = [line]
			while (i + 1 < lines.length && lines[i + 1].trim() && !/^(#|```|\s*([-*]|\d+\.) )/.test(lines[i + 1])) para.push(lines[++i])
			out.push(`<p>${inline(para.join(' '), root)}</p>`)
		}
	}
	return out.join('\n')
}
