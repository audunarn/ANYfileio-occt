# ANYfileio-occt source candidate

**Current staged editable-export boundary:** BREP export uses native file-record
provenance. Editable STEP/IGES export currently returns
`geometry.association_unproved` while their transfer lineage is unresolved.
Asset CAD read/write, editable imports and native ANYgeometry persistence remain
available. Historical STEP/IGES export evidence below does not establish safety
of the staged identity repair; those routes await their next milestone.

Optional lazy OCP provider for ANYfileio. Native operations require the pinned
`cadquery-ocp-novtk` dependency; editable operations additionally require
ANYgeometry. Public editable export uses the core atomic facade.

Implemented and covered by real native tests: STEP/IGES/BREP units/read/write,
meshes, translations, holes/shared topology, independent coincident entities,
STEP XCAF prototype/occurrence trees, nested transforms, product names and
editable occurrence separation; owner part/sheet/member export groups; exact
line, circular arc, Bezier, retained line range, elliptic arc and NURBS curves;
planar, cylindrical/conical, polynomial extrusion and NURBS patch cases.
Exact CurveOnSurface supports isocurves and affine planar composition; general
nonplanar composition refuses instead of silently fitting. Conservative free
curve approximation is opt-in, budgeted and checked against reread file curves.

Topology-backed polynomial Coons needs the new public
`anygeometry.interchange.face_support_for_interchange` capability in the tested
unreleased ANYgeometry source candidate. A version floor alone does not prove
that capability exists; missing capability is a typed operation error.

BREP files carry no units: supply a source override when reading. Model-local
coordinates are used; external-coordinate export refuses. Solids are supported
by asset APIs and rejected atomically by editable import. Source metadata losses
are reported, including origin/CRS/history/attachments/junctions and construction
or control vertex roles. STEP external references are conservatively refused
before transfer until dependency snapshots/digests are available.

This is an unreleased development candidate, not a full-family qualification.
See [implementation status](docs/IMPLEMENTATION_STATUS.md) for evidence and
remaining unsupported combinations. No publishing workflow was enabled.

Opt-in generic non-isoparametric NURBS face trims now have an admitted bounded
route. The native fit is provisional until the actual file's 3D curve and actual
pcurve-on-support both satisfy conservative owner-box certificates against the
source. Independent topology checks preserve ordered loops, holes, incidence,
face multiplicity and declared shells. Native fit tolerance is diagnostic only.
STEP transport shells around previously unowned faces do not establish original
structural intent. Periodic/located/unsupported chart representations or work
limits can still produce typed refusals. See the status note for exact evidence
and remaining limits.



The source candidate also requires the public core canonical CAD identity helper;
older cores lacking it fail with a typed capability error. Real registered core
reads now cover the native suite, including lifecycle/retention and renamed-byte
identity cases. Incident vertex identity is checked separately from counts and
wire cycles, so a same-count weld/split cannot pass a trim certificate.

The exact natural-boundary subset now also covers piecewise RuledSurface and
explicit sampled Coons patches, including exact split-border stations, plus
nonperiodic elliptic ExtrudedSurface profiles with admitted ranged/reversed and
oblique cases. Ellipse CAD u is a rational conic chart rather than the owner's
angular u; native trim domains are preserved and that transport is explicit.
Unrepresentable coefficients, arbitrary interior charts and periodic seams still
refuse. IGES now emits17 significant digits with object-local formatting; no
geometric tolerance is changed. Focused evidence is recorded in the implementation status note.
See the living status note for the tested/refused matrix and exact evidence.

Shared edges on value-equal NURBS supports now import through one exact retained
pcurve definition and one owner edge, including reversed coedges. Different
representations refuse. A narrow polynomial Ruled reconstruction admits distinct
supports when the two-row uniform chart and every actual 3D/pcurve boundary have
an exact algebraic proof; general distinct-support sharing still refuses.
STEP unowned edge-connected faces use open
transport carriers to retain existing sharing; no structural sheet is inferred.
Every editable geometry export rereads the actual file and requires a complete bounded native
material/use graph witness before publication. It preserves distinct coincident
entities, repeated oriented uses, ordered wires, outer/hole loops, shells,
containers and admitted product boundaries. Exact coordinate-distance ties remain
separate candidates; coordinates never weld identities. `max_topology_work`
bounds extraction, refinement and search independently of approximation budgets.
Fitted-trim certificates consume the graph's explicit edge-direction mapping.
Known naked STEP wireframe vertex splitting refuses atomically, including bounded
free polylines; BREP preserves that tested bounded route.

