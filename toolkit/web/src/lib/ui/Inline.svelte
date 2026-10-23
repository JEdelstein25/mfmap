<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- One line of inline Markdown (code, bold, links, file:line references). -->
<script>
	import { inline } from '../markdown.js'
	import { report } from '../report.svelte.js'
	import { onSourceClick, onSourceKey } from '../source.svelte.js'

	let { text } = $props()
</script>

<!-- svelte-ignore a11y_no_static_element_interactions, a11y_click_events_have_key_events -->
<span class="ui-inline" onclick={onSourceClick} onkeydown={onSourceKey}>{@html inline(text, report.data?.root)}</span>

<style>
	.ui-inline :global(code) { font: 12.5px/1.5 var(--mf-mono); background: var(--mf-sunken); padding: 1px 5px; border-radius: var(--mf-radius-sm); }
</style>
