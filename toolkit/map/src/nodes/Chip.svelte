<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A node on the estate: a program, a program with no source in the repository, a way in, a screen,
     a data store or a call whose target is set at run time. Small, so a whole estate fits; the
     side panel has the rest. -->
<script>
	import Handles from './Handles.svelte'
	import Overlays from './Overlays.svelte'
	import Rough from './Rough.svelte'
	import { STATUS, tagColor, ui } from '../state.svelte.js'

	let { id, data, selected = false } = $props()

	const tone = $derived(data.kind === 'program' ? 'program' : data.kind === 'external' ? 'external'
		: data.kind === 'dynamic' ? 'dynamic' : data.tags?.[0]?.tone || 'entry')
	const color = $derived({ program: '#1f2937', external: '#78716c', dynamic: '#ea580c' }[tone] || tagColor(tone))
	const icon = $derived({ program: '▦', external: '▢', dynamic: '?', transaction: '⚡', job: '⏱', proc: '⏱', api: '⇄',
		page: '⌂', screen: '▣', vsam: '⬡', db2: '⛁', ims: '⛁', imsdb: '⛁', mq: '⇄', queue: '☰', dataset: '▤',
		sequential: '▤', gsam: '▤', zosasset: '⇄' }[tone] || '•')
	const sub = $derived(data.kind === 'program' ? data.tags.map((t) => t.text).slice(0, 4).join(' · ') || data.sub
		: data.kind === 'data' ? data.tags.map((t) => t.text).join(' · ') : data.note && data.kind === 'external' ? data.note : data.sub)
	// Long dataset names differ at the end: keep the end.
	const name = $derived(data.label.length > 23 ? '…' + data.label.slice(-22) : data.label)
	const foldedText = $derived(data.folded?.length ? `${data.folded[0].how.toLowerCase()} ${data.folded.map((f) => f.label).join(', ')}` : '')
	const status = $derived(ui.overlays.status ? STATUS[data.overlays?.status] : null)
	const questioned = $derived(ui.overlays.questions && data.overlays?.questions?.length)

	function dblclick(event) {
		if (data.drill) {
			event.stopPropagation()
			ui.drill?.(data.drill, id)
		}
	}
</script>

<Handles />
<div class="mf-chip {data.kind}" class:selected class:questioned class:sketchy={ui.sketch} style:--accent={status?.color || color}
	style:--tone={color} ondblclick={dblclick} role="presentation" title={data.label}>
	{#if ui.sketch}<Rough {id} width={data.w} height={data.h} radius={data.kind === 'program' ? 0 : 12} stroke={color} />{/if}
	<span class="icon">{icon}</span>
	<div class="body">
		<div class="name mono">{name}</div>
		{#if sub}<div class="meta">{sub}</div>{/if}
		{#if foldedText}<div class="meta folded" title={foldedText}>{foldedText}</div>{/if}
	</div>
	{#if status && data.kind === 'program'}<span class="status" style:background={status.color} title={status.label}></span>{/if}
</div>
<Overlays overlays={data.overlays} />
