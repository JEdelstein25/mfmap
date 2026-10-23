<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A box around the nodes of one unit, wave or status when the estate is grouped. It only frames
     them; the edges are the same as without it. Double-click a unit's box to open the unit. -->
<script>
	import Rough from './Rough.svelte'
	import { ui } from '../state.svelte.js'

	let { id, data } = $props()

	const hues = ['47 111 237', '15 157 122', '217 119 6', '139 92 246', '225 29 72', '6 182 212', '101 163 13', '100 116 139']
	const hue = $derived(hues[data.index % hues.length])
</script>

<div class="mf-group" class:sketchy={ui.sketch} style:--hue={hue}
	ondblclick={() => data.drill && ui.drill?.(data.drill, null)} role="presentation">
	{#if ui.sketch}<Rough {id} width={data.w} height={data.h} radius={10} stroke="rgb({hue})" />{/if}
	<div class="label" title={data.drill ? 'Double-click to open the unit' : ''}>
		<span>{data.label}</span>
		{#if data.grouping === 'unit'}<small>unit {data.id}</small>{/if}
	</div>
</div>
