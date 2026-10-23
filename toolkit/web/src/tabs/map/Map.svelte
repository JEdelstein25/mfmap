<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- The Map tab: one level of the map at a time, from /api/graph, on a Svelte Flow canvas. The level is
     in the URL (#map, #map/unit/<id>, #map/program/<name>). The page polls with If-None-Match and
     redraws only when a parse, resolver, unit or question changed, keeping the viewport. Adapted from
     the embeddable graph of Amp's mainframe migration post. -->
<script>
	import '@xyflow/svelte/dist/style.css'
	import './style.css'
	import { Background, BackgroundVariant, Controls, MiniMap, SvelteFlow } from '@xyflow/svelte'
	import { onDestroy, tick } from 'svelte'

	import { css, hex } from '../../lib/palette.js'
	import { openSource } from '../../lib/source.svelte.js'

	import FocusZoom from './FocusZoom.svelte'
	import LabeledEdge from './LabeledEdge.svelte'
	import Sidebar from './Sidebar.svelte'
	import { layout } from './layout.js'
	import Band from './nodes/Band.svelte'
	import Card from './nodes/Card.svelte'
	import Chip from './nodes/Chip.svelte'
	import GroupBox from './nodes/GroupBox.svelte'
	import DataStore from './nodes/DataStore.svelte'
	import Entry from './nodes/Entry.svelte'
	import Paragraph from './nodes/Paragraph.svelte'
	import { TONES, ui } from './state.svelte.js'

	const nodeTypes = { card: Card, data: DataStore, entry: Entry, paragraph: Paragraph, band: Band, chip: Chip, groupbox: GroupBox }
	const edgeTypes = { labeled: LabeledEdge }

	let graph = $state.raw(null)
	let nodes = $state.raw([])
	let edges = $state.raw([])
	let error = $state(null)
	let updated = $state(null)
	let flash = $state(false)
	let search = $state('')
	let flow = null
	let etag = null
	let timer = null
	let loading = false
	let folded = $state(0)

	// #map[/unit/<id>|/program/<name>|/focus/<node id>][?group=unit|wave|status]
	function parseRoute() {
		const [path, query = ''] = location.hash.replace(/^#/, '').split('?')
		const [, level = 'estate', ...rest] = path.split('/')
		const id = rest.length ? decodeURIComponent(rest.join('/')) : null
		const group = new URLSearchParams(query).get('group') || 'none'
		if (['unit', 'program'].includes(level) && id) return { level, id, focus: null, group }
		return { level: 'estate', id: null, focus: level === 'focus' && id ? id : null, group }
	}
	let route = $state(parseRoute())
	// What is fetched, and what is shown: focus and grouping only change the drawing.
	const key = (r) => `${r.level}/${r.id || ''}`
	const viewKey = (r) => `${key(r)}/${r.focus || ''}/${r.group}/${ui.hops}`
	let shownKey = null
	let shownView = null

	function href(level, id) {
		return level === 'estate' ? estateHref(null, route.group) : `#map/${level}/${encodeURIComponent(id)}`
	}
	function estateHref(focus, group) {
		const query = group && group !== 'none' ? `?group=${group}` : ''
		return (focus ? `#map/focus/${encodeURIComponent(focus)}` : '#map') + query
	}
	const grouping = $derived(graph?.groupings?.includes(route.group) ? route.group : 'none')

	// The nodes within ui.hops edges of the focused node, and the edges between them.
	function neighborhood(g, id, hops) {
		const near = new Map()
		for (const e of g.edges) {
			if (!near.has(e.source)) near.set(e.source, [])
			if (!near.has(e.target)) near.set(e.target, [])
			near.get(e.source).push(e.target)
			near.get(e.target).push(e.source)
		}
		let keep = new Set([id]), ring = [id]
		for (let i = 0; i < hops; i++) {
			ring = ring.flatMap((x) => near.get(x) || []).filter((x) => !keep.has(x))
			ring.forEach((x) => keep.add(x))
		}
		return { ...g, nodes: g.nodes.filter((n) => keep.has(n.id)),
			edges: g.edges.filter((e) => keep.has(e.source) && keep.has(e.target)) }
	}

	// Programs with no source in the repository that call and touch nothing (IDCAMS, IEFBR14,
	// CEE3ABD...) are leaves that dozens of jobs share: drawn as nodes they pull unrelated jobs
	// together. Unless the reader shows them, they are folded into each caller, which lists them.
	function collapseLeaves(g) {
		const calls = new Set(g.edges.map((e) => e.source))
		const leaves = new Set(g.nodes.filter((n) => n.kind === 'external' && !calls.has(n.id)).map((n) => n.id))
		if (!leaves.size) return g
		const folded = new Map()
		for (const e of g.edges) {
			if (!leaves.has(e.target)) continue
			if (!folded.has(e.source)) folded.set(e.source, [])
			folded.get(e.source).push({ id: e.target, label: e.target.split(':').pop(), how: e.label, evidence: e.evidence })
		}
		return { ...g, nodes: g.nodes.filter((n) => !leaves.has(n.id)).map((n) => (folded.has(n.id) ? { ...n, folded: folded.get(n.id) } : n)),
			edges: g.edges.filter((e) => !leaves.has(e.target)), foldedCount: leaves.size }
	}

	async function relayout(fit) {
		if (!graph) return
		let shown = graph.level === 'estate' && route.focus ? neighborhood(graph, route.focus, ui.hops) : graph
		if (graph.level === 'estate' && !route.focus && !ui.showLeaves) shown = collapseLeaves(shown)
		folded = shown.foldedCount || 0
		let laid
		try {
			laid = layout(shown, { grouping })
		} catch (e) {
			error = `Cannot lay out this view: ${e.message}`
			return
		}
		if (!fit) {
			// Keep positions the reader dragged nodes to, when the same node is still shown.
			const moved = new Map(nodes.filter((n) => n.data?.moved).map((n) => [n.id, n.position]))
			for (const n of laid.nodes) if (moved.has(n.id)) n.position = moved.get(n.id)
		}
		nodes = laid.nodes
		edges = applyEdges(laid.edges)
		shownView = viewKey(route)
		if (!fit) return
		if (ui.selected && !laid.nodes.concat(laid.edges).some((x) => x.id === ui.selected.id)) ui.selected = null
		await tick()
		await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))
		const g = graph
		// A whole estate fits only at a zoom where nothing is legible: start legible at the top of
		// its first column of ways in (or its first group), with the minimap, search and focus for
		// the rest.
		const firsts = laid.nodes.filter((n) => (grouping === 'none' ? n.data?.kind === 'entry' : n.type === 'groupbox'))
		if (g.level === 'estate' && !route.focus && laid.nodes.length > 150 && firsts.length) {
			const left = Math.min(...firsts.map((n) => n.position.x))
			const top = Math.min(...firsts.filter((n) => n.position.x < left + 300).map((n) => n.position.y))
			await flow?.setViewport({ x: 40 - left * 0.75, y: 24 - top * 0.75, zoom: 0.75 })
		} else {
			await flow?.fitView({ duration: 0, padding: 0.08, maxZoom: 1.1 })
		}
		// A large program fits only at a zoom where nothing is legible: start at its entry
		// instead, with the minimap for the rest.
		const start = laid.nodes.find((n) => n.id === `program:${g.id}`)
		if (g.level === 'program' && start && flow && flow.getViewport().zoom < 0.45) {
			const width = document.querySelector('.mfmap-map .mf-canvas')?.clientWidth || 1200
			const zoom = 0.6
			flow.setCenter(start.position.x - 40 + width / zoom / 2, start.position.y + start.height / 2, { zoom, duration: 450 })
		}
		if (flow) ui.zoom = flow.getViewport().zoom
	}

	function applyEdges(list) {
		return list.map((e) => ({ ...e, hidden: e.data.kind === 'falls-through' && !ui.fallsThrough }))
	}

	async function load() {
		if (loading) return
		loading = true
		const want = { ...route }
		const fresh = key(want) !== shownKey
		try {
			const res = await fetch(`api/graph?level=${want.level}&id=${encodeURIComponent(want.id || '')}`,
				{ headers: !fresh && etag ? { 'If-None-Match': etag } : {} })
			if (key(want) !== key(route)) return
			if (res.status === 304) {
				error = null
				return
			}
			if (!res.ok) {
				error = (await res.json().catch(() => ({}))).error || `HTTP ${res.status}`
				graph = null
				nodes = []
				edges = []
				shownKey = key(want)
				return
			}
			etag = res.headers.get('ETag')
			graph = await res.json()
			error = null
			updated = new Date()
			if (!fresh) {
				flash = true
				setTimeout(() => (flash = false), 900)
			}
			shownKey = key(want)
			await relayout(fresh || shownView !== viewKey(route))
		} catch (e) {
			error = 'Disconnected; retrying'
		} finally {
			loading = false
		}
	}

	function poll() {
		clearTimeout(timer)
		const visible = location.hash.startsWith('#map') && !document.hidden
		if (visible) load()
		timer = setTimeout(poll, graph?.run?.status === 'running' ? 1500 : 3000)
	}
	poll()

	function onhash() {
		if (!location.hash.startsWith('#map')) return
		const next = parseRoute()
		if (viewKey(next) === viewKey(route)) return
		const refetch = key(next) !== key(route)
		route = next
		ui.hover = null
		if (refetch) {
			ui.selected = null
			load()
		} else relayout(true)
	}
	window.addEventListener('hashchange', onhash)
	onDestroy(() => {
		clearTimeout(timer)
		window.removeEventListener('hashchange', onhash)
	})

	// Double-click or "Open": zoom into the node, then show its level.
	ui.drill = async (drill, nodeId) => {
		if (!drill) return
		if (nodeId && flow) {
			flow.fitView({ nodes: [{ id: nodeId }], duration: 320, maxZoom: 2.2 })
			await new Promise((r) => setTimeout(r, 300))
		}
		location.hash = href(drill.level, drill.id)
	}
	ui.select = (type, id) => (ui.selected = { type, id })
	// Search only moves the view; the panel opens on a click.
	ui.focus = (id) => (location.hash = estateHref(id, route.group))
	ui.openSource = (path, line) => openSource(path, line || 1)

	const selectedItem = $derived.by(() => {
		if (!ui.selected || !graph) return null
		if (ui.selected.type === 'edge') return graph.edges.find((x) => x.id === ui.selected.id) || null
		// The drawn node first: on the estate it can carry the leaves folded into it.
		return nodes.find((n) => n.id === ui.selected.id)?.data || graph.nodes.find((x) => x.id === ui.selected.id) || null
	})
	const labelOf = (id) => graph?.nodes.find((n) => n.id === id)?.label || id

	function nodeclick({ node }) {
		if (node.type === 'band' || node.type === 'groupbox') return
		ui.selected = { type: 'node', id: node.id }
		// The panel takes the right of the canvas: bring a node it would cover into view.
		const canvas = document.querySelector('.mfmap-map .mf-canvas')?.getBoundingClientRect()
		const right = flow?.flowToScreenPosition({ x: node.position.x + node.width, y: node.position.y })
		if (canvas && right && right.x > canvas.right - 400) {
			const { zoom } = flow.getViewport()
			flow.setCenter(node.position.x + node.width / 2, node.position.y + node.height / 2, { zoom, duration: 300 })
		}
	}

	function jump(event) {
		event.preventDefault()
		const q = search.trim().toUpperCase()
		if (!q || !graph) return
		const here = graph.nodes.find((n) => n.label.toUpperCase() === q || n.id.toUpperCase().endsWith(':' + q))
		if (here && graph.level === 'estate') {
			ui.focus(here.id)
		} else if (here) {
			ui.selected = { type: 'node', id: here.id }
			flow?.fitView({ nodes: [{ id: here.id }], duration: 400, maxZoom: 1.3 })
		} else if (graph.index.programs.includes(q)) {
			location.hash = href('program', q)
		} else {
			const unit = graph.index.units.find(([id, name]) => id.toUpperCase() === q || name.toUpperCase() === q)
			if (unit) location.hash = href('unit', unit[0])
		}
		search = ''
	}

	function toggleFalls() {
		ui.fallsThrough = !ui.fallsThrough
		edges = applyEdges(edges)
	}

	const fallCount = $derived(graph?.edges.filter((e) => e.kind === 'falls-through').length || 0)
	const crumbs = $derived(route.focus && graph?.level === 'estate'
		? [{ level: 'estate', label: 'Estate' }, { focus: route.focus, label: `Around ${labelOf(route.focus)}` }]
		: graph?.crumbs || [{ level: 'estate', label: 'Estate' }])
	const shownCount = $derived(nodes.filter((n) => n.type !== 'groupbox').length)
	// [tone, label, dashed]
	const legend = $derived(
		graph?.level === 'program'
			? [['control', 'PERFORM / GO TO / CALL'], ['read', 'READ'], ['write', 'WRITE'], ['rw', 'READ/WRITE']]
			: graph?.level === 'unit'
				? [['control', 'START / RUN / CALL / SEND / RECEIVE'], ['read', 'READ'], ['write', 'WRITE'], ['rw', 'READ/WRITE']]
				: [['control', 'START / RUN / CALL / LINK / SEND'], ['control', 'XCTL', true], ['dashed', 'set at run time', true],
					['read', 'READ'], ['write', 'WRITE'], ['rw', 'READ/WRITE']],
	)
	const toneColor = { control: css(TONES.control), dashed: css('warn-500'), read: css(TONES.read), write: css(TONES.write),
		rw: css(TONES.rw), screen: css(TONES.screen), depends: css(TONES.depends) }
