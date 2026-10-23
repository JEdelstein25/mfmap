<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- One question for a person: what the agent found, the default it goes ahead with, what the answer
     affects, and the answer once someone gives one with mfmap answer. -->
<script>
	import { Badge, Card, Facts, Inline } from '../lib/index.js'

	let { q } = $props()
</script>

<Card muted={!!q.answer} class="ui-question">
	<div class="head">
		<span class="id mono">{q.id}</span>
		<div class="text"><Inline text={q.question} /></div>
		{#if q.answer}<Badge tone="var(--mf-ok)">Answered</Badge>{:else}<Badge tone="var(--mf-question)">Open</Badge>{/if}
	</div>
	<div class="facts"><Facts rows={[['Found', q.found], ['Default', q.default], ['Affects', q.affects], ['Answer', q.answer]]} /></div>
</Card>

<style>
	:global(.ui-question) { padding: 14px 16px; }
	.head { display: flex; align-items: flex-start; gap: 10px; }
	.id { flex: none; margin-top: 2px; font-size: 12px; color: var(--mf-faint); }
	.text { flex: 1; font-weight: 600; font-size: 14.5px; }
	.facts { margin-top: 10px; }
</style>
