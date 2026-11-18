import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { protectInstalled } from './picomatch-guard.mjs'

const advisory = 'https://github.com/advisories/GHSA-fc5q-39xc-vjpf'
// npm also flags packages which depend on an affected package. Trace each
// blocking finding to its advisory, including cyclic peer-dependency graphs.
function coveredByBackport(name, findings, protectedPaths) {
    const pending = [name]
    const visited = new Set()
    let foundBackport = false
    while (pending.length) {
        const current = pending.pop()
        if (visited.has(current)) continue
        visited.add(current)
        const entry = findings[current]
        if (!entry?.via?.length) return false
        for (const cause of entry.via) {
            if (typeof cause === 'string') {
                pending.push(cause)
            } else if (current === 'picomatch' && cause.url === advisory &&
                       entry.nodes?.length && entry.nodes.every(path => protectedPaths.has(path))) {
                foundBackport = true
            } else {
                return false
            }
        }
    }
    return foundBackport
}

export function onlyPatchedFindings(findings, protectedPaths) {
    const blocking = Object.entries(findings)
        .filter(([, entry]) => ['high', 'critical'].includes(entry.severity))
    return blocking.length > 0 && blocking.every(([name]) => coveredByBackport(name, findings, protectedPaths))
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
    const protectedPaths = protectInstalled({ check: true })
    const audit = spawnSync('npm', ['audit', '--include=dev', '--audit-level=high', '--json'], {
        encoding: 'utf8', maxBuffer: 32 * 1024 * 1024,
    })
    if (audit.error) throw audit.error
    if (audit.status === 0) process.exit(0)
    const report = JSON.parse(audit.stdout)
    if (audit.status !== 1 || report.auditReportVersion !== 2 || report.error || !report.vulnerabilities) {
        throw new Error('npm audit did not return a valid dependency report: ' + audit.stderr)
    }

    if (!onlyPatchedFindings(report.vulnerabilities, protectedPaths)) {
        console.error(audit.stdout)
        process.exit(1)
    }
    console.log('npm audit reported %s. Verified local parser guard across %d installed picomatch packages and bundled parsers.', advisory, protectedPaths.size)
}
