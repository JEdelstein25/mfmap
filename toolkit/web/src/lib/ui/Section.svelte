<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A titled part of a page, with an optional count and actions on the right. -->
<script>
	let { title, count = undefined, id = undefined, actions = undefined, children } = $props()
</script>

<section class="ui-section" {id}>
	<div class="head">
		<h2>{title}{#if count !== undefined}<span class="count">{count}</span>{/if}</h2>
		{#if actions}<div class="actions">{@render actions()}</div>{/if}
	</div>
	{@render children?.()}
</section>

<style>
	.ui-section { margin: 30px 0 0; }
	.head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
	h2 { flex: 1; margin: 0; font-size: 13px; font-weight: 650; text-transform: uppercase; letter-spacing: .06em; color: var(--mf-muted); }
	.count { margin-left: 8px; font-weight: 500; color: var(--mf-faint); }
	.actions { display: flex; gap: 8px; align-items: center; }
</style>
