<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- Gives App the canvas's viewport functions, which only work inside <SvelteFlow>. Adapted from the
     focus zoom of Amp's mainframe migration post. -->
<script>
	import { useSvelteFlow } from '@xyflow/svelte'
	import { onMount } from 'svelte'

	let { onready } = $props()
	const flow = useSvelteFlow()
	onMount(() => onready(flow))
</script>
