<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A short label: a status, a kind, a count. tone is any CSS colour or token; variant is soft
     (tinted, the default), solid or outline. -->
<script>
	let { tone = 'var(--mf-muted)', variant = 'soft', title = undefined, mono = false, children } = $props()
</script>

<span class="ui-badge {variant}" class:mono style:--tone={tone} {title}>{@render children?.()}</span>

<style>
	.ui-badge { display: inline-flex; align-items: center; gap: 4px; padding: 1px 7px; border-radius: 999px; font-size: 11.5px; font-weight: 600; line-height: 18px; white-space: nowrap; color: var(--tone); background: color-mix(in srgb, var(--tone) 12%, transparent); }
	.ui-badge.solid { color: var(--mf-ink-0); background: var(--tone); }
	.ui-badge.outline { background: none; box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--tone) 45%, transparent); }
	.ui-badge.mono { font: 600 11px/18px var(--mf-mono); }
</style>
