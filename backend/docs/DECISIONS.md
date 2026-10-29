# Engineering decisions and requirement traceability

The user requested a geometry subsystem, not the full PRD application. The PRD, executive brief and backlog are reference specifications; they do not authorize external messages, publishing, model calls or unrelated product work. All three supplied DOCX files were read locally through their XML. Text snapshots are in `docs/source/`.

Source DOCX SHA-256:

| Document | SHA-256 |
|---|---|
| PRD | `07d6ac09a9917dd68326f6451c0ba273fc7e64095496ce32508d4fcfeed69818` |
| Executive brief | `91d2c671dd4aef32c554d84e84db8f40335b123429f9570912b2b8f7e7761386` |
| Backlog | `4849aee42df78ab2f64215352950aab4bab5b54cfd023b942a7297a822fecdde` |

## Contracts and interpretation

The existing `frontend/src/domain/types.ts` is a display-oriented mirror. It omits the PRD §20 constraint payloads, geometric region definitions, actual staging volumes, constructor minima and cut-volume limit. Its B02 records explicitly say they are illustrative. The engine therefore requires those supplemental fields and never treats the mock data as engineering-ready. Existing frontend files and behavior remain unchanged. The future HTTP adapter must project engine records into the frontend's presentation contract.

PRD §10.4 fixes local foot bottoms at Z=0. The existing frontend illustration places them at world Z=4. The engine follows the PRD local frame and applies the authoritative STEP occurrence transform once. Fixtures use an identity bracket placement; imported rotated and translated occurrences remain supported.

The PRD does not fully specify web length or post X placement. Constructor v1 makes these explicit in the binding: `web_length_mm` is required; feet are centered at ±span/2; posts occupy each foot's inner-edge strip; the web must cover the complete post tops. These choices agree with the frontend family geometry after its occurrence translation. Arbitrary imported brackets must match the resulting solid by two-way material difference before editing. No feature tree is inferred.

Finite server grids are in `templates.SERVER_DOMAINS`. The binding may narrow them, never widen them. Both T01 and T02 are implemented. T02 rebuilds top strips from the unchanged posts to the offset web; it does not translate the feet or whole bracket. A constructor-valid result can still fail envelope, keep-out, assembled or path checks.

## Numerical policy

Engineering units are millimetres. `policy_v1` uses the PRD's 0.01 mm geometry guard and 0.5 mm default noncontact clearance. This is a declared application policy, not a manufacturing standard. The entire policy payload is hashed into candidate/path identity, not only its version string.

Supplemental implementation thresholds are explicit in `Policy`: material residue/noise 1e-9 mm³, planar-contact coordinate representation noise 1e-9 mm, contact-area noise 1e-9 mm², and rigid-matrix algebraic tolerance 1e-9. These quantities have distinct units. They are numerical filters for this primitive domain, not validated industrial accuracy claims. Material differences up to the volume noise are numerically unresolved. Near clearance boundaries return unknown. The proxy coverage check subtracts every proposed box from the actual BRep and validates the Boolean output before interpreting residue.

Default material proxies inflate each full BRep bound by 0.01 mm; obstacles are additionally expanded by clearance + 0.01 mm during interval checks. This deliberately introduces additional conservatism beyond the declared minimum clearance. Trusted bracket boxes receive the same world guard after placement. Clear certificates establish the requested lower bound, not an exact minimum gap. A valid starting contact does not establish a positive gap at t=0.

Only analytic swept-box separation can admit a noncontact path. Overlap intervals and a bounded set of face-center poses guide BRep intersection/distance witness queries. Those poses can reject a move or leave it unknown; they cannot certify it clear. A hidden obstacle remains in every obstacle set. A failed Boolean, validity check or coverage check cannot create a pass.

## Native binding evidence

Tested locally: Python 3.12.16; CadQuery 2.6.1; cadquery-ocp 7.8.1.1.post1; OCCT 7.8.1 family. Installed OCP docstrings and executable probes determined overloads. `BRepTools.Write_s` needs an explicit format version when excluding triangles. `BRepAlgoAPI_Common` does not expose `HasErrors`; the wrapper checks `IsDone`, nullness and BRep validity. `STEPCAFControl_Reader.ExternFiles()` returns an unregistered Python map type; package preflight conservatively rejects external-document/reference entities before native transfer. Uniform explicitly declared millimetre STEP units are required in v1; other units are rejected rather than silently guessed.

