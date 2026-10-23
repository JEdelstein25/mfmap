<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A source and a target handle on each side; the layout picks the pair that face each other. -->
<script>
	import { Handle, Position } from '@xyflow/svelte'

	const sides = [
		['top', Position.Top],
		['right', Position.Right],
		['bottom', Position.Bottom],
		['left', Position.Left],
	]
</script>

{#each sides as [name, position] (name)}
	<Handle type="target" {position} id={`t-${name}`} isConnectable={false} class="mf-handle" />
	<Handle type="source" {position} id={`s-${name}`} isConnectable={false} class="mf-handle" />
{/each}
