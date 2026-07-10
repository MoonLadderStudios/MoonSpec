# MoonSpec Acceptance Assessment

MoonSpec can preserve source-backed acceptance rows in `artifacts/moonspec/source-acceptance.json` and assess current implementation evidence into `artifacts/moonspec/acceptance-assessment.json`. Both artifacts include a `featureId`; downstream stages consume them only when that value matches the active feature, so stale root artifacts from another story do not feed the current plan.

External systems can provide a matrix, including Jira, GitHub, and MoonMind adapters, but those adapters must not become required coupling for portable MoonSpec bundles.

Vertical Multi-Surface Story coverage should stay grouped when one user-visible acceptance row spans multiple implementation surfaces.

Negative Constraints must be preserved and verified or explicitly ruled out.
