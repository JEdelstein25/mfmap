// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// Positions for one level of the map from /api/graph. The server decides what to draw; this only
// places it:
//
// - graph (estate): the resolved graph left to right, optionally boxed by unit, wave or status.
// - columns (unit): a column per role (ways in, callers, programs, called, data), ordered so edges
//   cross as little as possible.
// - flow (program): paragraphs left to right with dagre, following PERFORM, GO TO and calls.
//   Fall-through edges shape the layout only for paragraphs nothing else reaches; otherwise every
//   program would be one long chain of paragraphs in source order.
import dagre from '@dagrejs/dagre'

const SIZE = {
	unit: [300, 186],
	program: [290, 150],
	external: [250, 112],
	group: [330, 120],
	data: [250, 98],
	entry: [210, 64],
	screen: [210, 64],
	paragraph: [236, 70],
	logic: [262, 118],
}

export function size(n) {
	if (n.kind === 'paragraph' && n.highlight) return SIZE.logic
	return SIZE[n.kind] || SIZE.entry
}

const center = (n) => ({ x: n.position.x + n.width / 2, y: n.position.y + n.height / 2 })

function flowNode(n, x, y) {
	const [w, h] = size(n)
	return { id: n.id, type: n.kind === 'paragraph' ? 'paragraph' : ['data'].includes(n.kind) ? 'data'
		: ['entry', 'screen'].includes(n.kind) ? 'entry' : 'card', position: { x, y }, width: w, height: h,
		data: { ...n, w, h }, draggable: true, zIndex: 1 }
}

function bandNode(b, x, y, width, height, index, vertical) {
	return { id: `band:${b.id}`, type: 'band', position: { x, y }, width, height, zIndex: -1,
		selectable: false, draggable: false, focusable: false,
		data: { ...b, index, vertical, w: width, h: height } }
}

// Handles on the sides that face each other, so edges leave and enter cards cleanly.
function attach(edges, byId, vertical) {
	return edges.map((e) => {
		const s = byId.get(e.source), t = byId.get(e.target)
		let sourceHandle = 's-right', targetHandle = 't-left'
		if (s && t) {
			const a = center(s), b = center(t)
			const dx = b.x - a.x, dy = b.y - a.y
			if (Math.abs(dy) > Math.abs(dx) * (vertical ? 0.35 : 1.2)) {
				;[sourceHandle, targetHandle] = dy > 0 ? ['s-bottom', 't-top'] : ['s-top', 't-bottom']
			} else {
				;[sourceHandle, targetHandle] = dx >= 0 ? ['s-right', 't-left'] : ['s-left', 't-right']
			}
		}
		return { id: e.id, source: e.source, target: e.target, sourceHandle, targetHandle, type: 'labeled',
			data: e, zIndex: 0 }
	})
}

// Barycentre ordering: each node moves towards the average position of its neighbours.
function order(groups, edges, rounds = 6) {
	const pos = new Map()
	const index = () => groups.forEach((g) => g.forEach((n, i) => pos.set(n.id, i / Math.max(1, g.length - 1))))
	const neighbours = new Map()
	for (const e of edges) {
		if (!neighbours.has(e.source)) neighbours.set(e.source, [])
		if (!neighbours.has(e.target)) neighbours.set(e.target, [])
		neighbours.get(e.source).push(e.target)
		neighbours.get(e.target).push(e.source)
	}
	index()
	for (let r = 0; r < rounds; r++) {
		for (const g of groups) {
			const score = new Map(g.map((n) => {
				const ns = (neighbours.get(n.id) || []).filter((x) => pos.has(x) && !g.some((m) => m.id === x))
				return [n.id, ns.length ? ns.reduce((s, x) => s + pos.get(x), 0) / ns.length : pos.get(n.id)]
			}))
			g.sort((a, b) => score.get(a.id) - score.get(b.id))
		}
		index()
	}
}

// The estate: every node of the resolved graph as a chip, laid out left to right from the ways in
// through the programs to the data, with dagre. A grouping only adds boxes around the same nodes:
// the edges are the same with or without it.
const CHIP = { program: [220, 58], external: [196, 46], entry: [196, 46], screen: [196, 46], data: [220, 54],
	dynamic: [210, 42] }
const GROUP_PAD = 18, GROUP_HEAD = 30
const chipSize = (n) => { const [w, h] = CHIP[n.kind] || CHIP.entry; return [w, n.folded?.length ? h + 12 : h] }

