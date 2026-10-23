<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- The Backlog tab: every unit in migration.json by wave, its progress, and what mfmap check finds.
     #backlog/<unit ID> opens that unit. -->
<script>
	import { tick } from 'svelte'
	import { Callout, Empty, Inline, Page, Progress, report, route, Section, Segmented, SourceLink, STATUS } from '../lib/index.js'
	import Endpoint from './Endpoint.svelte'
	import UnitCard from './UnitCard.svelte'

	const plan = $derived(report.data?.plan)
	let status = $state('all')
	let search = $state('')
	let opened = $state(new Set())

	const matches = (u) => {
		const q = search.trim().toLowerCase()
		return (status === 'all' || u.status === status) &&
			(!q || [u.id, u.name, ...u.programs].some((x) => x.toLowerCase().includes(q)))
	}
	const waves = $derived.by(() => {
		const out = new Map()
		for (const u of plan?.units || []) if (matches(u)) out.set(u.wave, [...(out.get(u.wave) || []), u])
		return [...out].sort(([a], [b]) => a - b)
	})
	const active = $derived((plan?.units || []).flatMap((u) => (u.threads || []).filter((t) => !t.finished).map((t) => ({ u, t }))))

	function toggle(id) {
		const next = new Set(opened)
		next.has(id) ? next.delete(id) : next.add(id)
		opened = next
	}

	// #backlog/<id>: open that unit and bring it into view.
	$effect(() => {
		const id = route.tab === 'backlog' && route.path[0]
		if (!id || !plan) return
		if (!opened.has(id)) opened = new Set([...opened, id])
		tick().then(() => document.getElementById(`unit-${id}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' }))
	})
</script>

<Page title="Backlog" width="wide">
	{#snippet meta()}
		{#if plan}
			<div>{plan.units.length} units in <SourceLink path={plan.path} line={1} /></div>
			{#if plan.target}<div class="target">{plan.target}</div>{/if}
		{/if}
	{/snippet}
	{#if !report.data}
		<Empty>Loading…</Empty>
	{:else if !plan}
		<Empty title="No migration.json yet">The backlog appears here once <code class="mf-code">migration.json</code> has units.</Empty>
	{:else}
		{#if plan.errors.length}
			<Callout tone="danger" title="{plan.errors.length} problems (mfmap check)">
				<ul>{#each plan.errors.slice(0, 30) as e, i (i)}<li><Inline text={e} /></li>{/each}</ul>
			</Callout>
		{/if}
		{#if plan.units.length}
			<div class="progress"><Progress segments={['verified', 'built', 'building', 'todo'].map((s) => ({ label: STATUS[s].label.toLowerCase(), n: plan.progress[s], color: STATUS[s].color }))} /></div>
		{/if}
		{#if plan.warnings.length}
			<details class="warnings"><summary>{plan.warnings.length} warnings</summary><ul>{#each plan.warnings as w, i (i)}<li><Inline text={w} /></li>{/each}</ul></details>
		{/if}
		{#if active.length}
			<Section title="Active threads" count={active.length}>
				<ul class="threads">{#each active as { u, t } (t.url)}<li><a href={t.url} target="_blank" rel="noopener">{u.id} · {t.task}</a> <span class="muted">{u.name}</span></li>{/each}</ul>
			</Section>
		{/if}

		<div class="filters">
			<input class="mf-input" type="search" placeholder="Filter units and programs" bind:value={search} aria-label="Filter" />
			<Segmented label="Status" bind:value={status} options={[{ value: 'all', label: 'All' }, ...Object.entries(STATUS).map(([value, s]) => ({ value, label: s.label, count: plan.progress[value] }))]} />
		</div>
		{#each waves as [wave, units] (wave)}
			<Section title="Wave {wave}" count={units.length}>
				<div class="grid">
					{#each units as u (u.id)}<UnitCard unit={u} open={opened.has(u.id)} ontoggle={() => toggle(u.id)} />{/each}
				</div>
			</Section>
		{:else}
			{#if plan.units.length}<Empty>No unit matches.</Empty>{/if}
		{/each}
		{#if plan.excluded.length}
			<Section title="Not migrated" count={plan.excluded.length}>
				<ul class="excluded">{#each plan.excluded as e (e.program)}<li><Endpoint value={e.program} /> <Inline text={e.reason} /></li>{/each}</ul>
			</Section>
		{/if}
	{/if}
</Page>

<style>
	.progress { padding: 16px 18px; background: var(--mf-surface); border: 1px solid var(--mf-line); border-radius: var(--mf-radius); margin-bottom: 14px; }
	.warnings { margin: 0 0 6px; font-size: 13px; color: var(--mf-muted); }
	.warnings summary { cursor: pointer; color: var(--mf-warn); font-weight: 600; }
	.warnings ul { margin: 6px 0 0; padding-left: 20px; }
	.filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 26px 0 -8px; }
	.filters input { width: 260px; }
	.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 12px; align-items: start; }
	.threads, .excluded { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 6px; font-size: 13.5px; }
	.muted { color: var(--mf-muted); }
	.target { margin-top: 2px; max-width: 900px; }
	:global(.ui-callout) { margin-bottom: 14px; }
</style>
