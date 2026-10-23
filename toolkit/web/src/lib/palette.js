// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// The palette is defined once, in lib/tokens.css. Code names a colour by its token, such as
// 'ink-600' or 'accent-500': css(token) is for style attributes, and hex(token) is the resolved value
// for SVG that cannot use CSS variables (the sketch style).

export const css = (token) => `var(--mf-${token})`

const resolved = new Map()
export function hex(token) {
	if (!resolved.has(token)) {
		resolved.set(token, getComputedStyle(document.documentElement).getPropertyValue(`--mf-${token}`).trim() || '#000')
	}
	return resolved.get(token)
}