The IGES reader and writer explicitly verify their per-model coordinate units;
raw cm/mm/in file coordinates and normalized metres are independently checked.
Unknown-header overrides and inconsistent unit headers refuse. Unproved closed
or seam edge direction, branched/incomplete wires and ambiguous placed-identity
product binding also refuse. STEP parts require the emitted flat named product
structure; BREP preserves container/use boundaries with product-name loss, and
IGES declared parts remain unsupported. The preceding source suite passed 235
tests. Independent review and installed acceptance remain separate
gates. See the status note for evidence, hashes and remaining limits.

Opt-in bounded BREP interchange also admits open Plane/NURBS section trims,
including one edge shared by four faces. Export checks the source, actual file
3D curve and every incident surface pcurve. Import reconstructs a unique public
whole-section candidate and checks it against the captured raw BREP geometry
with exact physical unit ratios, including normalization rounding. Different
planar coordinate frames are supported. All bounded section reconstruction now
requires the public owner `bounded_section_work` capability. Clipped open domains
also use the public parameter-region matcher. This path retains every
possible UV region/path, refuses ambiguity or inconclusive results, and checks
unchanged world endpoints before the same literal-file certificate. UV matching
only locates proposals; it does not prove world error or recover historical
parameters. The cooperative clipped fixtures use explicit `max_depth=48` and
`max_segments=100000`; the default depth of 24 refuses this finer matching route.
The measured whole-open import and export at deviation .002 need the explicit 100k
work allowance. Defaults are unchanged, and exhausted limits refuse. Older owner
wheels missing the bounded-work capability receive a typed refusal for both
whole and clipped reconstruction; native persistence remains available.
Exact mode, unresolved domains, closed/seam cases and unsupported formats refuse.
See [clipped import status](GEOMETRY_WORKER_STATUS.md) for focused evidence and
remaining acceptance gates.

The corrective candidate checks every literal native representation-location
datum before raw certification and refuses unsupported transforms. Owner section
construction, refinement and queries cooperate with the same finite conversion
work ledger and cancellation checkpoints. This is not a hard wall-time bound.
Certified PlaneNurbs CAD export currently refuses with a typed missing-cooperative-
validation diagnostic: the owner's audit uses a separate qualification context,
and that gate is not bypassed. Committed conversion still requires its geometric
certificate. Matching wheel identities, combined checks and independent review
are recorded separately in GEOMETRY_WORKER_STATUS.md; historical full-suite
counts refer to their preserved candidate snapshots.

Editable STEP imports retain loose reference points and edges in their actual
product envelope through public ANYgeometry groups and versioned Part metadata.
These bindings do not create physical Members. Product names, distinct repeated
occurrences and existing Sheet/Member carriers remain separate; geometry added
later remains unowned unless explicitly bound. Native persistence retains the
model UUID, groups and affiliation metadata. Export validates the originating
model and Part, exact group membership and active entity references before using
the binding. Copying groups/metadata or replacing topology requires deliberate
remapping; the current default is a typed refusal. Missing, edited or ambiguous
bindings also refuse. This does not repair the separate STEP limitation for
branched connected free wireframes, or redefine export report reference IDs.
An imported wire mixing existing face-boundary edges with outside edges refuses
before owner conversion: preserving that mixed carrier as reference geometry is
not currently admitted. A reference edge sharing a face corner remains subject
to the unchanged actual-file topology gate; if STEP splits that vertex, export
refuses atomically. Separate mixed products retain each sheet and reference
edge in the same named envelope.
Entirely free wires also require an ordered native walk covering every distinct
edge use exactly once. Branched, disconnected or repeated-use carriers refuse
before conversion. Passing that accounting check does not bypass the separate
export policy for retained Member parameter ranges.