OCCT Boolean and STEP transfer can modify flags/tolerances on shared topology. The implementation uses deep copies before Boolean operations, STEP writing and tessellation. BRep fingerprints exclude triangulations; preview generation cannot change an authoritative hash. Regression tests compare original hashes before and after analysis, editing and export.

Repeated solid-validity evidence is cached only inside each process, keyed by the complete actual BRep fingerprint and policy payload. The bounded 256-entry cache stores no shapes, caller pass flags, Boolean results or path verdicts, and returns private metadata copies. A changed transform/topology or policy causes a miss; null shapes are rejected before cache lookup. Every independent worker starts empty. All candidate reconstruction, material differences, collisions, distances and sweep decisions still execute against actual geometry. This removed redundant expensive validity checks while retaining the 30-second stage budget.

Rerunning the demo archives previous completion/stage records in content-addressed history before preparing new inputs. A timeout writes a failed-run record and cannot expose an earlier summary as the current pass. Bundle completion markers publish only after all referenced artifacts and the ZIP are durable.

Sources consulted for orientation: [CadQuery import/export](https://cadquery.readthedocs.io/en/stable/importexport.html). The stable online page contains newer APIs than this pinned release; installed source and executed binding behavior take precedence. No online documentation establishes a passing UNLOCK result.

## Supported limits and remaining scope

| Requirement area | Implementation / boundary |
|---|---|
| BL001, BL006 | Actual STEPCAFControl/XCAF traversal; structural occurrence paths, shared definitions, hierarchy, composed placements; closed single-solid leaves |
| BL004–005 | Strict Pydantic models, generated JSON Schema, bounded flat ZIP, reference checks, immutable byte artifacts and atomic completion records; SQLite/coordinator not implemented |
| BL007 | Synthetic B01/B02/B03 plus held-out B02 geometry; source, dimensions and oracle JSON; no third-party CAD or industrial validation |
| BL008–009 | Shaft + handle volumes, named terminal engagement contact, separate screw extraction; six-axis continuous material-box validation |
| BL012–014 | Actual constructor matching, T01 web cut, T02 regenerated offset web/links; protected solid/void comparison |
| BL015 | Independent reconstruction, per-constraint checks, explicit direct forward/reverse segments and stage checks; full search/reinsertion sequence is outside this assignment |
| BL016 | Original/revised assembly STEP, changed part, metadata, preview, differences and evidence; real reimport and repeated geometric/path checks; explicit part-only fallback |
| Resource limits | Import 60 s; each demo native stage 30 s; parent demo 120 s; cancellation terminates workers; Linux 8 GiB address-space cap and CPU/core limits. No production queue/coordinator is implemented |

Contact support is intentionally limited to independently isolated world-axis planar regions in opposing half spaces. Unsupported contact partitions and terminal reinsertion contacts can remain unknown. Thread engagement, torque and arbitrary drive-tip motion are not modeled. The positive tool fixture uses an outward shaft beginning on a planar simplified fastener head. B03 supplies an actual thin tool obstruction. A free-looking cylinder is never recognized as a screw without semantics.

Full source occurrence paths preserve hierarchy and ordinal positions across the supported assembly writer. Raw native occurrence IDs derive from source bytes and structural path; therefore a new STEP file has new native IDs. The revised manifest preserves semantic component IDs and maps them to reimported structural paths. Sharing identical original part definitions and occurrence-local replacement are tested. Shared subassembly definitions may be expanded into occurrence-specific assembly nodes on export; part occurrences, world placements and hierarchy are retained. Nonidentity free root placements and multiple free solid roots are explicitly unsupported for assembly export.

No disassembly optimizer, Muse controller, FastAPI service, public upload endpoint, authentication, production deployment or React integration was added. A geometry `passed` report is scoped to its listed constraints and direct segments. It is not a complete repair-route verdict, structural qualification or manufacturing release. Fixtures have a pending redistribution license; they are local synthetic examples, not rights-cleared public demo assets.
