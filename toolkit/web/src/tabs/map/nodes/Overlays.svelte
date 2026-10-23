<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- Overlay badges on a node: parse errors, unresolved calls and open questions. The unit status is
     drawn by the card itself. -->
<script>
	import { ui } from '../state.svelte.js'

	let { overlays } = $props()
</script>

{#if overlays}
	<div class="mf-badges">
		{#if ui.overlays.errors && overlays.errors}
			<span class="mf-badge mf-err" title="{overlays.errors} parse errors">{overlays.errors} {overlays.errors > 1 ? "errors" : "error"}</span>
		{/if}
		{#if ui.overlays.unresolved && overlays.unresolved}
			<span class="mf-badge mf-unres" title="{overlays.unresolved} unresolved calls">{overlays.unresolved} unresolved</span>
		{/if}
		{#if ui.overlays.questions && overlays.questions?.length}
			<span class="mf-badge mf-q" title="Open questions {overlays.questions.join(', ')}"
				>{overlays.questions.length > 2 ? `${overlays.questions.length} questions` : overlays.questions.join(' ')}</span
			>
		{/if}
	</div>
{/if}
