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
	import { Background, BackgroundVariant, Controls, MiniMap, SvelteFlow } from '@xyflow/svelte'
	import { onDestroy, tick } from 'svelte'

	import FocusZoom from './FocusZoom.svelte'
	import LabeledEdge from './LabeledEdge.svelte'
	import Sidebar from './Sidebar.svelte'
	import { layout } from './layout.js'
	import Band from './nodes/Band.svelte'
	import Card from './nodes/Card.svelte'
	import DataStore from './nodes/DataStore.svelte'
	import Entry from './nodes/Entry.svelte'
	import Paragraph from './nodes/Paragraph.svelte'
	import { STATUS, ui } from './state.svelte.js'

	let { openSource = () => {} } = $props()

	const nodeTypes = { card: Card, data: DataStore, entry: Entry, paragraph: Paragraph, band: Band }
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

	function parseRoute() {
		const [, level = 'estate', ...rest] = location.hash.replace(/^#/, '').split('/')
		const id = rest.length ? decodeURIComponent(rest.join('/')) : null
		return ['unit', 'program'].includes(level) && id ? { level, id } : { level: 'estate', id: null }
	}
	let route = $state(parseRoute())
	const key = (r) => `${r.level}/${r.id || ''}`
	let shownKey = null

	function href(level, id) {
		return level === 'estate' ? '#map' : `#map/${level}/${encodeURIComponent(id)}`
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
			const g = await res.json()
			const laid = layout(g)
			// Keep positions the reader dragged nodes to, when the same node is still on the level.
			if (!fresh) {
				const moved = new Map(nodes.filter((n) => n.data?.moved).map((n) => [n.id, n.position]))
				for (const n of laid.nodes) if (moved.has(n.id)) n.position = moved.get(n.id)
			}
			graph = g
			nodes = laid.nodes
			edges = applyEdges(laid.edges)
			error = null
			updated = new Date()
			if (!fresh) {
				flash = true
				setTimeout(() => (flash = false), 900)
			}
			shownKey = key(want)
			if (fresh) {
				if (ui.selected && !laid.nodes.concat(laid.edges).some((x) => x.id === ui.selected.id)) ui.selected = null
				await tick()
				await flow?.fitView({ duration: 0, padding: 0.08, maxZoom: 1.1 })
				// A large program fits only at a zoom where nothing is legible: start at its entry
				// instead, with the minimap for the rest.
				const start = laid.nodes.find((n) => n.id === `program:${g.id}`)
				if (g.level === 'program' && start && flow && flow.getViewport().zoom < 0.45) {
					const width = document.querySelector('.mfmap-map .mf-canvas')?.clientWidth || 1200
					const zoom = 0.6
					flow.setCenter(start.position.x - 40 + width / zoom / 2, start.position.y + start.height / 2, { zoom, duration: 450 })
				}
			}
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
		if (key(next) === key(route)) return
		route = next
		ui.selected = null
		ui.hover = null
		load()
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
	ui.openSource = (path, line) => openSource(path, line || 1)

	const selectedItem = $derived.by(() => {
		if (!ui.selected || !graph) return null
		const list = ui.selected.type === 'edge' ? graph.edges : graph.nodes
		return list.find((x) => x.id === ui.selected.id) || null
	})
	const labelOf = (id) => graph?.nodes.find((n) => n.id === id)?.label || id

	function nodeclick({ node }) {
		if (node.type === 'band') return
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
		if (here) {
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
	const statusCounts = $derived.by(() => {
		const c = {}
		for (const n of graph?.nodes || []) if (n.kind === 'unit') c[n.overlays.status] = (c[n.overlays.status] || 0) + 1
		return c
	})
	const legend = $derived(
		graph?.level === 'program'
			? [['control', 'PERFORM / GO TO / CALL'], ['read', 'READ'], ['write', 'WRITE'], ['rw', 'READ/WRITE']]
			: graph?.level === 'unit'
				? [['control', 'START / RUN / CALL'], ['screen', 'SEND / RECEIVE'], ['read', 'READ'], ['write', 'WRITE'], ['rw', 'READ/WRITE']]
				: [['read', 'READ'], ['write', 'WRITE'], ['rw', 'READ/WRITE'], ['depends', 'NEEDS (unit dependency)']],
	)
	const toneColor = { control: '#475569', read: '#2563eb', write: '#dc2626', rw: '#c2410c', screen: '#0891b2', depends: '#7c3aed' }
</script>

<div class="mfmap-map" class:sketch={ui.sketch} class:with-panel={!!selectedItem}>
	<div class="mf-toolbar">
		<div class="where">
			<div class="crumbs">
				{#each graph?.crumbs || [{ level: 'estate', label: 'Estate' }] as c, i (i)}
					{#if i}<span class="sep">›</span>{/if}
					<a href={href(c.level, c.id)} class:on={i === (graph?.crumbs.length || 1) - 1}>{c.label}</a>
				{/each}
			</div>
			{#if graph}<div class="subtitle">{graph.subtitle}</div>{/if}
		</div>
		<form class="search" onsubmit={jump}>
			<input bind:value={search} list="mf-index" placeholder="Jump to unit or program" aria-label="Jump to unit or program" />
			<datalist id="mf-index">
				{#each graph?.index.units || [] as [id, name] (id)}<option value={id}>{name}</option>{/each}
				{#each graph?.index.programs || [] as p (p)}<option value={p}></option>{/each}
			</datalist>
		</form>
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
			fitView
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
			onnodepointerenter={({ node }) => node.type !== 'band' && (ui.hover = node.id)}
			onnodepointerleave={() => (ui.hover = null)}
			onnodedragstop={({ targetNode }) => targetNode && (targetNode.data.moved = true)}
		>
			<FocusZoom onready={(f) => (flow = f)} />
			<Background variant={BackgroundVariant.Dots} gap={18} size={1.4} bgColor={ui.sketch ? '#fdfcf7' : '#f6f5f0'} patternColor="#c9c6bb" />
			<Controls showLock={false} />
			{#if nodes.length > 40}
				<MiniMap pannable zoomable nodeColor={(n) => (n.type === 'band' ? 'transparent' : n.data?.highlight ? '#f59e0b' : '#a8a29e')} />
			{/if}
		</SvelteFlow>

		<div class="mf-legend">
			{#each legend as [tone, text] (tone)}
				<span><i style:background={toneColor[tone]} class:dashed={tone === 'depends'}></i>{text}</span>
			{/each}
			{#if graph?.level === 'program'}<span><i class="logic"></i>business logic</span>{/if}
			{#if graph?.level === 'estate' && ui.overlays.status}
				{#each Object.entries(statusCounts) as [s, n] (s)}
					<span><i style:background={STATUS[s]?.color || '#78716c'}></i>{n} {s}</span>
				{/each}
			{/if}
		</div>
		<div class="mf-meta" class:flash>
			{#if error}<b>{error}</b>{:else if graph}
				{graph.nodes.length} of {graph.totals.entities} entities · {graph.edges.length} edges for
				{graph.edges.reduce((s, e) => s + e.count, 0)} of {graph.totals.relationships} relationships
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
