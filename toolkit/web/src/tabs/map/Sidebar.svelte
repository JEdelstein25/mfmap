<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- The side panel for the selected node or edge: what it is, its overlays and questions, and the
     file and line of every relationship it stands for, each opening the source viewer. Adapted from
     the program detail sidebar of Amp's mainframe migration post and the panel of Amp's architecture
     map. -->
<script>
	import { css } from '../../lib/palette.js'
	import { STATUS, TONES, tagColor, ui } from './state.svelte.js'

	let { item, type, graph, labelOf, onclose } = $props()

	const questions = $derived(
		(item.overlays?.questions || []).map((qid) => graph.questions.find((q) => q.id === qid) || { id: qid }),
	)
	const status = $derived(STATUS[item.overlays?.status])
	const short = (path) => (path && graph.root && path.startsWith(graph.root + '/') ? path.slice(graph.root.length + 1) : path)
	const kind = $derived(type === 'edge' ? `${item.kind} edge` : item.kind === 'external' ? 'program in another unit' : item.kind)
</script>

<aside class="mf-panel">
	<div class="mf-head">
		<div>
			<div class="kind">{kind}</div>
			{#if type === 'edge'}
				<h2>
					<span style:color={css(TONES[item.tone] || TONES.control)}>{item.label}</span>
					{#if item.count > 1}<small>×{item.count}</small>{/if}
				</h2>
				<div class="sub mono">{labelOf(item.source)} → {labelOf(item.target)}</div>
			{:else}
				<h2 class="mono">{item.label}</h2>
				{#if item.sub}<div class="sub">{item.sub}</div>{/if}
			{/if}
		</div>
		<button class="mf-close" onclick={onclose} title="Close">×</button>
	</div>

	{#if item.tags?.length || (status && type !== 'edge')}
		<div class="tags">
			{#if status && item.kind !== 'external'}<span class="tag" style:--tag={status.color}>{status.label}</span>{/if}
			{#each item.tags || [] as t (t.text)}<span class="tag" style:--tag={tagColor(t.tone)}>{t.text}</span>{/each}
		</div>
	{/if}
	{#if item.counts?.length}
		<div class="stats">
			{#each item.counts as c (c.label)}<span class="stat"><b>{c.n}</b><i>{c.label}</i></span>{/each}
		</div>
	{/if}
	{#if item.note}<p class="note">{item.note}</p>{/if}
	<div class="actions">
		{#if item.drill}
			<button class="drill" onclick={() => ui.drill?.(item.drill, item.id)}>
				Open {item.drill.level === 'unit' ? 'unit' : 'paragraphs'} ↘
			</button>
		{/if}
		{#if type === 'node' && graph.level === 'estate'}
			<button class="drill plain" onclick={() => ui.focus?.(item.id)}>Show its neighborhood</button>
		{/if}
		{#if type === 'node' && (item.groups?.unit || (item.unit && graph.level === 'program'))}
			<button class="drill plain" onclick={() => ui.drill?.({ level: 'unit', id: item.groups?.unit || item.unit }, null)}>
				Open unit {item.groups?.unit || item.unit}
			</button>
		{/if}
		{#if type === 'node' && (item.groups?.unit || item.unit)}
			<a class="drill plain" href="#backlog/{encodeURIComponent(item.groups?.unit || item.unit)}">In the backlog</a>
		{/if}
	</div>
	{#if item.items?.length}
		<h3>Programs</h3>
		<ul class="items">
			{#each item.items as x (x.label)}
				<li><button class="link mono" onclick={() => ui.drill?.(x.drill, null)}>{x.label}</button> <span>{x.note}</span></li>
			{/each}
		</ul>
	{/if}

	{#if item.folded?.length}
		<h3>Without source in the repository</h3>
		<ul class="evidence">
			{#each item.folded as f (f.id)}
				<li><button class="link" onclick={() => ui.openSource?.(f.evidence[0]?.path, f.evidence[0]?.line)}>
					<span class="mono">{f.how} {f.label}</span> {f.evidence[0] ? `${short(f.evidence[0].path)}:${f.evidence[0].line}` : ''}</button></li>
			{/each}
		</ul>
	{/if}
	{#if questions.length}
		<h3>Open questions</h3>
		{#each questions as q (q.id)}
			<div class="question">
				<div><span class="qid">{q.id}</span> {q.question || ''}</div>
				{#if q.default}<div class="default"><i>Default:</i> {q.default}</div>{/if}
			</div>
		{/each}
	{/if}
	{#if item.overlays?.errorEvidence?.length}
		<h3>Parse errors <small>{item.overlays.errors}</small></h3>
		<ul class="evidence">
			{#each item.overlays.errorEvidence as e, i (i)}
				<li><button class="link" onclick={() => ui.openSource?.(e.path, e.line)}><span class="mono">{short(e.path)}:{e.line}</span> {e.text}</button></li>
			{/each}
		</ul>
	{/if}
	{#if item.overlays?.unresolvedEvidence?.length}
		<h3>Unresolved <small>{item.overlays.unresolved}</small></h3>
		<ul class="evidence">
			{#each item.overlays.unresolvedEvidence as e, i (i)}
				<li><button class="link" onclick={() => ui.openSource?.(e.path, e.line)}><span class="mono">{short(e.path)}:{e.line}</span> {e.text}</button></li>
			{/each}
		</ul>
	{/if}
	{#if item.evidence?.length}
		<h3>Evidence{#if item.count > item.evidence.length}<small> first {item.evidence.length} of {item.count}</small>{/if}</h3>
		<ul class="evidence">
			{#each item.evidence as e, i (i)}
				<li>
					<button class="link" onclick={() => ui.openSource?.(e.path, e.line)}>
						<span class="mono">{short(e.path)}{e.line ? `:${e.line}` : ''}</span>
						{e.text}
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</aside>