CAD export reports now reference the actual serialized document. The appended
`output_document_id` is the canonical ID returned by `read_cad` for those bytes
and units; every mapped reference belongs to that document's manifest. Export
retains the complete native topology/product witness and resolves its identities
against the same live document's canonical tables. It does not relabel prewriter
indices or claim recovery of historical IDs. STEP Parts map to occurrences;
Sheets and Members map to their actual shell/wire carriers. BREP has no
manifest-addressable compound identity, so a Part maps to its witness-verified
carrier closure with an explicit identity/name-loss diagnostic. Read nonmetre
BREP output using the report's output unit as the source-unit override.

One `max_topology_work` ledger covers native record provenance, pinned topology
and reference lookup. Defaults remain unchanged; explicit fixture allowances
remain recorded separately. Full source native geometry, ranges, pcurves and
oriented uses are frozen before writer preparation. Native ShapeSet payload
bytes and opaque entity records are captured before physical I/O. Expected
literal geometry is decoded before writing; established native encoding
(including decimal trim-domain rounding) is preserved rather than claimed
lossless. The actual document retains its SAME raw ShapeSet and native
normalization history. Raw certificates and canonical report refs consume this
one association. They no longer choose independent topology automorphisms or
endpoint matches. Repeated face-edge uses needing unproved seam-pcurve handling
refuse. Missing or altered provenance, payload/source geometry changes and
inconsistent normalization refuse atomically. Geometric bounds and the separate
legacy generated-reference contract are unchanged.

BREP Member export consumes every referenced current edge in its stored order
and use orientation. Persistent Member station ranges place those whole edges
on the chain; they do not trim an edge or its retained NURBS basis domain.
CAD loses those station ranges and edge-use history, as recorded in the write
report. Native JSON preserves them exactly. Ordinary BREP editable import keeps
the material geometry but does not infer structural Parts or Members from wire
carriers; its report states that grouping loss. Product-backed native scene
imports can reconstruct Members from complete ordered wires, with stations
reconstructed from edge lengths. Automatic structural reconstruction from an
ordinary BREP remains an open coverage gap. STEP/IGES editable export remains
staged behind the association-unproved refusal.

BREP export also checks physical fidelity independently of native record
identity. Before unit transforms or serialization it freezes every native
vertex, full supported curve/surface definition and native-returned incident pcurve. The same
record pins then select actual literal and canonical entities. Exact rational
arithmetic bounds their displacement in metres against
`min(tolerance.length, tolerance.surface_residual) / 2` in source units.
This reserve comes from the model's computational tolerances; it does not grant
approximation or grow with the coordinate origin. Existing optional approximation
certificates still check the actual literal geometry separately.

The native BREP encoder retains its established precision. Large translations
can therefore refuse with `geometry.precision.exceeded` even when topology and
record identity survive. Positive-weight equal-basis spline control bounds,
analytic same-frame bounds, full-knot parameter transport and certified pcurve
chart hulls support the check. Unknown definitions, changed weights/directions,
unproved knot changes, periodic spline definitions and unsupported extrapolation refuse
with `geometry.precision.unproved`. Only a single clamped degree-one, two-pole
curve with equal positive weights has admitted global affine continuation.
That out-of-domain continuation is fidelity under the verified OCCT 7.9.3
evaluator semantics, not a claim that every CAD reader extrapolates identically.
It requires the loaded `cadquery-ocp-novtk` distribution `7.9.3.1.1` and the
actual loaded `OCP.__version__ == '7.9.3.1'`; unknown or different versions
refuse this extension. In-domain proofs do not use that version-specific rule.
Pcurves returned by the native API can be synthesized for planar faces when
none is stored; the check covers those returned definitions, alongside the
separate full 3D edge check, and does not claim independent stored-PC evidence.
General NURBS surface extrapolation remains unproved: the different-boundary-
resolution Coons fixture and the millimetre panel emitted in inches currently
refuse when their serialized pcurves leave the active surface basis. These two
surface routes remain planned for precision verification; ordinary grid Coons
surfaces and bare millimetre lines/points emitted in inches have positive checks.
