<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->
<!-- An endpoint from migration.json (kind:name) as a chip. A program opens its paragraphs on the map. -->
<script>
	import { href } from '../lib/index.js'

	let { value } = $props()
	const kind = $derived(value.includes(':') ? value.slice(0, value.indexOf(':')) : '')
	const name = $derived(kind ? value.slice(kind.length + 1) : value)
</script>

{#if kind === 'program'}
	<a class="ui-endpoint" href={href('map', 'program', name)} title="Open {name} on the map"><span class="mono">{name}</span></a>
{:else}
	<span class="ui-endpoint" title={value}><span class="mono">{name}</span>{#if kind}<small>{kind}</small>{/if}</span>
{/if}

<style>
	.ui-endpoint { display: inline-flex; align-items: baseline; gap: 5px; padding: 1px 7px; border-radius: 5px; background: var(--mf-sunken); color: var(--mf-fg); font-size: 12px; max-width: 100%; }
	.ui-endpoint .mono { font-size: 12px; overflow-wrap: anywhere; }
	a.ui-endpoint .mono { color: var(--mf-accent); }
	a.ui-endpoint:hover { text-decoration: none; background: var(--mf-accent-soft); }
	small { color: var(--mf-faint); font-size: 10.5px; }
</style>
