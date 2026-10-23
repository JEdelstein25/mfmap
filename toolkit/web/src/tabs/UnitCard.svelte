<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- One unit of migration.json: a summary card that opens to everything the plan and the unit's notes
     say about it. -->
<script>
	import { Badge, Button, Card, href, Inline, Markdown, SourceLink, STATUS } from '../lib/index.js'
	import Endpoint from './Endpoint.svelte'

	let { unit: u, open = false, ontoggle } = $props()
	const status = $derived(STATUS[u.status] || STATUS.todo)
	const deps = $derived([...new Set((u.dependencies || []).map((d) => d.unit))])
	const counts = $derived([
		[u.programs.length, 'programs'], [(u.entryPoints || []).length, 'ways in'],
		[(u.reads || []).length, 'reads'], [(u.writes || []).length, 'writes'],
		[(u.interfaces || []).length, 'interfaces'], [(u.acceptanceChecks || []).length, 'checks'],
	].filter(([n]) => n))
</script>

<Card accent={status.color} class="ui-unit {open ? 'open' : ''}" id="unit-{u.id}">
	<div class="summary">
		<button class="toggle" onclick={ontoggle} aria-expanded={open}>
			<div class="top">
				<span class="mono uid">{u.id}</span>
				<Badge tone={status.color}>{status.label}</Badge>
			</div>
			<div class="name">{u.name}</div>
			<div class="counts">{#each counts as [n, label] (label)}<span><b>{n}</b> {label}</span>{/each}</div>
			{#if deps.length}<div class="deps">After {#each deps as d, i (d)}{i ? ', ' : ''}<span class="mono">{d}</span>{/each}</div>{/if}
		</button>
		<div class="side">
			<Button size="sm" href={href('map', 'unit', u.id)} title="Open this unit on the map">Map</Button>
			<span class="chev" class:up={open}>▾</span>
		</div>
	</div>

	{#if open}
		<div class="detail">
			{#if u.threads?.length}
				<h4>Threads</h4>
				<ul class="plain">{#each u.threads as t (t.url)}<li><a href={t.url} target="_blank" rel="noopener">{t.task}</a>{#if t.finished} <Badge>finished</Badge>{/if}</li>{/each}</ul>
			{/if}
			{#each [['Programs', u.programs], ['Ways in', u.entryPoints], ['Reads', u.reads], ['Writes', u.writes]] as [label, list] (label)}
				{#if list?.length}<h4>{label}</h4><div class="chips">{#each list as e (e)}<Endpoint value={e} />{/each}</div>{/if}
			{/each}
			{#if u.dependencies?.length}
				<h4>Depends on</h4>
				<ul class="rows">
					{#each u.dependencies as d, i (i)}
						<li><div class="row-head"><a class="mono" href="#backlog/{encodeURIComponent(d.unit)}">{d.unit}</a> for <Endpoint value={d.on} /></div><div class="row-body"><Inline text={d.handling} /></div></li>
					{/each}
				</ul>
			{/if}
			{#if u.interfaces?.length}
				<h4>Interfaces</h4>
				<ul class="rows">
					{#each u.interfaces as x, i (i)}
						<li>
							<div class="row-head">
								<Badge>{x.direction}</Badge>
								<span class="iname">{x.name}</span>
								{#if x.with}<span class="muted">with <span class="mono">{x.with}</span></span>{/if}
							</div>
							<div class="row-body">
								{#if /^[a-z][a-z0-9-]*:\S+$/.test(x.layout)}<Endpoint value={x.layout} />{:else}<Inline text={x.layout} />{/if}
								{#if x.evidence} <span class="ev"><Inline text={x.evidence} /></span>{/if}
							</div>
						</li>
					{/each}
				</ul>
			{/if}
			{#if u.acceptanceChecks?.length}
				<h4>Acceptance checks</h4>
				<ol class="rows">
					{#each u.acceptanceChecks as c, i (i)}
						<li><div class="row-body"><Inline text={c.description} /></div>{#if c.data}<div class="data"><span>Data</span> <Inline text={c.data} /></div>{/if}</li>
					{/each}
				</ol>
			{/if}
			{#if u.notes}
				<h4>Notes <SourceLink path={u.notesPath} line={1} /></h4>
				<div class="notes"><Markdown text={u.notes} /></div>
			{:else}
				<p class="muted small">No <code class="mf-code">units/{u.id}.md</code> yet.</p>
			{/if}
		</div>
	{/if}
</Card>

<style>
	:global(.ui-unit) { overflow: hidden; scroll-margin-top: 80px; transition: box-shadow .15s; }
	:global(.ui-unit:hover) { box-shadow: var(--mf-shadow); }
	:global(.ui-unit.open) { grid-column: 1 / -1; }
	.summary { display: flex; align-items: flex-start; }
	.toggle { flex: 1; min-width: 0; text-align: left; border: 0; background: none; padding: 13px 4px 13px 15px; cursor: pointer; }
	.top { display: flex; align-items: center; gap: 8px; }
	.uid { font-size: 12px; color: var(--mf-faint); }
	.name { margin-top: 3px; font-size: 15px; font-weight: 650; line-height: 1.35; }
	.counts { display: flex; flex-wrap: wrap; gap: 2px 12px; margin-top: 7px; font-size: 12.5px; color: var(--mf-muted); }
	.counts b { color: var(--mf-fg); font-weight: 600; font-variant-numeric: tabular-nums; }
	.deps { margin-top: 5px; font-size: 12.5px; color: var(--mf-faint); }
	.deps .mono { color: var(--mf-muted); }
	.side { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; padding: 12px 14px 0 0; }
	.chev { color: var(--mf-faint); transition: transform .15s; }
	.chev.up { transform: rotate(180deg); }
	.detail { padding: 2px 18px 18px 15px; border-top: 1px solid var(--mf-line); }
	h4 { display: flex; align-items: baseline; gap: 10px; margin: 18px 0 8px; font-size: 11.5px; font-weight: 650; text-transform: uppercase; letter-spacing: .06em; color: var(--mf-muted); }
	h4 :global(.ui-source-link) { text-transform: none; letter-spacing: 0; font-weight: 400; }
	.chips { display: flex; flex-wrap: wrap; gap: 5px; }
	ul.plain { margin: 0; padding-left: 18px; font-size: 13.5px; }
	.rows { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; }
	ol.rows { list-style: decimal; padding-left: 22px; }
	.rows li { font-size: 13.5px; line-height: 1.5; }
	ul.rows li { padding: 9px 12px; background: var(--mf-surface-2); border: 1px solid var(--mf-line); border-radius: 7px; }
	.row-head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; margin-bottom: 4px; }
	.iname { font-weight: 550; }
	.row-body { color: var(--mf-ink-800); overflow-wrap: anywhere; }
	.ev { font-size: 12.5px; }
	.data { margin-top: 4px; font-size: 12.5px; color: var(--mf-muted); overflow-wrap: anywhere; }
	.data span { font-weight: 650; text-transform: uppercase; font-size: 10.5px; letter-spacing: .05em; color: var(--mf-faint); }
	.notes { padding: 12px 16px; border-radius: 8px; background: var(--mf-surface-2); border: 1px solid var(--mf-line); }
	.notes :global(.mf-prose) { font-size: 13.5px; }
	.muted { color: var(--mf-muted); }
	.small { font-size: 13px; margin: 16px 0 0; }
</style>
