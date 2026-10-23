<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A bar split into segments, [{ label, n, color }], with a legend. -->
<script>
	let { segments } = $props()
	const total = $derived(segments.reduce((s, x) => s + x.n, 0) || 1)
</script>

<div class="ui-progress">
	<div class="bar">
		{#each segments as s (s.label)}{#if s.n}<i style:width="{(100 * s.n) / total}%" style:background={s.color} title="{s.n} {s.label}"></i>{/if}{/each}
	</div>
	<div class="legend">
		{#each segments as s (s.label)}<span><i style:background={s.color}></i>{s.n} {s.label}</span>{/each}
	</div>
</div>

<style>
	.bar { display: flex; height: 8px; border-radius: 999px; overflow: hidden; background: var(--mf-sunken); }
	.bar i + i { border-left: 2px solid var(--mf-surface); }
	.legend { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 8px; font-size: 12.5px; color: var(--mf-muted); }
	.legend span { display: inline-flex; align-items: center; gap: 6px; }
	.legend i { width: 8px; height: 8px; border-radius: 50%; }
</style>
