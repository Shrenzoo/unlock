# Original B02 publication grant and provenance

Recorded 2026-10-30. This is the account holder's authorization record, not an
independent legal title search or a direct statement collected from his brother.

Shreyas Pabbathi confirmed in this task that he and his brother created UNLOCK
and the original B02 fixture through their own implementation with AI assistance,
and did not knowingly import proprietary CAD or third-party geometry. He
authorized public display and redistribution of their original B02 and generated
engineering results under CC BY 4.0, conditional on all rightsholders agreeing.
When specifically asked whether his brother agreed to these terms, he answered
"yes he has". Both identified contributors' agreement is therefore recorded by
the account holder. No other human contributor appears in the reviewed fixture
and bridge constructor Git history, and none has been identified in this task.

The original constructor entered Git in `c18342f` on 2026-10-29, under Shreyas
Pabbathi's commit identity. It constructs boxes, cylinders, a bridge and holes
with CadQuery, assembles eight occurrences, and exports real STEP. The bridge
constructor is in `src/unlock_engine/templates.py`; no external CAD file is
imported by the fixture source. Seed 0 and all dimensions are explicit. Git
history and source inspection support this provenance; they do not independently
prove that no unrecorded contributor exists. The ownership confirmation above
supplies the authors' account.

Copyright 2026 the UNLOCK team (Shreyas Pabbathi and his brother). The team's
original B02 geometry and generated demonstration assets are licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) with its
[legal terms](https://creativecommons.org/licenses/by/4.0/legalcode).
Attribute the UNLOCK team, retain the license link and identify adaptations.
The revised assembly and changed bracket are marked as adaptations, with their
actual changes recorded in template parameters and geometry differences.

Covered assets include original and revised B02 STEP geometry, its changed
bracket, previews, manifests, paths, constraints, verification results and
associated generated demonstration evidence, to the extent the team holds rights.
This grant does not relicense application source, third-party dependencies,
trademarks, other fixtures, private engineering inputs or third-party materials.
In particular, B01, B03 and the held-out fixture variant retain their existing
provenance. AI assistance is disclosed; no third-party model output is presented
as proof of ownership or engineering safety.

New B02 exports include `attribution.txt`, `LICENSE-B02.txt` and
`THIRD_PARTY_NOTICES.txt` inside their hashed file inventory. Dependency notices
remain installed with the pinned backend libraries. The frontend deployment also
preserves its shipped dependency notices. No dependency source or binary is
included in a CAD export, and the B02 grant does not change a dependency license.

The old pending-license snapshots and historic evidence remain immutable. A new
run must generate geometry, independent checks, STEP round trips, licensing
files and all hashes before it can become the public snapshot. This statement
does not retrospectively relabel the old evidence. The example remains synthetic
and does not establish physical safety, structural qualification or fitness for
manufacturing.
