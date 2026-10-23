// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// The source viewer every tab shares: openSource(path, line) shows the lines around `line` of a file
// the store knows (from /api/source) in <SourceViewer>, which App draws once.

export const viewer = $state({ open: false, path: null, line: 1, start: 1, lines: [], error: null })

export async function openSource(path, line = 1) {
	if (!path) return
	Object.assign(viewer, { open: true, path, line: Number(line) || 1, lines: [], error: null })
	try {
		const res = await fetch(`api/source?path=${encodeURIComponent(path)}&line=${Number(line) || 1}`)
		if (!res.ok) throw new Error(`mfmap serve cannot show ${path}`)
		const s = await res.json()
		if (viewer.path === path) Object.assign(viewer, { start: s.start, lines: s.lines })
	} catch (e) {
		viewer.error = e.message
	}
}

export function closeSource() {
	viewer.open = false
}

// Opens the source for a click on a .mf-src element that Markdown or Inline rendered.
export function onSourceClick(event) {
	const el = event.target.closest?.('.mf-src')
	if (!el) return
	event.preventDefault()
	openSource(el.dataset.path, el.dataset.line)
}

export function onSourceKey(event) {
	if (event.key === 'Enter' && event.target.classList?.contains('mf-src')) onSourceClick(event)
}
