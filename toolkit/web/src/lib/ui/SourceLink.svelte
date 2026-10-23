<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A file and line that opens the source viewer, shown relative to the parse root. -->
<script>
	import { short } from '../report.svelte.js'
	import { openSource } from '../source.svelte.js'

	let { path, line = undefined, children = undefined } = $props()
</script>

<button type="button" class="ui-source-link" onclick={() => openSource(path, line || 1)} title="{path}{line ? ':' + line : ''}">
	{#if children}{@render children()}{:else}{short(path)}{line ? `:${line}` : ''}{/if}
</button>

<style>
	.ui-source-link { border: 0; background: none; padding: 0; font: 12.5px var(--mf-mono); color: var(--mf-accent); cursor: pointer; text-align: left; word-break: break-all; }
	.ui-source-link:hover { text-decoration: underline; }
</style>
