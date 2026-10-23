<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- One question for a person: what the agent found, the default it goes ahead with, what the answer
     affects, and a form to answer it (saved through /api/answer). A half-typed answer survives
     refreshes because the list is keyed by question ID. -->
<script>
	import { Badge, Button, Card, Facts, Inline, post } from '../lib/index.js'

	let { q, onsaved } = $props()
	let editing = $state(false)
	let draft = $state(null)
	let saving = $state(false)
	let error = $state(null)
	const open = $derived(!q.answer || editing)

	async function save(event) {
		event.preventDefault()
		saving = true
		error = null
		try {
			onsaved(await post('api/answer', { id: q.id, answer: draft ?? q.answer ?? '' }))
			editing = false
			draft = null
		} catch (e) {
			error = e.message
		} finally {
			saving = false
		}
	}
</script>

<Card muted={!!q.answer && !editing} class="ui-question">
	<div class="head">
		<span class="id mono">{q.id}</span>
		<div class="text"><Inline text={q.question} /></div>
		{#if q.answer}<Badge tone="var(--mf-ok)">Answered{q.by === 'page' ? ' here' : ''}</Badge>{:else}<Badge tone="var(--mf-question)">Open</Badge>{/if}
	</div>
	<div class="facts"><Facts rows={[['Found', q.found], ['Default', q.default], ['Affects', q.affects]]} /></div>
	{#if open}
		<form onsubmit={save}>
			<textarea rows="1" placeholder="Your answer"
				value={draft ?? q.answer ?? ''} oninput={(e) => (draft = e.currentTarget.value)}></textarea>
			<div class="buttons">
				{#if editing}<Button variant="ghost" size="sm" onclick={() => ((editing = false), (draft = null))}>Cancel</Button>{/if}
				<Button variant="primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
			</div>
		</form>
		{#if error}<p class="error">{error}</p>{/if}
	{:else}
		<div class="answer">
			<span class="label">Answer</span>
			<div><Inline text={q.answer} /></div>
			<Button variant="ghost" size="sm" onclick={() => (editing = true)}>Change</Button>
		</div>
	{/if}
</Card>

<style>
	:global(.ui-question) { padding: 14px 16px; }
	.head { display: flex; align-items: flex-start; gap: 10px; }
	.id { flex: none; margin-top: 2px; font-size: 12px; color: var(--mf-faint); }
	.text { flex: 1; font-weight: 600; font-size: 14.5px; }
	.facts { margin: 10px 0 0 0; }
	form { display: flex; gap: 10px; align-items: flex-end; margin-top: 12px; }
	textarea { flex: 1; min-height: 38px; resize: vertical; padding: 8px 10px; font-size: 13.5px; border: 1px solid var(--mf-line-strong); border-radius: 7px; background: var(--mf-surface); }
	textarea:focus { outline: none; border-color: var(--mf-accent); box-shadow: 0 0 0 3px var(--mf-accent-soft); }
	.buttons { display: flex; gap: 6px; }
	.answer { display: flex; gap: 12px; align-items: baseline; margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--mf-line); font-size: 13.5px; }
	.answer > div { flex: 1; }
	.label { color: var(--mf-ok); font-weight: 650; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }
	.error { color: var(--mf-danger); font-size: 13px; margin: 6px 0 0; }
</style>
