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
	import { css, hex } from '../../../lib/palette.js'
	import { kindCode, tagColor, ui } from '../state.svelte.js'

	let { id, data, selected = false } = $props()

	const tone = $derived(data.tags?.[0]?.tone || 'dataset')
	const shared = $derived(data.tags?.some((t) => t.tone === 'shared'))
	const questioned = $derived(ui.overlays.questions && data.overlays?.questions?.length)
</script>

<Handles />
<div class="mf-store" class:selected class:shared class:questioned class:sketchy={ui.sketch} style:--accent={css('ink-500')}>
	{#if ui.sketch}<Rough {id} width={data.w} height={data.h} radius={14} stroke={hex('ink-500')} />{/if}
	<div class="icon mf-kind">{kindCode(tone)}</div>
	<div class="body">
		<div class="head">
			<span class="name mono" title={data.label}>{data.label}</span>
			{#each data.tags.slice(1) as t (t.text)}
				<span class="tag" style:--tag={tagColor(t.tone)}>{t.text}</span>
			{/each}
		</div>
		{#if data.sub && data.sub !== data.label}<div class="meta mono" title={data.sub}>{data.sub}</div>{/if}
		{#if data.note}<div class="note">{data.note}</div>{/if}
	</div>
</div>
<Overlays overlays={data.overlays} />
