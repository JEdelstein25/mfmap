// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// State the canvas, its nodes, edges and the side panel share.
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

// Colours for edge tones and tags, shared by nodes, edges and the panel.
export const TONES = {
	read: '#2563eb',
	write: '#dc2626',
	rw: '#c2410c',
	control: '#475569',
	flow: '#94a3b8',
	depends: '#7c3aed',
	screen: '#0891b2',
}

// A unit's status in migration.json (see the schema).
export const STATUS = {
	todo: { label: 'TODO', color: '#78716c' },
	building: { label: 'BUILDING', color: '#2563eb' },
	built: { label: 'BUILT', color: '#0d9488' },
	verified: { label: 'VERIFIED', color: '#16a34a' },
}

const TAG_COLORS = {
	online: '#2563eb', batch: '#b45309', service: '#7c3aed', vsam: '#ca8a04', files: '#0891b2',
	sequential: '#0891b2', dataset: '#64748b', db2: '#16a34a', ims: '#be185d', imsdb: '#be185d',
	mq: '#9333ea', tstd: '#0d9488', shared: '#dc2626', logic: '#d97706', unit: '#4f46e5',
	transaction: '#2563eb', job: '#b45309', proc: '#b45309', api: '#7c3aed', screen: '#0891b2',
	queue: '#0d9488', gsam: '#be185d',
}

export function tagColor(tone) {
	return TAG_COLORS[tone] || '#64748b'
}

// A stable small integer for an ID, so the sketch style draws the same wobble on every refresh.
export function seed(id) {
	let h = 0
	for (const c of String(id)) h = (h * 31 + c.charCodeAt(0)) | 0
	return (Math.abs(h) % 100000) + 1
}
