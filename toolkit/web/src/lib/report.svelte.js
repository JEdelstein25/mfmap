// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// /api/report, which the header and the Notes, Parser and Backlog tabs share: the latest run, the
// questions, the notes and the parser summary as Markdown, file counts, and migration.json as `plan`.
import { poll } from './resource.svelte.js'

export const report = poll('api/report', { isBusy: (d) => d.run?.status === 'running' })

// A unit's status in migration.json (see the schema), with its label and colour token.
export const STATUS = {
	todo: { label: 'To do', color: 'var(--mf-status-todo)' },
	building: { label: 'Building', color: 'var(--mf-status-building)' },
	built: { label: 'Built', color: 'var(--mf-status-built)' },
	verified: { label: 'Verified', color: 'var(--mf-status-verified)' },
}

// A path relative to the parse root, for display.
export function short(path) {
	const root = report.data?.root
	return path && root && path.startsWith(root + '/') ? path.slice(root.length + 1) : path
}
