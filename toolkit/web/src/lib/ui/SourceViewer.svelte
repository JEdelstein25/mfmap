<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- The source viewer: the lines around the line openSource() asked for, with that line marked.
     App draws it once; Escape or a click outside closes it. -->
<script>
	import { tick } from 'svelte'
	import { short } from '../report.svelte.js'
	import { closeSource, viewer } from '../source.svelte.js'

	let box = $state(null)
	$effect(() => {
		if (viewer.lines.length) tick().then(() => box?.querySelector('.hl')?.scrollIntoView({ block: 'center' }))
	})
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && closeSource()} />

{#if viewer.open}
	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
	<div class="ui-modal" onclick={(e) => e.target === e.currentTarget && closeSource()}>
		<div class="box" role="dialog" aria-modal="true" aria-label="Source">
			<div class="bar">
				<span class="mono path" title={viewer.path}>{short(viewer.path)}<b>:{viewer.line}</b></span>
				<button class="close" onclick={closeSource} title="Close (Esc)">×</button>
			</div>
			<div class="code" bind:this={box}>
				{#if viewer.error}<p class="error">{viewer.error}</p>
				{:else if !viewer.lines.length}<p class="muted">Loading…</p>
				{:else}
					<pre>{#each viewer.lines as text, i (i)}<span class:hl={viewer.start + i === viewer.line}><i>{viewer.start + i}</i>{text || ' '}</span>{/each}</pre>
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.ui-modal { position: fixed; inset: 0; z-index: 100; display: grid; place-items: center; background: color-mix(in srgb, var(--mf-ink-900) 38%, transparent); animation: fade .12s ease-out; }
	.box { width: min(960px, 94vw); max-height: 84vh; display: flex; flex-direction: column; background: var(--mf-surface); border-radius: var(--mf-radius-lg); box-shadow: var(--mf-shadow-lg); overflow: hidden; }
	.bar { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-bottom: 1px solid var(--mf-line); background: var(--mf-surface-2); }
	.path { flex: 1; min-width: 0; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.path b { color: var(--mf-accent); font-weight: 600; }
	.close { border: 0; background: none; font-size: 22px; line-height: 1; color: var(--mf-faint); cursor: pointer; }
	.close:hover { color: var(--mf-fg); }
	.code { overflow: auto; padding: 8px 0; }
	pre { margin: 0; font: 12.5px/1.6 var(--mf-mono); }
	pre span { display: block; padding: 0 16px; white-space: pre; }
	pre span.hl { background: var(--mf-accent-100); box-shadow: inset 3px 0 0 var(--mf-accent); }
	pre i { display: inline-block; width: 4.5em; color: var(--mf-faint); font-style: normal; user-select: none; }
	.error { color: var(--mf-danger); padding: 0 16px; }
	.muted { padding: 0 16px; }
	@keyframes fade { from { opacity: 0; } }
</style>
