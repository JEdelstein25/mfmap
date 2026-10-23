<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- Markdown from the server or the agent. file:line references open the source viewer. skipTitle
     drops a leading "# Title" line when the page already shows one. -->
<script>
	import { markdown } from '../markdown.js'
	import { report } from '../report.svelte.js'
	import { onSourceClick, onSourceKey } from '../source.svelte.js'

	let { text, skipTitle = false } = $props()
	const html = $derived(markdown(skipTitle ? String(text ?? '').replace(/^# .*\n/, '') : text, report.data?.root))
</script>

<!-- svelte-ignore a11y_no_static_element_interactions, a11y_click_events_have_key_events -->
<div class="mf-prose" onclick={onSourceClick} onkeydown={onSourceKey}>{@html html}</div>
