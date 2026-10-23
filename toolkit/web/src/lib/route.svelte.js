// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// The route is the URL hash: #<tab>[/<rest>][?<query>], for example #backlog/accounts or
// #map/unit/accounts?group=wave. An empty hash is the first tab. Tabs read route.tab, route.path
// (the parts after the tab, decoded) and route.query.

function parse() {
	const [path, query = ''] = location.hash.replace(/^#/, '').split('?')
	const [tab = '', ...rest] = path.split('/')
	return { tab, path: rest.map(decodeURIComponent), query: Object.fromEntries(new URLSearchParams(query)) }
}

export const route = $state(parse())

window.addEventListener('hashchange', () => Object.assign(route, parse()))

export function href(tab, ...path) {
	return '#' + [tab, ...path.map(encodeURIComponent)].join('/')
}
