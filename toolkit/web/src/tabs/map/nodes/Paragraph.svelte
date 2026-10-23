<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A paragraph in a program's control flow. Business-logic paragraphs are highlighted with the
     summary recorded for them. -->
<script>
	import Handles from './Handles.svelte'
	import Overlays from './Overlays.svelte'
	import Rough from './Rough.svelte'
	import { hex } from '../../../lib/palette.js'
	import { tagColor, ui } from '../state.svelte.js'

	let { id, data, selected = false } = $props()

	const questioned = $derived(ui.overlays.questions && data.overlays?.questions?.length)
</script>

<Handles />
<div class="mf-para" class:logic={data.highlight} class:selected class:questioned class:sketchy={ui.sketch}>
	{#if ui.sketch}<Rough {id} width={data.w} height={data.h} stroke={hex(data.highlight ? 'accent-500' : 'ink-800')}
			fill={data.highlight ? hex('accent-200') : 'none'} />{/if}
	<div class="head">
		<span class="name mono" title={data.label}>{data.label}</span>
		{#each data.tags.filter((t) => t.tone !== 'logic') as t (t.text)}
			<span class="tag" style:--tag={tagColor(t.tone)}>{t.text}</span>
		{/each}
	</div>
	{#if data.highlight}
		<div class="logic-tag">BUSINESS LOGIC</div>
		<div class="note" title={data.note}>{data.note}</div>
	{:else if data.counts?.length}
		<div class="stats">
			{#each data.counts as c (c.label)}<span class="stat"><b>{c.n}</b><i>{c.label}</i></span>{/each}
		</div>
	{/if}
</div>
<Overlays overlays={data.overlays} />
