<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A band behind the nodes: a wave or the shared data on the estate level, a column on the unit
     level. Tinted in turn, as the tiers of Amp's architecture map. -->
<script>
	import Rough from './Rough.svelte'
	import { hex } from '../../../lib/palette.js'
	import { ui } from '../state.svelte.js'

	let { id, data } = $props()

</script>

<div class="mf-band" class:vertical={data.vertical} class:sketchy={ui.sketch}>
	{#if ui.sketch}<Rough {id} width={data.w || 10} height={data.h || 10} stroke={hex('ink-400')} />{/if}
	<div class="label">
		<span>{data.label}</span>
		{#if data.sub}<small>{data.sub}</small>{/if}
	</div>
</div>
