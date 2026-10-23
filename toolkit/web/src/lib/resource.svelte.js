// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// A JSON endpoint that refreshes itself, for live tabs: poll('api/x') fetches it now and every
// `interval` ms while the page is visible (or `busy` ms while `isBusy(data)`), sends the last ETag so
// an unchanged answer costs a 304, and replaces `data` only when the body changed, so components
// keyed on it keep their state (a half-typed answer, an expanded card).
//
//   const report = poll('api/report', { isBusy: (d) => d.run?.status === 'running' })
//   {#if report.data}...{report.updated.toLocaleTimeString()}{/if}

export function poll(url, { interval = 4000, busy = 1500, isBusy = () => false } = {}) {
	const state = $state({ data: null, error: null, updated: null, loading: true })
	let etag = null
	let text = null
	let timer = null

	async function load() {
		try {
			const res = await fetch(url, { headers: etag ? { 'If-None-Match': etag } : {} })
			if (res.status !== 304) {
				if (!res.ok) throw new Error(`HTTP ${res.status}`)
				etag = res.headers.get('ETag')
				const body = await res.text()
				if (body !== text) {
					text = body
					state.data = JSON.parse(body)
				}
			}
			state.error = null
			state.updated = new Date()
		} catch (e) {
			state.error = 'Disconnected; retrying'
		} finally {
			state.loading = false
		}
	}

	async function tick() {
		clearTimeout(timer)
		if (!document.hidden) await load()
		timer = setTimeout(tick, state.data && isBusy(state.data) ? busy : interval)
	}

	document.addEventListener('visibilitychange', () => !document.hidden && tick())
	tick()
	// Call after a change this page made, to show it without waiting for the next poll.
	state.refresh = tick
	return state
}

// POSTs JSON and returns the JSON answer, or throws with the server's error.
export async function post(url, body) {
	const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
	const data = await res.json().catch(() => ({}))
	if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
	return data
}
