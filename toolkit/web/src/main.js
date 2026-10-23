// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// The page of mfmap serve. page.html calls Mfmap.start(element) once.
import './lib/tokens.css'
import { mount } from 'svelte'
import App from './App.svelte'

export function start(target) {
	return mount(App, { target })
}