</script>

<div class="mfmap-map" class:sketch={ui.sketch} class:with-panel={!!selectedItem}>
	<div class="mf-toolbar">
		<div class="where">
			<div class="crumbs">
				{#each crumbs as c, i (i)}
					{#if i}<span class="sep">›</span>{/if}
					<a href={c.focus ? estateHref(c.focus, route.group) : href(c.level, c.id)} class:on={i === crumbs.length - 1}>{c.label}</a>
				{/each}
			</div>
			{#if graph}<div class="subtitle">{graph.subtitle}</div>{/if}
		</div>
		<form class="search" onsubmit={jump}>
			<input bind:value={search} list="mf-index" placeholder={graph?.level === 'estate' ? 'Focus on a program, job, file…' : 'Jump to unit or program'}
				aria-label="Search" />
			<datalist id="mf-index">
				{#each graph?.index.units || [] as [id, name] (id)}<option value={id}>{name}</option>{/each}
				{#if graph?.level === 'estate'}
					{#each graph.nodes.filter((n) => !graph.index.programs.includes(n.label)) as n (n.id)}<option value={n.label}>{n.sub}</option>{/each}
				{/if}
				{#each graph?.index.programs || [] as p (p)}<option value={p}></option>{/each}
			</datalist>
		</form>
		{#if graph?.level === 'estate'}
			<div class="toggles">
				<label title="Boxes around the nodes of each unit, wave or status in migration.json. The edges stay the same.">Group
					<select value={grouping} onchange={(e) => (location.hash = estateHref(route.focus, e.currentTarget.value))}>
						{#each graph.groupings as g (g)}<option value={g}>{g}</option>{/each}
					</select></label>
				{#if !route.focus}
					<label title="Programs with no source in the repository that call and touch nothing, such as IDCAMS: folded into the jobs and programs that run or call them">
						<input type="checkbox" bind:checked={ui.showLeaves} onchange={() => relayout(false)} /> Programs without source
						<small>{folded ? `${folded} folded` : ''}</small></label>
				{/if}
				{#if route.focus}
					<label title="How many edges away from the focused node to show">Hops
						<select bind:value={ui.hops} onchange={() => relayout(true)}>
							{#each [1, 2, 3] as h (h)}<option value={h}>{h}</option>{/each}
						</select></label>
					<a class="clear" href={estateHref(null, route.group)}>Show everything</a>
				{/if}
			</div>
		{/if}
		<div class="toggles">
			<label title="Colour units and programs by their status in migration.json"><input type="checkbox" bind:checked={ui.overlays.status} /> Status</label>
			<label title="Parse errors"><input type="checkbox" bind:checked={ui.overlays.errors} /> Errors <small>{graph?.overlays.errors ?? ''}</small></label>
			<label title="Calls and queries the resolvers could not resolve"><input type="checkbox" bind:checked={ui.overlays.unresolved} /> Unresolved <small>{graph?.overlays.unresolved ?? ''}</small></label>
			<label title="Open questions that name an entity"><input type="checkbox" bind:checked={ui.overlays.questions} /> Questions <small>{graph?.overlays.questions ?? ''}</small></label>
			{#if graph?.level === 'program'}
				<label title="Paragraphs that fall through into the next one"><input type="checkbox" checked={ui.fallsThrough} onchange={toggleFalls} /> Fall-through <small>{fallCount}</small></label>
			{/if}
			<span class="split"></span>
			<label class="style" title="Hand-drawn style"><input type="checkbox" bind:checked={ui.sketch} /> Sketch</label>
		</div>
	</div>

	<div class="mf-canvas">
		<SvelteFlow
			bind:nodes
			bind:edges
			{nodeTypes}
			{edgeTypes}
			minZoom={0.08}
			maxZoom={2.5}
			zoomOnDoubleClick={false}
			elevateEdgesOnSelect={false}
			nodesConnectable={false}
			elementsSelectable={true}
			proOptions={{ hideAttribution: true }}
			onnodeclick={nodeclick}
			onedgeclick={({ edge }) => (ui.selected = { type: 'edge', id: edge.id })}
			onpaneclick={() => (ui.selected = null)}
			onnodepointerenter={({ node }) => !['band', 'groupbox'].includes(node.type) && (ui.hover = node.id)}
			onnodepointerleave={() => (ui.hover = null)}
			onnodedragstop={({ targetNode }) => targetNode && (targetNode.data.moved = true)}
			onmove={(_, viewport) => (ui.zoom = viewport.zoom)}
		>
			<FocusZoom onready={(f) => (flow = f)} />
			<Background variant={BackgroundVariant.Dots} gap={18} size={1.4} bgColor={css('ink-50')} patternColor={css('ink-300')} />
			<Controls showLock={false} />
			{#if nodes.length > 40}
				<MiniMap pannable zoomable nodeColor={(n) => (n.type === 'band' ? 'transparent' : n.data?.highlight ? hex('accent-500') : hex('ink-300'))} />
			{/if}
		</SvelteFlow>

		<div class="mf-legend">
			{#each legend as [tone, text, dashed] (text)}
				<span><i style:background={dashed ? `repeating-linear-gradient(90deg, ${toneColor[tone]} 0 5px, transparent 5px 8px)` : toneColor[tone]}></i>{text}</span>
			{/each}
			{#if graph?.level === 'program'}<span><i class="logic"></i>business logic</span>{/if}
		</div>
		<div class="mf-meta" class:flash>
			{#if error}<b>{error}</b>{:else if graph}
				{shownCount} nodes of {graph.totals.entities} entities · {edges.length} edges for
				{edges.reduce((s, e) => s + (e.data?.count || 0), 0)} of {graph.totals.relationships} relationships
				{#if graph.run?.status === 'running'} · parsing…{/if}
				{#if updated} · updated {updated.toLocaleTimeString()}{/if}
			{:else}Loading map…{/if}
		</div>
		{#if !graph && error}
			<div class="mf-empty">{error}. <a href="#map">Back to the estate</a></div>
		{/if}
	</div>

	{#if selectedItem}
		<Sidebar item={selectedItem} type={ui.selected.type} {graph} {labelOf} onclose={() => (ui.selected = null)} />
	{/if}
</div>
