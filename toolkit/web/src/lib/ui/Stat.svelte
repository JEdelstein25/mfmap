<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- A number with a label under it. -->
<script>
	let { value, label, tone = 'var(--mf-fg)' } = $props()
</script>

<div class="ui-stat"><b style:color={tone}>{value}</b><span>{label}</span></div>

<style>
	.ui-stat { display: flex; flex-direction: column; min-width: 72px; }
	b { font-size: 22px; font-weight: 600; line-height: 1.15; font-variant-numeric: tabular-nums; }
	span { font-size: 12px; color: var(--mf-muted); }
</style>
