<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- The hand-drawn outline of a node in the sketch style, drawn with Rough.js. -->
<script>
	import rough from 'roughjs'
	import { seed } from '../state.svelte.js'

	let { id, width, height, stroke = '#1f2937', fill = 'none', radius = 0 } = $props()

	const generator = rough.generator()
	const paths = $derived.by(() => {
		const options = { seed: seed(id), roughness: 1.3, bowing: 1.2, stroke, strokeWidth: 1.4,
			fill: fill === 'none' ? undefined : fill, fillStyle: 'hachure', hachureGap: 7, fillWeight: 0.6 }
		const shape = radius
			? generator.path(`M${radius + 2},2 H${width - radius - 2} Q${width - 2},2 ${width - 2},${radius + 2} V${height - radius - 2} Q${width - 2},${height - 2} ${width - radius - 2},${height - 2} H${radius + 2} Q2,${height - 2} 2,${height - radius - 2} V${radius + 2} Q2,2 ${radius + 2},2 Z`, options)
			: generator.rectangle(2, 2, width - 4, height - 4, options)
		return generator.toPaths(shape)
	})
</script>

<svg class="mf-rough" {width} {height} aria-hidden="true">
	{#each paths as p, i (i)}
		<path d={p.d} stroke={p.stroke} stroke-width={p.strokeWidth} fill={p.fill || 'none'} />
	{/each}
</svg>
