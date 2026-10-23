<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- The shell: the header with the project, the tabs from tabs.js and the run's status, the current
     tab, and the source viewer. A full-window tab (the Map) stays mounted once opened, so going back
     to it keeps its view. -->
<script>
	import { report } from './lib/report.svelte.js'
	import { route } from './lib/route.svelte.js'
	import SourceViewer from './lib/ui/SourceViewer.svelte'
	import { TABS } from './tabs.js'

	const current = $derived(TABS.find((t) => t.id === route.tab) || TABS[0])
	const project = $derived(report.data?.root?.split('/').filter(Boolean).pop() || '')
	const running = $derived(report.data?.run?.status === 'running')
	let visited = $state(new Set())
	$effect(() => {
		if (current.full && !visited.has(current.id)) visited = new Set([...visited, current.id])
	})
	$effect(() => {
		document.title = `${current.label} · mfmap${project ? ' · ' + project : ''}`
	})
</script>

<div class="mf-app" class:full={current.full}>
	<header class="mf-header">
		<a class="brand" href="#{TABS[0].id}" title={report.data?.root}>
			<span class="logo">mf</span><span class="name">mfmap</span>{#if project}<span class="project">{project}</span>{/if}
		</a>
		<nav>
			{#each TABS as t (t.id)}
				{@const n = report.data && t.badge?.(report.data)}
				<a href="#{t.id}" class:on={t === current} aria-current={t === current ? 'page' : undefined}>{t.label}{#if n}<span class="n">{n}</span>{/if}</a>
			{/each}
		</nav>
		<div class="status" class:running class:error={!!report.error}>
			{#if report.error}{report.error}
			{:else if running}Parsing
			{:else if report.updated}Updated {report.updated.toLocaleTimeString()}
			{:else}Loading{/if}
		</div>
	</header>

	<main>
		{#each TABS.filter((t) => t.full && visited.has(t.id)) as t (t.id)}
			<div class="full-tab" hidden={t !== current}><t.component /></div>
		{/each}
		{#if !current.full}
			{#key current.id}<div class="scroll"><current.component /></div>{/key}
		{/if}
	</main>
</div>

<SourceViewer />

<style>
	.mf-app { display: grid; grid-template-rows: var(--mf-header) 1fr; height: 100vh; }
	.mf-header { position: sticky; top: 0; z-index: 20; display: flex; align-items: center; gap: 28px; padding: 0 20px; background: color-mix(in srgb, var(--mf-surface) 92%, transparent); backdrop-filter: blur(8px); border-bottom: 1px solid var(--mf-line); }
	.brand { display: flex; align-items: center; gap: 8px; color: var(--mf-fg); font-weight: 700; }
	.brand:hover { text-decoration: none; }
	.logo { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 6px; background: var(--mf-fg); color: var(--mf-ink-0); font: 700 11px var(--mf-mono); letter-spacing: -.04em; }
	.name { font-size: 15px; letter-spacing: -.01em; }
	.project { padding-left: 9px; margin-left: 2px; border-left: 1px solid var(--mf-line-strong); color: var(--mf-muted); font-weight: 500; font-size: 13.5px; }
	nav { display: flex; gap: 2px; height: 100%; }
	nav a { position: relative; display: flex; align-items: center; gap: 6px; padding: 0 12px; color: var(--mf-muted); font-weight: 550; font-size: 13.5px; }
	nav a:hover { color: var(--mf-fg); text-decoration: none; }
	nav a.on { color: var(--mf-fg); }
	nav a.on::after { content: ''; position: absolute; left: 10px; right: 10px; bottom: -1px; height: 2px; border-radius: 2px; background: var(--mf-fg); }
	.n { min-width: 18px; padding: 0 6px; border-radius: 999px; background: var(--mf-sunken); color: var(--mf-muted); font-size: 11px; line-height: 18px; text-align: center; font-variant-numeric: tabular-nums; }
	nav a.on .n { background: var(--mf-fg); color: var(--mf-ink-0); }
	.status { margin-left: auto; display: flex; align-items: center; gap: 7px; font-size: 12px; color: var(--mf-faint); white-space: nowrap; }
	.status::before { content: ''; width: 7px; height: 7px; border-radius: 50%; background: var(--mf-ok); }
	.status.running::before { background: var(--mf-accent); animation: pulse 1.1s infinite; }
	.status.error { color: var(--mf-danger); }
	.status.error::before { background: var(--mf-danger); }
	main { min-height: 0; position: relative; }
	.scroll { height: 100%; overflow: auto; }
	.full-tab { height: 100%; }
	.full-tab[hidden] { display: none; }
	@keyframes pulse { 50% { opacity: .25; } }
</style>
