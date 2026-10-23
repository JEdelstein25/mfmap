<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A scrolling tab: a title row with optional actions, a subtitle, and the content. width is narrow
     (reading) or wide (cards and tables). -->
<script>
	let { title, subtitle = undefined, width = 'narrow', meta = undefined, actions = undefined, children } = $props()
</script>

<div class="ui-page {width}">
	<header>
		<div class="titles">
			<h1>{title}</h1>
			{#if meta}<div class="sub">{@render meta()}</div>{:else if subtitle}<div class="sub">{subtitle}</div>{/if}
		</div>
		{#if actions}<div class="actions">{@render actions()}</div>{/if}
	</header>
	{@render children?.()}
</div>

<style>
	.ui-page { margin: 0 auto; padding: 32px 28px 96px; }
	.narrow { max-width: 900px; }
	.wide { max-width: 1240px; }
	header { display: flex; align-items: flex-end; gap: 16px; margin-bottom: 22px; }
	.titles { flex: 1; min-width: 0; }
	h1 { margin: 0; font-size: 24px; letter-spacing: -0.015em; }
	.sub { margin-top: 4px; color: var(--mf-muted); font-size: 13.5px; }
	.actions { display: flex; gap: 8px; align-items: center; }
</style>
