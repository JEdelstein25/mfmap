// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// The Map tab of mfmap serve. page.html calls MfmapMap.open(element, { openSource }) the first time
// the tab is shown; openSource(path, line) is the page's source viewer.
import { mount } from 'svelte'
import App from './App.svelte'
import './style.css'

let app = null

export function open(target, options = {}) {
	if (!app) app = mount(App, { target, props: options })
	return app
}
