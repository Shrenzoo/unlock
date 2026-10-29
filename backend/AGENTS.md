# Geometry subsystem guidance

- Keep original BReps immutable. OCCT Boolean, compound assembly, STEP transfer and tessellation can change shared topology flags: use private deep copies at mutation boundaries.
- Only validated conservative coverage plus complete analytic sweep separation can admit a translation. Witness sampling can reject or leave unknown, never admit.
- Preserve separate clear, blocked and unknown statuses. Mandatory unknown/missing checks prohibit a passing aggregate.
- Put numerical assumptions in `contracts.Policy`, include the full policy in evidence identity and invalidate stale geometry/constraint hashes.
- Use only trusted constructors and finite server grids for edits. Independently reconstruct candidates and inspect actual protected material and voids.
- STEP export success requires real reimport and geometry/path checks. Preserve hierarchy/occurrence placements; label part-only fallback explicitly.
- Run `python -m pytest` and `ruff check src tests` from this directory using Python 3.12 and the pinned lockfile. Keep raw evidence and report failures honestly.
- Native parsing and geometry belong in bounded processes before any future HTTP integration. Do not add model calls, publication, external geometry transfer or frontend redesign to a geometry task.
