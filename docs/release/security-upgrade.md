# Frontend dependency repair — 5 October 2026

The old Next.js 14.2.35 production dependency had known critical/high advisories.
The release preparation also exposed vulnerable Jest 29 development dependencies.
XINHAO WANG explicitly approved a major-version upgrade and full regression.

The repair pins Next.js 16.3.8, React/React DOM 19.3.0, their 19.3 type packages,
Testing Library React 16.3.3 and Jest/jsdom 30.5.2. Docker and CI use Node 24 LTS.
The [official Next.js 16 migration guide](https://nextjs.org/docs/app/guides/upgrading/version-16)
was checked alongside the installed version's bundled guide. No scoring logic,
criteria, preference weights or service URL policy changed.

React component types use React.JSX.Element. The build uses the React JSX runtime
and includes Next's generated dev types. The obsolete `next lint` script is
removed, not reported as passing lint. Existing scope tests, type checking and
Jest remain separate gates. Root-layout tests render into a document instead
of placing an html element inside a div or suppressing nesting warnings.

The lockfile was regenerated in an empty directory to include cross-platform
optional dependencies. Both local `npm ci` and Linux/arm64 Docker `npm ci` passed.
Both reported zero known vulnerabilities. The local full `npm audit` also
reported zero known vulnerabilities at verification time. This is not a
guarantee against future advisories.

Production build, 75 Jest tests, type checking and the real Compose browser
rehearsal passed after the upgrade. See verification.md for the final combined
evidence. Future dependency refreshes should rerun these gates rather than
using a forced audit fix without review.
