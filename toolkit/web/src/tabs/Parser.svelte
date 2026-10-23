<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- The Parser tab: the latest run and what the parser read and found. -->
<script>
	import { Markdown, Page, report, Stat } from '../lib/index.js'

	const files = $derived(report.data?.files || {})
	const run = $derived(report.data?.run)
</script>

<Page title="Parser">
	{#snippet meta()}
		{#if run}Run {run.id} · {run.status === 'running' ? 'parsing now' : 'finished ' + new Date((run.finished || run.started) * 1000).toLocaleString()}{:else}No parse has run yet{/if}
	{/snippet}
	{#if run}
		<div class="stats">
			<Stat value={files.clean ?? 0} label="clean" tone="var(--mf-ok)" />
			<Stat value={files.errors ?? 0} label="with errors" tone={files.errors ? 'var(--mf-danger)' : undefined} />
			<Stat value={files.crash ?? 0} label="crashed" tone={files.crash ? 'var(--mf-danger)' : undefined} />
		</div>
	{/if}
	<Markdown text={report.data?.parser} skipTitle />
</Page>

<style>
	.stats { display: flex; gap: 28px; padding: 14px 18px; margin-bottom: 24px; background: var(--mf-surface); border: 1px solid var(--mf-line); border-radius: var(--mf-radius); }
</style>
