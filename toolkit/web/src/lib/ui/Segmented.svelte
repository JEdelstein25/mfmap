<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A choice of a few options, [{ value, label, count? }], bound to value. -->
<script>
	let { options, value = $bindable(), label = undefined } = $props()
</script>

<div class="ui-segmented" role="radiogroup" aria-label={label}>
	{#each options as o (o.value)}
		<button type="button" role="radio" aria-checked={value === o.value} class:on={value === o.value} onclick={() => (value = o.value)}>
			{o.label}{#if o.count !== undefined}<span>{o.count}</span>{/if}
		</button>
	{/each}
</div>

<style>
	.ui-segmented { display: inline-flex; padding: 2px; gap: 2px; border-radius: 8px; background: var(--mf-sunken); }
	button { border: 0; background: none; padding: 4px 11px; border-radius: 6px; font-size: 12.5px; font-weight: 550; color: var(--mf-muted); cursor: pointer; }
	button:hover { color: var(--mf-fg); }
	button.on { background: var(--mf-surface); color: var(--mf-fg); box-shadow: var(--mf-shadow-sm); }
	span { margin-left: 6px; color: var(--mf-faint); font-weight: 500; font-variant-numeric: tabular-nums; }
</style>
