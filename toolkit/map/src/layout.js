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
// - bands (estate): a horizontal band per wave, as tiers in an architecture map, with the shared
//   data in a band below, ordered under the units that use it.
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

function bands(g) {
	// Waves left to right as columns, so dependencies read from later waves back to earlier ones; the
	// shared data runs along the bottom under the units that use it.
	const PAD = 30, TOP = 58, GAP_X = 110, GAP_Y = 34
	const nodes = [], placed = new Map()
	const columnsOf = g.bands.filter((b) => b.id !== 'shared')
	const waves = columnsOf.filter((b) => b.id !== 'outside').concat(columnsOf.filter((b) => b.id === 'outside'))
	const members = (b) => g.nodes.filter((n) => n.band === b.id)
	const stackHeight = (list) => list.reduce((s, n) => s + size(n)[1] + GAP_Y, -GAP_Y)
	const tallest = Math.max(...waves.map((b) => stackHeight(members(b))), 200)
	let x = 0
	waves.forEach((b, i) => {
		const list = members(b)
		const width = Math.max(...list.map((n) => size(n)[0]), 240) + PAD * 2
		let y = TOP + (tallest - stackHeight(list)) / 2
		for (const n of list) {
			const fn = flowNode(n, x + (width - size(n)[0]) / 2, y)
			nodes.push(fn)
			placed.set(n.id, fn)
			y += size(n)[1] + GAP_Y
		}
		nodes.unshift(bandNode(b, x, 0, width, tallest + TOP + PAD, g.bands.indexOf(b), true))
		x += width + GAP_X
	})
	const shared = g.bands.find((b) => b.id === 'shared')
	if (shared) {
		const list = members(shared)
		const want = (n) => {
			const users = g.edges.filter((e) => e.target === n.id).map((e) => placed.get(e.source)).filter(Boolean)
			return users.length ? users.reduce((s, u) => s + center(u).x, 0) / users.length : x / 2
		}
		const goals = list.map((n) => ({ n, x: want(n) - size(n)[0] / 2 })).sort((a, b) => a.x - b.x)
		// Each store under its users, pushed right where they would overlap, then the row recentred.
		let edge = -Infinity
		for (const s of goals) {
			s.x = Math.max(s.x, edge)
			edge = s.x + size(s.n)[0] + 36
		}
		const total = x - GAP_X
		const shift = goals.length ? Math.min(0, (total - edge + 36) / 2) : 0
		const top = tallest + TOP + PAD + 70
		for (const s of goals) {
			const fn = flowNode(s.n, s.x + shift, top + TOP)
			nodes.push(fn)
			placed.set(s.n.id, fn)
		}
		const h = Math.max(...list.map((n) => size(n)[1]), 60)
		const left = Math.min(0, ...goals.map((s) => s.x + shift)) - PAD
		const right = Math.max(total, ...goals.map((s) => s.x + shift + size(s.n)[0])) + PAD
		nodes.unshift(bandNode(shared, left, top, right - left, TOP + h + PAD, g.bands.indexOf(shared), false))
	}
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

export function layout(g) {
	return { bands, columns, flow }[g.layout](g)
}