function chip(n, x, y) {
	const [w, h] = chipSize(n)
	return { id: n.id, type: 'chip', position: { x, y }, width: w, height: h, data: { ...n, w, h }, draggable: true,
		zIndex: 1 }
}

// dagre, left to right: top-left positions by ID, and the size of the whole.
function arrange(items, links, nodesep) {
	const d = new dagre.graphlib.Graph()
	d.setGraph({ rankdir: 'LR', nodesep, ranksep: 140, edgesep: 6, marginx: 0, marginy: 0 })
	d.setDefaultEdgeLabel(() => ({}))
	for (const { id, w, h } of items) d.setNode(id, { width: w, height: h })
	const ids = new Set(items.map((i) => i.id))
	// One layout edge per pair, weighted by how many edges it stands for.
	for (const [s, t, weight] of links) {
		if (s === t || !ids.has(s) || !ids.has(t)) continue
		const [a, b] = d.hasEdge(t, s) ? [t, s] : [s, t]
		const was = d.edge(a, b)
		d.setEdge(a, b, { weight: (was?.weight || 0) + weight, minlen: 1 })
	}
	dagre.layout(d)
	const at = new Map()
	let width = 0, height = 0
	for (const { id, w, h } of items) {
		const p = d.node(id)
		at.set(id, { x: p.x - w / 2, y: p.y - h / 2 })
		width = Math.max(width, p.x + w / 2)
		height = Math.max(height, p.y + h / 2)
	}
	return { at, width, height }
}

function topology(g, { grouping = 'none' } = {}) {
	const groupOf = (n) => (grouping === 'none' ? null : n.groups?.[grouping] ?? null)
	const groups = [...new Set(g.nodes.map(groupOf).filter((v) => v != null))].sort((a, b) => String(a).localeCompare(String(b)))
	const sizeOf = new Map(g.nodes.map((n) => [n.id, chipSize(n)]))
	const links = g.edges.map((e) => [e.source, e.target, e.tone === 'control' ? 2 : 1, e.id])
	// Nodes with no edge and no group (often jobs that only run a utility) go in a grid under the
	// graph instead of stretching its first column.
	const linked = new Set(g.edges.flatMap((e) => [e.source, e.target]))
	const loose = g.nodes.filter((n) => !linked.has(n.id) && groupOf(n) == null)
	const looseIds = new Set(loose.map((n) => n.id))
	// Each group is laid out on its own and then placed as one block, so boxes never overlap; the
	// edges drawn are the same ones, between the same nodes.
	const inner = new Map(groups.map((v) => {
		const members = g.nodes.filter((n) => groupOf(n) === v)
		return [v, arrange(members.map((n) => ({ id: n.id, w: sizeOf.get(n.id)[0], h: sizeOf.get(n.id)[1] })), links, 14)]
	}))
	const blockOf = new Map(g.nodes.map((n) => [n.id, groupOf(n) != null ? `group:${groupOf(n)}` : n.id]))
	const items = [
		...groups.map((v) => ({ id: `group:${v}`, w: inner.get(v).width + GROUP_PAD * 2, h: inner.get(v).height + GROUP_HEAD + GROUP_PAD })),
		...g.nodes.filter((n) => groupOf(n) == null && !looseIds.has(n.id)).map((n) => ({ id: n.id, w: sizeOf.get(n.id)[0], h: sizeOf.get(n.id)[1] })),
	]
	const outer = arrange(items, links.map(([s, t, w, name]) => [blockOf.get(s), blockOf.get(t), w, name]), groups.length ? 40 : 12)
	const nodes = [], placed = new Map()
	groups.forEach((v, i) => {
		const box = outer.at.get(`group:${v}`)
		const width = inner.get(v).width + GROUP_PAD * 2, height = inner.get(v).height + GROUP_HEAD + GROUP_PAD
		const label = grouping === 'unit' ? g.groupLabels?.unit?.[v] || v : String(v)
		nodes.push({ id: `group:${v}`, type: 'groupbox', position: { ...box }, width, height, zIndex: -1, selectable: false,
			draggable: false, focusable: false,
			data: { id: v, label, index: i, grouping, w: width, h: height, drill: grouping === 'unit' ? { level: 'unit', id: v } : null } })
	})
	for (const n of g.nodes) {
		if (looseIds.has(n.id)) continue
		const v = groupOf(n)
		const p = v != null
			? { x: outer.at.get(`group:${v}`).x + GROUP_PAD + inner.get(v).at.get(n.id).x, y: outer.at.get(`group:${v}`).y + GROUP_HEAD + inner.get(v).at.get(n.id).y }
			: outer.at.get(n.id)
		const fn = chip(n, p.x, p.y)
		nodes.push(fn)
		placed.set(n.id, fn)
	}
	const columns = Math.max(4, Math.floor(Math.max(outer.width, 900) / 236))
	loose.sort((a, b) => a.kind.localeCompare(b.kind) || a.label.localeCompare(b.label)).forEach((n, i) => {
		const fn = chip(n, (i % columns) * 236, outer.height + 80 + Math.floor(i / columns) * 76)
		nodes.push(fn)
		placed.set(n.id, fn)
	})
	return { nodes, edges: attach(g.edges, placed, false) }
}

