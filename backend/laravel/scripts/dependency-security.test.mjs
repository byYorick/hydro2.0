import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import test from 'node:test'
import { onlyPatchedFindings } from './audit-dependencies.mjs'
import { protectInstalled } from './picomatch-guard.mjs'

const installed = protectInstalled({ check: true })
const rootRequire = createRequire(new URL('../package.json', import.meta.url))

test('ordinary build patterns work on every installed parser', () => {
    for (const location of installed) {
        const matcher = rootRequire('./' + location)
        assert.equal(matcher('**/*.vue')('src/Home.vue'), true)
        assert.equal(matcher('+(foo|bar).js')('foobar.js'), true)
        assert.equal(matcher('+(foo|bar).js')('other.js'), false)
        // A bounded, harmless example of syntax outside our supported subset.
        assert.throws(() => matcher('+([ab]).js'), /Unsupported repeated extglob/)
    }
})

test('audit requires the matching advisory, installed paths and dependency chain', () => {
    const cause = { url: 'https://github.com/advisories/GHSA-fc5q-39xc-vjpf' }
    const picomatch = { severity: 'high', nodes: [...installed], via: [cause] }
    const tool = { severity: 'high', via: ['picomatch'] }
    assert.equal(onlyPatchedFindings({ picomatch, tool }, installed), true)
    assert.equal(onlyPatchedFindings({ picomatch, tool }, new Set()), false)
    const other = { url: 'https://example.org/independent-finding' }
    assert.equal(onlyPatchedFindings({ picomatch: { ...picomatch, via: [cause, other] } }, installed), false)
    assert.equal(onlyPatchedFindings({ picomatch, tool: { severity: 'critical', via: [other] } }, installed), false)
    assert.equal(onlyPatchedFindings({ picomatch, tool: { ...tool, via: ['missing'] } }, installed), false)
})
