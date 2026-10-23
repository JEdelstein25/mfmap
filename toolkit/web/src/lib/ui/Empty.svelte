<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- What a tab or section shows when it has nothing yet. -->
<script>
	let { title = undefined, children } = $props()
</script>

<div class="ui-empty">
	{#if title}<div class="title">{title}</div>{/if}
	<div class="body">{@render children?.()}</div>
</div>

<style>
	.ui-empty { padding: 36px 20px; text-align: center; border: 1px dashed var(--mf-line-strong); border-radius: var(--mf-radius-lg); color: var(--mf-muted); }
	.title { font-weight: 650; color: var(--mf-fg); margin-bottom: 4px; }
</style>
