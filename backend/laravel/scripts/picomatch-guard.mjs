// Temporary backport for GHSA-fc5q-39xc-vjpf. Remove after upstream releases.
// Keep registry package identities intact so npm can report future advisories.
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const parserAnchor = 'const extglobOpen = (type, value) => {'
const parserArgs = 'type, input, state.index'
const standalone = {
    '2.3.2': '3a91656f440069aa8f8e15c9d695b9f6b2209df1eab2be8127c72cbcca45ff5f',
    '4.0.7': '4e1e05447668aa1e94366c5516a2bcd8f5fff800cc92b1d0cd7d77703b8618c4',
}
const bundles = {
    'rollup@4.67.4': [
        ['dist/es/shared/watch.js', '9a751e79d6c6616ff0b4918911076cd2a64caabb862ee2573a33523f0b87ee92'],
        ['dist/es/shared/node-entry.js', '5b1641f30396aab1746f2a0668b038636f37f405881ce4e0d03e992c3df66be9'],
        ['dist/shared/rollup.js', 'bbaa66924723048aa1459ec5bf50b0d6bc875ee5950dd840471d95079444cf1d'],
        ['dist/shared/index.js', '0e5dfd6907cced5777187d3c28b22377610765fac44e2533de20bb5008a18a80'],
    ],
    'playwright@1.56.1': [
        ['lib/common/expectBundleImpl.js', 'c43aeb7db7ade211af5ec5a41c54834e47a55d183c854e91a39f9d35b675fd58', 'Ht=($,X)=>{', '$, e, y.index'],
        ['lib/utilsBundleImpl.js', '122ed1a77842db055083e61a181813f2887dc786d176b8e820b8444d2b78f7a6', 'jt=(b,W)=>{', 'b, t, A.index'],
    ],
}

// In this project's toolchain a repeated extglob may repeat a literal word or
// unambiguous literal alternatives. Reject unsupported syntax before compiling it.
function guardRepetition(type, input, index) {
    if (type !== 'plus' && type !== 'star') return
    const end = input.indexOf(')', index + 2)
    const body = input.slice(index + 2, end)
    if (end < 0 || /[^a-zA-Z0-9_.|-]/.test(body)) {
        throw new SyntaxError('Unsupported repeated extglob in build pattern')
    }
    const words = body.toLowerCase().split('|').sort()
    if (words[0] === '' || words.some((word, i) => i > 0 && word.startsWith(words[i - 1]))) {
        throw new SyntaxError('Ambiguous repeated extglob in build pattern')
    }
}

function protectFile(path, digest, check, anchor = parserAnchor, args = parserArgs) {
    const installed = readFileSync(path, 'utf8')
    const replacement = anchor + '\n(' + guardRepetition.toString() + ')(' + args + ');\n'
    const original = installed.replaceAll(replacement, anchor)
    if (!original.includes(anchor) || createHash('sha256').update(original).digest('hex') !== digest) {
        throw new Error('Unrecognized parser source: ' + path)
    }
    const expected = original.replaceAll(anchor, replacement)
    if (installed === expected) return
    if (check) throw new Error('Missing parser protection: ' + path)
    writeFileSync(path, expected)
}

export function protectInstalled({ check }) {
    const { packages } = JSON.parse(readFileSync(join(root, 'package-lock.json'), 'utf8'))
    const protectedPaths = new Set()
    for (const [location, pkg] of Object.entries(packages)) {
        const name = location.split('/').at(-1)
        if (!['picomatch', 'rollup', 'playwright'].includes(name)) continue
        const directory = join(root, location)
        // npm ci --omit=dev can legitimately leave these development tools out.
        if (!check && pkg.dev && !existsSync(directory)) continue
        const entries = name === 'picomatch'
            ? [['lib/parse.js', standalone[pkg.version]]]
            : bundles[name + '@' + pkg.version]
        if (!entries) throw new Error('Review parser guard for ' + location + '@' + pkg.version)
        for (const [file, digest, anchor, args] of entries) {
            protectFile(join(directory, file), digest, check, anchor, args)
        }
        if (name === 'picomatch') protectedPaths.add(location)
    }
    return protectedPaths
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
    protectInstalled({ check: process.argv.includes('--check') })
}
