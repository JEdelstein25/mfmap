<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A surface with a border and a shadow. accent draws a coloured left edge; muted is for things that
     are done or out of the way. Extra attributes go to the element. -->
<script>
	let { accent = undefined, muted = false, children, class: cls = '', ...rest } = $props()
</script>

<div class="ui-card {cls}" class:accent={!!accent} class:muted style:--accent={accent} {...rest}>{@render children?.()}</div>

<style>
	.ui-card { background: var(--mf-surface); border: 1px solid var(--mf-line); border-radius: var(--mf-radius); box-shadow: var(--mf-shadow-sm); }
	.ui-card.accent { border-left: 3px solid var(--accent); }
	.ui-card.muted { background: var(--mf-surface-2); box-shadow: none; }
</style>
