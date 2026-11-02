# Glossary

[← Back to the README](../README.md)

Terms the README uses that may be unfamiliar if you don't work in mechanical CAD.

**B-rep (boundary representation).** The standard way CAD software represents a solid: not a mesh of triangles, but an exact mathematical description of its faces, edges and vertices. UNLOCK verifies against real B-reps throughout, which is why its measurements are exact rather than approximate.

**STEP file.** A neutral, vendor-independent file format (`.step`, ISO 10303) for exchanging 3D geometry. AP214 and AP242 are the two variants UNLOCK accepts. UNLOCK additionally requires explicit uniform millimetre units, a flat package, and 5–12 rigid single-solid parts.

**Assembly.** Multiple parts, each a solid, positioned relative to one another. UNLOCK treats parts as discrete components with declared roles, so it knows which one failed and which ones are fixed.

**Keep-out / protected region.** An area of the model that must not be touched: a mounting interface, a sealing surface, a clearance zone. Declared up front, hashed into the revision's identity, and checked on every candidate.

**Envelope.** The bounding volume the design must stay inside.

**Removal path.** The trajectory a part takes to leave its assembly. UNLOCK searches along six axes with tool-approach constraints, using conservative coverage plus complete analytic sweep separation.

**Sweep separation.** Proving that as a part moves along a path, no other solid ever intersects the volume it sweeps through. It is the geometric core of "can this part actually come out".

**Conservative coverage.** Over-approximating a region rather than under-approximating it. When the checker is unsure it says `unknown` rather than guessing, so doubt never produces a pass.

**Witness.** A concrete, inspectable piece of evidence for a claim. When the planner says a bracket blocks extraction, it produces a B-rep witness at real coordinates you can look at.

**Boolean operation.** Union, subtraction or intersection between two solids. UNLOCK uses them to remove material and to prove the removal stayed inside the declared region.

**Deep copy at mutation boundaries.** OCCT, the geometry kernel, can silently change shared topology flags during boolean and transfer operations. Taking private copies at each boundary keeps the original geometry unchanged.

**Tessellation.** Converting an exact B-rep into triangles for display. UNLOCK renders tessellated geometry in Three.js but verifies against the exact B-rep underneath.

**Provenance.** Where a result came from: computed live, computed earlier, or merely illustrated. The frontend only paints a pass green when it is backed by computed evidence.

**Revision.** An immutable snapshot of imported geometry with its constraints hashed into its identity. Evidence computed against one revision can't be replayed against another.
