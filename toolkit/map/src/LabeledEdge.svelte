<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- An edge with a short label (READ, WRITE, PERFORM, XCTL, NEEDS ...) and a count when it stands
     for several statements. Clicking the edge or its label opens it in the side panel. Adapted from
     the labeled edge of Amp's mainframe migration post. -->
<script>
	import { BaseEdge, EdgeLabel, getBezierPath, getSmoothStepPath } from '@xyflow/svelte'
	import rough from 'roughjs'
	import { TONES, seed, ui } from './state.svelte.js'

	let { id, source, target, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, selected = false } = $props()

	const path = $derived(
		data?.step
			? getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 10 })
			: getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition }),
	)
	const color = $derived(TONES[data?.tone] || TONES.control)
	const touched = $derived(!ui.hover || ui.hover === source || ui.hover === target)
	const active = $derived(selected || (ui.hover && touched) ||
		(ui.selected?.type === 'node' && (ui.selected.id === source || ui.selected.id === target)))
	const width = $derived(Math.min(1.3 + Math.log2(data?.count || 1) * 0.6, 4) + (active ? 1 : 0))
	const dash = $derived(data?.dashed ? '6 5' : '')
	const generator = rough.generator()
	const sketch = $derived(ui.sketch ? generator.toPaths(generator.path(path[0], {
		seed: seed(id), roughness: 1.1, bowing: 0.8, stroke: color, strokeWidth: width,
	})) : [])
	const text = $derived(`${data?.label || ''}${data?.count > 1 ? ` ×${data.count}` : ''}`)

	function pick(event) {
		event.stopPropagation()
		ui.select?.('edge', id)
	}
</script>

{#if ui.sketch}
	<g class="mf-edge sketch {data?.tone}" class:dim={!touched} class:active>
		{#each sketch as p, i (i)}
			<path d={p.d} stroke={color} stroke-width={width} fill="none" stroke-dasharray={dash} />
		{/each}
		<path d={path[0]} class="hit" />
	</g>
{:else}
	<BaseEdge
		{id}
		path={path[0]}
		interactionWidth={14}
		class="mf-edge {data?.tone} {touched ? '' : 'dim'} {active ? 'active' : ''}"
		style="stroke: {color}; stroke-width: {width};{dash ? ` stroke-dasharray: ${dash};` : ''}"
	/>
{/if}
{#if text && (data?.tone !== 'depends' || active) && (active || ui.zoom >= 0.55)}
	<EdgeLabel x={path[1]} y={path[2]}>
		<button
			class="mf-edge-label nodrag nopan"
			class:dim={!touched}
			class:active
			class:control={['control', 'flow'].includes(data?.tone)}
			style:--edge={color}
			onclick={pick}>{text}</button
		>
	</EdgeLabel>
{/if}
