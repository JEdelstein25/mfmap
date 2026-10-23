<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- The Notes tab: the questions the agent recorded for a person, open ones first, and the agent's
     notes. -->
<script>
	import { Empty, Markdown, Page, report, Section, Segmented } from '../lib/index.js'
	import Question from './Question.svelte'

	let filter = $state('open')
	const questions = $derived(report.data?.questions || [])
	const open = $derived(questions.filter((q) => !q.answer))
	const shown = $derived(filter === 'open' ? open : filter === 'answered' ? questions.filter((q) => q.answer) : [...open, ...questions.filter((q) => q.answer)])
</script>

<Page title="Notes">
	{#snippet meta()}<span class="mono">{report.data?.root}</span>{/snippet}
	<Section title="Questions for you" count={questions.length ? `${open.length} open of ${questions.length}` : undefined}>
		{#snippet actions()}
			{#if questions.length}
				<Segmented label="Show" bind:value={filter} options={[
					{ value: 'open', label: 'Open', count: open.length },
					{ value: 'answered', label: 'Answered', count: questions.length - open.length },
					{ value: 'all', label: 'All' },
				]} />
			{/if}
		{/snippet}
		{#if questions.length}
			<p class="intro">None of these block the work: the agent goes ahead with each default. Answer one with <code class="mf-code">mfmap answer</code> to change the plan.</p>
			<div class="list">
				{#each shown as q (q.id)}<Question {q} />{/each}
			</div>
			{#if !shown.length}<Empty>No {filter} questions.</Empty>{/if}
		{:else}
			<Empty title="No questions yet">The agent adds them here as it finds things the source cannot answer.</Empty>
		{/if}
	</Section>
	<Section title="Agent notes">
		<Markdown text={report.data?.notes?.replace(/^## Agent Notes\n/, '')} />
	</Section>
</Page>

<style>
	.intro { margin: -4px 0 12px; color: var(--mf-muted); font-size: 13.5px; }
	.list { display: flex; flex-direction: column; gap: 10px; }
</style>
