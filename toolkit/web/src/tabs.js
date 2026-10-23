// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// The tabs of mfmap serve, in order. A tab is a component that reads what it shows from the shared
// report (lib/report.svelte.js) or its own endpoint (poll() in lib/resource.svelte.js) and draws it
// with the building blocks in lib/index.js. To add one, write tabs/<Name>.svelte and list it here:
//
//   id      the URL hash (#<id>[/...]); the first tab is also the empty hash
//   label   the tab's name in the header
//   badge   (report) => a count to show beside the label, or nothing
//   full    true for a tab that fills the window instead of scrolling (the Map)
import Backlog from './tabs/Backlog.svelte'
import Map from './tabs/map/Map.svelte'
import Notes from './tabs/Notes.svelte'
import Parser from './tabs/Parser.svelte'

export const TABS = [
	{ id: 'notes', label: 'Notes', component: Notes, badge: (r) => r.questions?.filter((q) => !q.answer).length },
	{ id: 'parser', label: 'Parser', component: Parser, badge: (r) => (r.files?.errors || 0) + (r.files?.crash || 0) },
	{ id: 'backlog', label: 'Backlog', component: Backlog, badge: (r) => r.plan?.units.length },
	{ id: 'map', label: 'Map', component: Map, full: true },
]