function columns(g) {
	const GAP_X = 170, GAP_Y = 26, PAD = 54, PER_COLUMN = 11
	const groups = g.bands.map((b) => g.nodes.filter((n) => n.band === b.id).sort((a, c) => a.label.localeCompare(c.label)))
	order(groups, g.edges)
	const nodes = [], placed = new Map()
	const heights = groups.map((members) => {
		const cols = Math.ceil(members.length / PER_COLUMN) || 1
		const per = Math.ceil(members.length / cols)
		let tallest = 0
		for (let c = 0; c < cols; c++) {
			const part = members.slice(c * per, (c + 1) * per)
			tallest = Math.max(tallest, part.reduce((s, n) => s + size(n)[1] + GAP_Y, -GAP_Y))
		}
		return tallest
	})
	const height = Math.max(...heights, 300) + PAD * 2
	let x = 0
	g.bands.forEach((b, i) => {
		const members = groups[i]
		const cols = Math.ceil(members.length / PER_COLUMN) || 1
		const per = Math.ceil(members.length / cols)
		const left = x
		let width = 0
		for (let c = 0; c < cols; c++) {
			const part = members.slice(c * per, (c + 1) * per)
			const w = Math.max(...part.map((n) => size(n)[0]))
			let y = PAD + (height - PAD * 2 - part.reduce((s, n) => s + size(n)[1] + GAP_Y, -GAP_Y)) / 2
			for (const n of part) {
				const fn = flowNode(n, x + 24 + (w - size(n)[0]) / 2, y)
				nodes.push(fn)
				placed.set(n.id, fn)
				y += size(n)[1] + GAP_Y
			}
			x += w + 30
			width += w + 30
		}
		nodes.unshift(bandNode(b, left, 0, width + 18, height, i, true))
		x += GAP_X
	})
	return { nodes, edges: attach(g.edges, placed, false) }
}

function flow(g) {
	const d = new dagre.graphlib.Graph({ multigraph: true })
	// Left to right: a main paragraph often performs twenty others, which stack better than they spread.
	d.setGraph({ rankdir: 'LR', nodesep: 22, ranksep: 110, edgesep: 12, marginx: 20, marginy: 20 })
	d.setDefaultEdgeLabel(() => ({}))
	for (const n of g.nodes) {
		const [w, h] = size(n)
		d.setNode(n.id, { width: w, height: h })
	}
	// A paragraph reached only by falling through (an EXIT paragraph after PERFORM ... THRU) hangs
	// under the paragraph before it instead of floating loose.
	const reached = new Set(g.edges.filter((e) => e.kind !== 'falls-through' && e.source !== e.target).map((e) => e.target))
	for (const e of g.edges) {
		if (e.source === e.target || (e.kind === 'falls-through' && reached.has(e.target))) continue
		d.setEdge(e.source, e.target, { weight: e.kind === 'access' ? 1 : 3, minlen: 1 }, e.id)
	}
	dagre.layout(d)
	const nodes = [], placed = new Map()
	for (const n of g.nodes) {
		const p = d.node(n.id)
		const [w, h] = size(n)
		const fn = flowNode(n, p.x - w / 2, p.y - h / 2)
		nodes.push(fn)
		placed.set(n.id, fn)
	}
	return { nodes, edges: attach(g.edges, placed, false).map((e) => ({ ...e, data: { ...e.data, step: true } })) }
}

export function layout(g, options = {}) {
	return { graph: topology, columns, flow }[g.layout](g, options)
}
