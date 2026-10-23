<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A button, or a link styled as one when href is set. variant: primary, secondary (the default) or
     ghost; size: sm or md. -->
<script>
	let { variant = 'secondary', size = 'md', href = undefined, children, ...rest } = $props()
</script>

{#if href}
	<a class="ui-button {variant} {size}" {href} {...rest}>{@render children?.()}</a>
{:else}
	<button class="ui-button {variant} {size}" type="button" {...rest}>{@render children?.()}</button>
{/if}

<style>
	.ui-button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; border: 1px solid var(--mf-line-strong); border-radius: 7px; background: var(--mf-surface); color: var(--mf-fg); font-weight: 550; cursor: pointer; text-decoration: none; white-space: nowrap; transition: background .12s, border-color .12s, box-shadow .12s; }
	.ui-button:hover { background: var(--mf-sunken); text-decoration: none; }
	.ui-button:disabled { opacity: .55; cursor: default; }
	.md { padding: 6px 13px; font-size: 13px; }
	.sm { padding: 3px 9px; font-size: 12px; border-radius: 6px; }
	.primary { background: var(--mf-fg); border-color: var(--mf-fg); color: var(--mf-ink-0); }
	.primary:hover { background: color-mix(in srgb, var(--mf-fg) 85%, white); }
	.ghost { border-color: transparent; background: none; color: var(--mf-accent); }
	.ghost:hover { background: var(--mf-accent-soft); }
</style>
