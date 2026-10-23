<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A unit, program or group card: a vertical kind label, the name with its status, tags, counts, a
     note and the source file. Adapted from the program card of Amp's mainframe migration post. -->
<script>
	import Handles from './Handles.svelte'
	import Overlays from './Overlays.svelte'
	import Rough from './Rough.svelte'
	import { css, hex } from '../../../lib/palette.js'
	import { STATUS, tagColor, ui } from '../state.svelte.js'

	let { id, data, selected = false } = $props()

	const status = $derived(STATUS[data.overlays?.status] || null)
	const accent = $derived(ui.overlays.status && status ? status.color
		: css(data.kind === 'external' || data.kind === 'group' ? 'ink-400' : 'ink-800'))
	const questioned = $derived(ui.overlays.questions && data.overlays?.questions?.length)
	const kindLabel = $derived({ unit: 'unit', program: 'program', external: 'other program', group: 'outside' }[data.kind])

	function dblclick(event) {
		if (data.drill) {
			event.stopPropagation()
			ui.drill?.(data.drill, id)
		}
	}
</script>

<Handles />
<div
	class="mf-card {data.kind}"
	class:selected
	class:questioned
	class:sketchy={ui.sketch}
	style:--accent={accent}
	ondblclick={dblclick}
	role="presentation"
>
	{#if ui.sketch}<Rough {id} width={data.w} height={data.h} stroke={hex(questioned ? 'accent-500' : 'ink-800')} />{/if}
	<div class="rail"><span>{kindLabel}</span></div>
	<div class="body">
		<div class="head">
			<div class="name" title={data.label}>{data.label}</div>
			{#if ui.overlays.status && status && data.kind !== 'external'}
				<span class="status" style:color={status.color} style:border-color={status.color}>{status.label}</span>
			{/if}
		</div>
		{#if data.sub}<div class="meta mono">{data.sub}</div>{/if}
		{#if data.tags?.length}
			<div class="tags">
				{#each data.tags as t (t.text)}
					<span class="tag" style:--tag={tagColor(t.tone)}>{t.text}</span>
				{/each}
			</div>
		{/if}
		{#if data.counts?.length}
			<div class="stats">
				{#each data.counts as c (c.label)}
					<span class="stat"><b>{c.n}</b><i>{c.label}</i></span>
				{/each}
			</div>
		{/if}
		{#if data.note}<div class="note">{data.note}</div>{/if}
		{#if data.file}<div class="foot mono">{data.file}</div>{/if}
	</div>
	{#if data.drill}<div class="drill" title="Double-click to open">⤢</div>{/if}
</div>
<Overlays overlays={data.overlays} />
