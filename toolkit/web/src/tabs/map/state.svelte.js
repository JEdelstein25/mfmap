// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// State the canvas, its nodes, edges and the side panel share.
import { css } from '../../lib/palette.js'

export const ui = $state({
	// { type: 'node' | 'edge', id }
	selected: null,
	// Node ID under the pointer: edges that do not touch it fade.
	hover: null,
	sketch: false,
	overlays: { status: true, errors: true, unresolved: true, questions: true },
	fallsThrough: false,
	// Estate: edges shown around the focused node; current zoom, which hides edge labels when small.
	hops: 1,
	showLeaves: false,
	zoom: 1,
	// Set by App: drill(drill, nodeId), select(type, id), focus(nodeId), openSource(path, line).
	drill: null,
	select: null,
	focus: null,
	openSource: null,
})

// Edge colours by tone, as palette tokens (lib/tokens.css): control flow in ink, data access in the
// accent (lighter for reads), unit dependencies faint.
export const TONES = {
	read: 'accent-400',
	write: 'accent-700',
	rw: 'accent-500',
	control: 'ink-600',
	flow: 'ink-400',
	depends: 'ink-400',
	screen: 'ink-600',
}

// A unit's status in migration.json (see the schema), as palette tokens.
export const STATUS = {
	todo: { label: 'TODO', color: css('status-todo') },
	building: { label: 'BUILDING', color: css('status-building') },
	built: { label: 'BUILT', color: css('status-built') },
	verified: { label: 'VERIFIED', color: css('status-verified') },
}

// Tags are all ink: what a tag says tells kinds apart, not its colour. Business logic is the one
// tag in the accent.
export function tagColor(tone) {
	return css(tone === 'logic' ? 'accent-500' : 'ink-600')
}

// The short label a node shows in place of an icon, by kind or first tag.
const CODES = {
	program: 'PGM', external: 'PGM', dynamic: '?', transaction: 'TX', job: 'JOB', proc: 'PROC', api: 'API',
	page: 'WEB', screen: 'BMS', vsam: 'VSAM', db2: 'DB2', ims: 'IMS', imsdb: 'IMS', mq: 'MQ', queue: 'QUEUE',
	dataset: 'DSN', sequential: 'FILE', files: 'FILE', gsam: 'GSAM', zosasset: 'ZOS', tstd: 'TSQ',
}
export function kindCode(tone) {
	return CODES[tone] || String(tone || '').slice(0, 4).toUpperCase()
}

// A stable small integer for an ID, so the sketch style draws the same wobble on every refresh.
export function seed(id) {
	let h = 0
	for (const c of String(id)) h = (h * 31 + c.charCodeAt(0)) | 0
	return (Math.abs(h) % 100000) + 1
}
