// Copyright (c) 2026 Amp.
//
// This program and the accompanying materials are made
// available under the terms of the Eclipse Public License 2.0
// which is available at https://www.eclipse.org/legal/epl-2.0/
//
// SPDX-License-Identifier: EPL-2.0

// Builds the Map tab into one script and one stylesheet that mfmap serve ships, so the page needs
// no network or build step at run time: toolkit/python/mfmap/static/map.js and map.css.
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

const BANNER = '/* mfmap Map tab, built from toolkit/map. Copyright (c) 2026 Amp. SPDX-License-Identifier: EPL-2.0. ' +
	'Third-party code and its licenses: map.licenses.txt. */\n'

// Writes map.licenses.txt next to the bundle, with the license of every package with code in it,
// and heads map.js and map.css with where they come from.
function licenses() {
	return {
		name: 'mfmap-licenses',
		generateBundle(_, bundle) {
			const packages = new Set()
			for (const chunk of Object.values(bundle)) {
				if (chunk.type === 'chunk') chunk.code = BANNER + chunk.code
				else if (chunk.fileName.endsWith('.css')) chunk.source = BANNER + chunk.source
				for (const id of chunk.moduleIds || Object.keys(chunk.modules || {})) {
					const m = id.match(/node_modules\/((?:@[^/]+\/)?[^/]+)\//)
					if (m) packages.add(m[1])
				}
			}
			const parts = [...packages].sort().map((name) => {
				const dir = join('node_modules', name)
				const pkg = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8'))
				const file = readdirSync(dir).find((f) => /^licen[cs]e/i.test(f))
				const text = file && existsSync(join(dir, file)) ? readFileSync(join(dir, file), 'utf8').trim() : `License: ${pkg.license}`
				return `${name} ${pkg.version} (${pkg.license})\n\n${text}\n`
			})
			this.emitFile({ type: 'asset', fileName: 'map.licenses.txt',
				source: `Third-party code in map.js and map.css\n\n${parts.join('\n' + '-'.repeat(72) + '\n\n')}` })
		},
	}
}

export default defineConfig({
	plugins: [svelte(), licenses()],
	define: { 'process.env.NODE_ENV': '"production"' },
	build: {
		outDir: '../python/mfmap/static',
		emptyOutDir: true,
		sourcemap: false,
		lib: {
			entry: 'src/main.js',
			name: 'MfmapMap',
			formats: ['iife'],
			fileName: () => 'map.js',
			cssFileName: 'map',
		},
	},
})
