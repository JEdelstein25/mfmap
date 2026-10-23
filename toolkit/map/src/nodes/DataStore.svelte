<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A data store: a VSAM file, dataset, Db2 table, IMS database or queue. Adapted from the data-store
     node of Amp's mainframe migration post. -->
<script>
	import Handles from './Handles.svelte'
	import Overlays from './Overlays.svelte'
	import Rough from './Rough.svelte'
	import { tagColor, ui } from '../state.svelte.js'

	let { id, data, selected = false } = $props()

	const type = $derived(data.tags?.[0]?.text || 'DATA')
	const icon = $derived({ VSAM: '⬡', DB2: '⛁', IMS: '⛁', 'IMS DB': '⛁', MQ: '⇄', SEQUENTIAL: '▤', GSAM: '▤' }[type] || '▤')
	const color = $derived(tagColor(data.tags?.[0]?.tone))
	const shared = $derived(data.tags?.some((t) => t.tone === 'shared'))
	const questioned = $derived(ui.overlays.questions && data.overlays?.questions?.length)
</script>

<Handles />
<div class="mf-store" class:selected class:shared class:questioned class:sketchy={ui.sketch} style:--accent={color}>
	{#if ui.sketch}<Rough {id} width={data.w} height={data.h} radius={14} stroke={color} fill={shared ? '#fde68a' : 'none'} />{/if}
	<div class="icon">{icon}</div>
	<div class="body">
		<div class="head">
			<span class="name mono" title={data.label}>{data.label}</span>
			{#each data.tags as t (t.text)}
				<span class="tag" style:--tag={tagColor(t.tone)}>{t.text}</span>
			{/each}
		</div>
		{#if data.sub && data.sub !== data.label}<div class="meta mono" title={data.sub}>{data.sub}</div>{/if}
		{#if data.note}<div class="note">{data.note}</div>{/if}
	</div>
</div>
<Overlays overlays={data.overlays} />
