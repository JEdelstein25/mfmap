<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- Labelled values, [[label, text]], as a two-column list. Empty values are left out; text is inline
     Markdown. -->
<script>
	import Inline from './Inline.svelte'

	let { rows } = $props()
</script>

<dl class="ui-facts">
	{#each rows.filter(([, v]) => v) as [label, text] (label)}<dt>{label}</dt><dd><Inline {text} /></dd>{/each}
</dl>

<style>
	.ui-facts { display: grid; grid-template-columns: 6.5em 1fr; gap: 5px 14px; margin: 0; font-size: 13.5px; }
	dt { color: var(--mf-faint); }
	dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
</style>
