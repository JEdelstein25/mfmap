<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A boxed message: tone is danger, warn, info or ok. -->
<script>
	let { tone = 'info', title = undefined, children } = $props()
	const colors = { danger: 'var(--mf-danger)', warn: 'var(--mf-warn)', info: 'var(--mf-accent)', ok: 'var(--mf-ok)' }
</script>

<div class="ui-callout" style:--tone={colors[tone] || tone}>
	{#if title}<div class="title">{title}</div>{/if}
	{@render children?.()}
</div>

<style>
	.ui-callout { padding: 11px 14px; border-radius: var(--mf-radius); border: 1px solid color-mix(in srgb, var(--tone) 30%, transparent); background: color-mix(in srgb, var(--tone) 6%, var(--mf-surface)); font-size: 13.5px; }
	.title { font-weight: 650; color: var(--tone); margin-bottom: 4px; }
	.ui-callout :global(ul) { margin: 4px 0 0; padding-left: 20px; }
</style>
