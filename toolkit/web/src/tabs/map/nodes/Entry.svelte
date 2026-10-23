<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A way in (transaction, job, API, queue) or a screen. -->
<script>
	import Handles from './Handles.svelte'
	import Overlays from './Overlays.svelte'
	import Rough from './Rough.svelte'
	import { hex } from '../../../lib/palette.js'
	import { kindCode, ui } from '../state.svelte.js'

	let { id, data, selected = false } = $props()

	const tone = $derived(data.tags?.[0]?.tone || 'entry')
	const questioned = $derived(ui.overlays.questions && data.overlays?.questions?.length)
</script>

<Handles />
<div class="mf-entry" class:selected class:questioned class:sketchy={ui.sketch}>
	{#if ui.sketch}<Rough {id} width={data.w} height={data.h} radius={30} stroke={hex('ink-500')} />{/if}
	<span class="icon mf-kind">{kindCode(tone)}</span>
	<div class="body">
		<div class="name mono" title={data.label}>{data.label}</div>
		<div class="meta">{data.sub}</div>
	</div>
</div>
<Overlays overlays={data.overlays} />
