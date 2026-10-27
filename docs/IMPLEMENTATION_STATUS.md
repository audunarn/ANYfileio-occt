# Provider implementation status

State: partial implementation, verified against the implemented criteria; broader parity remains open. Policy ANY_ECOSYSTEM_RISK_PROPORTIONATE_ENGINEERING_V1 revision 2026-09-24.2 retained. Original subscription worker unavailable; OpenAI fallback owns implementation. No publication or Git integration performed.

Implemented:
- Real lazy OCP STEP/IGES/BREP read, manifests, meshes including edge ranges/normals, translation, metre normalization and output units, thread-affine native ownership, guarded writer settings, live/preview/manifest modes, typed cancellation/healing/unit refusals.
- Editable STEP/IGES/BREP conversion of open topology: shared CAD identities, independent coincident entities, ordered loops/holes, periodic circles split into four open arcs, exact Straight/Arc/Bezier/EllipticArc/LineRange/NURBS curves, affine/isoparametric CurveOnSurface paths; planes, cylinders/cones, native rational extrusion supports, NURBS support, declared export part/sheet/member groups.
- Exact owner Coons materialization consumed through public anygeometry.interchange; four polynomial side charts constructed algebraically, chart rotation determined by exact corners. Generic nonplanar CurveOnSurface composition refuses rather than invoking OCCT numerical BuildCurves3d.
- Explicit bounded free specialized curves use owner conservative AABBs, exact rational squared norms with bounded Decimal initialization, depth/segment budgets, a prospective serialization reserve and reread straight-segment endpoint enclosures. Endpoint correspondence includes all file straight edges; exact physical unit ratios and prewriter scale rounding are included.
- Model-bound EntityHandle reports, immutable mappings, fresh imported identity, revision drift checks, optional caller read lease. Source model remains untouched.

Evidence so far: full suite provider-tests09 46 passed (3.219s process wall). Later provider-tests11 47 passed/1 failed; failure isolated to owner angular seam branch for cone, parent has now repaired owner implementation without tolerance relaxation. New test retry pending. Prior failures preserved in task evidence root C:/ANYworkspaceWork/anyfileio-geometry-20261026. No scientific tolerance relaxed: extrusion manifest-bound check was replaced with actual analytical support-coordinate test at 1e-12, since OCCT boxes deliberately include kernel gap.

Open/partial:
- STEP assembly hierarchy, separate coincident occurrences and XCAF names are not yet preserved; backend honestly advertises assembly=False and diagnoses flattening. Next integrated slice is XCAF manifests/native instance state plus independently merged editable occurrences.
- Generic nonplanar pcurve composition; general periodic NURBS/seams/shared multi-support pcurves; arbitrary trim consistency for approximations; nonrectangular explicit piecewise Coons/Ruled trims; generic extrusion profiles and all-family parity need further cases. These are typed refusals where current native construction cannot establish consistency.
- CAD origin/CRS/history/tags/groups/attachments/junctions metadata losses remain explicit. Core native route owns full-fidelity metadata.
- Review: parent independent review active; full parity not accepted. No release/qualification campaign claimed.

## Stable checkpoint 2026-10-26, before bounded trim continuation

Latest full suite: `C:/ANYworkspaceWork/anyfileio-geometry-20261026/venv/Scripts/python.exe -m pytest -q --tb=short`, cwd `C:/Github/ANYfileio-occt`, with task PYTHONPATH across core/geometry/provider. Result **64 passed**, process wall **3.922 s**. Receipt/raw output: `C:/ANYworkspaceWork/anyfileio-geometry-20261026/provider-tests21/`. Earlier failed attempts remain preserved, including CAF unit error, unsupported ExternFiles binding, invalid owner chart fixture, and cone owner scalar/vector seam regressions.

Updates superseding earlier open items: STEP XCAF native hierarchy/prototypes/occurrences and per-prototype meshes now work; repeated coincident occurrences import independently via public insert_model handle mappings. Nested rotation/translation composes once. Declared product parts and names round-trip; source shell/wire groups become owner sheets/members with explicit product part metadata. Native STEP asset translation retains XCAF hierarchy. Backend assembly=True now reflects those operations; IGES hierarchy and colour/layer omissions remain reported. Cone/cylinder supports now retain native trimmed UV extent; exact analytic line/circle pcurves implemented. Owner scalar/vector seam fixes are parent-owned, not provider tolerance changes. Public export delegates core atomic write; late mutation preserves existing destination. Messenger printers are guarded/restored and native informational C++ stdout suppressed; warning/error text goes to stderr. External STEP entity types refuse before transfer because this OCP binding cannot return ExternFiles DataMap.

Current changed files: `_native.py`, `_geometry.py`, `_xde.py`, `geometry_export.py`, `geometry_import.py`, `backend.py`, `pyproject.toml`, bootstrap/layering/native-foundation tests, new native geometry tests, README and this note. Pre-existing AGENTS/ECOSYSTEM_GUIDE changes preserved.

Remaining: generic nonplanar CurveOnSurface exact composition; generic bounded approximate trims (next authorized 35-call milestone); arbitrary ruled/explicit sampled-Coons trims; elliptic extrusion trim charts; periodic NURBS/seams and shared multi-support charts; comprehensive every-family parity. Exact rows only claim the tested cases above. Source coefficients not representable in native chart coordinates refuse. Read endpoint proxies must meet translation-invariant public owner feature_extent/curve-fit policy; moved native LINE/CIRCLE endpoints at offsets0 and1e8 refuse. Report keys/values/approximation sources are model-bound EntityHandles. Native output precision/capability limitations remain explicit; no full parity, qualification or release claim. Review active with parent.

## Bounded trim progress checkpoint

Opt-in generic nonplanar CurveOnSurface face trims now construct native pcurve+support edges, explicitly request/check OCCT BuildCurves3d fit with a prospective 1/8-tolerance fit target, and keep those records pending until reread-file certification. Exact default still refuses general composition. Actual file NURBS/Bezier 3D curves are reconstructed from full original knots/poles/weights/domain without Segment/refit; actual file face NURBS support and pcurve are reconstructed separately. Exact chart normalization must be representable; periodic, located or unsupported representations refuse. Source, file3D and filetrim conservative boxes are scaled with exact physical ratios and their union diameter is tested with exact rational arithmetic. This bounds normalized-parameter error and both Hausdorff directions; fit tolerance/samples are not acceptance. Endpoint proposals select a bijective edge correspondence; ambiguity refuses. Matching and subdivision share a global work cap.

First focused integration: BREP and STEP non-isoparametric four-edge NURBS face export -> reread certificate -> editable import both pass, source serialization unchanged. Command taskvenv `-m pytest tests/test_native_geometry.py -q --tb=short -k bounded_noniso`, evidence `provider-trimtests01` (2 passed,45 deselected,2.219 s process wall). Remaining before this milestone handoff: limit/cancel/tampered-file-PCurve refusals, full suite, STEP external-reference regression/empty-leaf guard from stable-checkpoint review, documentation and parent independent proof review.

## Final stable provider handoff (supersedes earlier open/checkpoint rows)

State: **verified against implemented provider/trim criteria; full-family parity remains partial**. Code is stable for parent wheel build and independent final review. No provider code edits are planned during that build. Source snapshot changed files:

- src/anyfileio_occt/backend.py, _native.py, _geometry.py, _xde.py, _trim_bounds.py, geometry_export.py, geometry_import.py
- pyproject.toml
- tests/test_bootstrap.py, test_layering.py, test_native_foundation.py, test_native_geometry.py
- new README.md and docs/IMPLEMENTATION_STATUS.md

Existing AGENTS.md/ECOSYSTEM_GUIDE.md changes were preserved. No sibling edits, network, workers, Git integration or publication by this worker.

Final command: task venv `python -m pytest -q --tb=short`, cwd C:/Github/ANYfileio-occt, task PYTHONPATH core+geometry+provider. **82 passed**, **5.531 s precise process wall**. Evidence directory: `C:/ANYworkspaceWork/anyfileio-geometry-20261026/provider-specialized02/` (command.json, result.json, stdout.jsonl, stderr, cleanup proof). Previous full provider-trimtests11 was79 passed; three actual public specialized family fixtures added after that: QuadricIntersectionCurve, BezierQuadricCurve, PlaneNurbsCurve, each exact-default refusal and certified bounded free-curve BREP write/reread. CylinderIntersectionCurve and generic CurveOnSurface free curves also have real bounded-file tests. Legal one-segment approximation was initially overconstrained by a test assertion; changed the count assertion to >=1 without changing deviation tolerance or certificate.

Bounded non-isoparametric NURBS trim evidence now covers BREP+STEP export, actual serialized 3D and pcurve/support enclosures, editable import, unchanged source, post-file cancellation, depth/segment limits, actual-file pcurve tampering, dropped/reversed faces, reassigned declared shells and duplicate carriers. All late failures preserve existing destination bytes. The source/3D/trim union-box proof uses full native knots/poles/weights/domains without Segment/refit, exact physical unit ratios and exact rational squared widths; native fit tolerance is separately reported and never substitutes for the certificate. Native coefficient/chart representations, periodicity, locations or matching ambiguities outside admitted cases typed-refuse.

Topology gate is separate from geometry proof: complete unambiguous edge bijection, nonshell material counts, oriented outer/hole cycles (cyclic rotation allowed, parameter reversal accounted), material face traversal multiplicity, every declared source shell oriented face multiset and open/closed state. Extra STEP carrier shells must be OPEN, contain only originally shell-unowned faces at original multiplicity, and neither duplicate incidence nor mix/reassign owned groups. No caps, solids or healing. CAD carrier shell -> imported sheet means file grouping only, not evidence of original source structural intent; diagnostics/import metadata losses explicitly say so. STEP transport-shell exception failed initially under strict shellcount equality, preserved provider-trimtests05; refined gate follows parent's adopted strict exception. Geometry proof independently reviewed clean before this topology addition; parent final topology review pending.

Stable-source additional contracts: shallow committed export avoids owner serialization; certified mode invokes the owner's certified gate. EntityHandle mapping keys, imported values, approximation sources and diagnostics are model-bound. Exact chart remapping and affine composition use rational coefficient equality/representability guards. Equal-but-distinct immutable NURBS support values share a native support handle correctly. Explicit sampled Coons tensor conversion now forms exact rational controls algebraically, refusing unrepresentable coefficients rather than evaluating rounded grid samples. STEP external-reference entities refuse before Transfer (real parsed StepModel injected native DocumentFile regression); null/empty converted leaf products refuse. Native informational C++ stdout is suppressed under restored messenger guard; warnings/errors remain stderr, and printer restoration is tested after success/failure.

Verified exact case families: free Straight/Arc/Bezier/EllipticArc/retained LineRange/NURBS; planar holes and shared edges; cylindrical/conical patches with exact line/circle trim charts and preserved height/span; polynomial owner ExtrudedSurface rectangular profile/generator trims; topology-backed polynomial Coons extrusion via public owner support materialization; NURBS iso/affine planar curve composition. Analytic ellipse and LineRange endpoint equality is checked on real BREP data. General CurveOnSurface exact composition deliberately refuses; opt-in generic NURBS face trims now have the bounded admitted route described above.

Remaining explicit limits: arbitrary RuledSurface/explicit sampled-Coons trimmed face charts are not qualified; elliptic extrusion trim charts refuse; periodic NURBS/seams and shared different-support pcurves refuse; nonrepresentable exact coefficient transport refuses; located fitted-trim certificates refuse; unusual serialized native curve/pcurve representations can legitimately refuse. IGES hierarchy/colour/layer metadata is partial; native format owns full fidelity. Nested structural parts are not an owner concept, so STEP occurrence parent links are retained as part metadata with explicit loss. Extreme/nonrepresentable source/target cases are not a general qualification. No full every-family parity, performance savings, different-family review completion, release or publication is claimed.

## Installed-boundary correction checkpoint (latest stable snapshot)

The parent's first installed-wheel smoke uncovered a real protocol integration failure: the backend copied a filename-dependent import identity instead of the core's frozen canonical identity. Failed wheel and smoke evidence are preserved by the parent. Backend now calls the new public `anyfileio.cad.cad_import_document_id` helper; no copied formula remains. Missing helper is typed `cad.core.capability_missing`. Source SHA/format/effective unit/heal/backend protocol determine identity; renaming identical bytes preserves document and CAD reference identity.

Real core validation also exposed missing retained-snapshot attachment and requested live tessellation publication. Final provider documents now attach the core-owned snapshot only when requested, return correctly closed preview/manifest lifecycles, and publish requested live meshes. The internal live wrapper used during assembly/mesh construction is never published and has no source snapshot; CadDocument has no destructor/finalizer, so dropping that wrapper does not close the sole returned owner's native state. No broad lifecycle refactor was needed after confirming that core behavior. Parent changed ephemeral facade import to retain_source=False, so the core releases the source spool before geometry conversion while the fully loaded native state remains live.

All native geometry tests now use real registered `read_cad` through their common read helper, with retain_source=False; direct backend calls remain only where intentionally testing protocol/foundation internals. Explicit retained-source tests release snapshots in finally blocks. Dedicated integration cases cover all three modes, live meshes, retained/released snapshots, same bytes under two filenames, all three formats with no retention, actual facade read_geometry, and old-core helper absence. Focused evidence: provider-core-boundary01,7 passed; provider-vertex-identity01,1 passed.

Final topology refinement derives a vertex identity mapping from BOTH endpoints of every matched edge, with parameter reversal accounted. It requires consistency, injectivity and surjectivity over all incident vertices, independently of coordinates and total counts. A real postwriter BREP adversary welds one source corner and splits another, preserves all six topology counts and all 3D curve definitions, and is rejected as welded vertex correspondence before any cycle/geometric certificate can accept it. Old destination bytes remain intact.

Latest full source command: task venv `python -m pytest -q --tb=short`, cwd C:/Github/ANYfileio-occt, core/geometry/provider source PYTHONPATH and actual registered provider metadata. **90 passed**, **5.531 s process wall**, evidence `C:/ANYworkspaceWork/anyfileio-geometry-20261026/provider-final-core01/`. Actual core load/read now passes. Only backend.py, _trim_bounds.py, native geometry tests and docs changed in this focused continuation. Code is stable for parent rebuild of core/provider; owner source unchanged. Independent final installed-wheel verification remains parent-owned; no release/full-parity claim.

## 2026-10-27 surface coverage continuation: early checkpoint

State: inspection/design; no provider source edits yet. Stable90-test baseline is preserved. New authorized files are _geometry.py, geometry_export.py, geometry_import.py, new _surface_trims.py, new tests/test_surface_interchange.py and docs.

Concrete finding: Ruled and explicit sampled-Coons already produce exact piecewise-bilinear native support grids, but have no boundary pcurves. Their natural boundaries are explicit 3D polylines on grid borders; a native affine/piecewise-affine pcurve can be attached without projection/fitting. Source Straight/LineRange boundary endpoints and intermediate grid points must match exact stored-coordinate geometry. Shared edges retain their existing native identity and 3D curve. Reversed edge traversal is represented by chart direction, not welding. Coons' actual algebraic tensor border, not merely its supplied array endpoints, is authoritative when corner tolerance admitted a mismatch.

First integrated deliverable: new _surface_trims.py enumerates native bilinear-grid border charts, verifies each source natural boundary segment algebraically, attaches matching pcurves and integrates both families. Tests will use actual core STEP/IGES/BREP readback, independent analytical surface points at1e-12m, reversed loops/edges, units and atomic refusal/cancellation. Arbitrary interior trims remain a typed refusal until an exact chart construction is established.

Elliptic extrusion finding: current support converts the full source ellipse before applying u_range, so owner angular ranges do not map affinely into the rational native knot chart. Exact coverage needs a restricted effective-angle rational profile, coherent native 3D and pcurve parameters, and explicit reparameterization. Tensor extrusion avoids normalizing an oblique extrusion vector. Binary coefficient representability must be checked; some oblique/ranged definitions genuinely cannot store exact translated rational poles. Elliptic subset follows the first tested piecewise-bilinear deliverable; no implicit fit/projection is planned.

Acceptance gates/resource bounds unchanged. No new owner API request yet; public stored boundary/directrix data suffices for the first deliverable. Full native tests have not been rerun before edits.

## 2026-10-27 surface implementation checkpoint (supersedes initial design)

Changed source: new _surface_trims.py; integration in _geometry.py and geometry_export.py; approved narrow _native.py IGES formatting fix. New tests/test_surface_interchange.py. No backend/_xde/_trim_bounds/owner edits.

Current focused suite: **47 passed** in surface-expanded04,4.328s process wall. This includes Ruled+explicit Coons natural boundaries and elliptic extrusion through real STEP/IGES/BREP, alternating reversed stored edges, manually reversed loops, PUBLIC reverse_face for all3families and all3formats, source-mm -> metre checks with native3D/PCurve parameter-domain consistency, reversed angular/axial ranges, oblique profile basis and leaning extrusion direction, analytical geometry1e-12m, analytical derivative normals1e-12, ordered cyclic vertex coordinates1e-12m, original identity/nonmutation, atomic interior/unrepresentable refusals, mid-chart cancellation, and IGES serialization failure/cancellation restoring units.

Natural grid PCs now locate dyadic split-edge endpoints inside border cells exactly, not only stored grid poles; collinear intermediate grid cells retain piecewise-affine native charts. Elliptic support uses effective u_range angular interval, a rational quadratic native chart and tensor extrusion; source angle u and CAD rational u differ and are transported explicitly. Direct stored border poles/weights (not VIso evaluation) establish exact matching with source native profile coefficients. Exact translated-pole/coherent-chart gates remain strict. Unsupported angular bases/periodic effective intervals/unrepresentable coefficients/interior trims typed-refuse.

Preserved failures: surface-grid01 invalid test fixture corners=(); surface-ellipse01 exposed actual IGES nine-digit coefficient truncation and unnecessary VIso rounding; surface-ellipse03 access violation using incomplete IGES base protocol; iges-precision02 exposed absent first-operation registry initialization. After the3-failure checkpoint, parent approved one discriminating continuation: controller Init_s before guarded unit snapshot under existing global/messenger lock, complete FileProtocol and object-local17-significant-digit FloatWriter. Fresh-process iges-fresh-approved01 passed1test at2.016s, preserving1e-12 target. No geometric precision/tolerance mode changed. surface-expanded01 used generic finite-difference normal fallback and compared ellipse angular u with rational u; corrected to public analytic derivatives and explicit chart transport. surface-expanded02 compared unnormalized m² area-vector error against a metre threshold; current test compares normalized orientation and ordered vertex coordinates at unchanged1e-12m. Those failures remain on disk; no source geometry tolerance was widened.

Remaining before stable handoff: one multi-resolution Coons/collinear-grid path check, the existing shared-different-support limitation demonstrated without broadening scope if practical, full provider suite, final docs/matrix/source hashes. About half the60-call budget remains; final12calls reserved for checks/handoff. Known owner representation blocker: importing native shared edges on DIFFERENT NURBS supports needs exact shared-support/pcurve evidence; current CurveOnSurface.also_on is unsupported. Export retains shared CAD edge identity, but this combination is not claimed as an editable roundtrip. Same-value support improvement is explicitly the parent's next separate milestone, not started here.

## 2026-10-27 exact natural surface milestone: STABLE FOR REVIEW

Code freeze now applies to _geometry.py, geometry_export.py, _surface_trims.py and the approved _native.py IGES delta. Subsequent separately authorized work will touch geometry_import.py/tests only. No owner/backend/_xde/_trim_bounds changes in this surface milestone.

Final focused surface suite: **51 passed**, surface-expanded05,4.828s process wall. Final full provider command taskvenv `python -m pytest -q --tb=short`, cwd C:/Github/ANYfileio-occt with core/geometry/provider source PYTHONPATH: **141 passed**, **8.828s process wall**, evidence `C:/ANYworkspaceWork/anyfileio-geometry-20261027/surface-full01/`. Cleanup receipt verifies zero remaining owned processes. No baseline run was repeated before edits; final full run includes the original90 and51 new surface cases.

Supported/refused matrix:
- RuledSurface: exact natural Straight/retained-LineRange border paths on the polynomial bilinear grid. Interior dyadic split points are located algebraically; collinear paths can cross multiple cells with exactly representable pcurve knots. Arbitrary interior trims/ambiguous chart paths refuse.
- Explicit sampled Coons: same exact natural grid route using the authoritative exact tensor net. Different dyadic boundary resolutions (3 vs5samples) round-trip all3formats. Algebraically unrepresentable tensor/chart coefficients refuse. The actual tensor border is used when source corner tolerance did not imply exact array equality.
- Elliptic ExtrudedSurface: nonperiodic effective angular interval from source u_range, rational conic tensor with exactly stored axial-range translations; EllipticArc profiles and Straight generators on admitted boundaries. Original/reversed angular and axial ranges, reversed stored edges, public reverse_face, oblique profile basis and leaning extrusion direction tested. Exact native profile coefficients must equal direct stored support-border coefficients; no VIso rounding/projection/fitting/reparameterization guess. Periodic/full-turn, mismatched bases/subarcs or unrepresentable translated poles remain typed refusals.
- Parameter transport: grid charts retain native stored border stations. Ellipse native rational q differs from owner angular u away from endpoints/midpoint; documented explicit conic-chart inverse used by analytical tests. Native pcurve domains are retained. Source-mm -> metre whole-shape scaling is tested with native PC/3D domain and midpoint consistency for all3families.
- Topology/orientation: original/manual loop and PUBLIC reverse_face variants, alternating reversed stored curves, surface normals from analytical derivatives and cyclic ordered vertex coordinates validated. Coordinate acceptance remains1e-12m; unit-normal orientation acceptance1e-12. No hidden fitting/healing/capping/welding. Holes/interior cuts outside natural-boundary admission refuse atomically.
- Shared differing supports: actual source owner2Ruled faces sharing2edges exports2faces/10edges/9vertices, demonstrating source CAD identity preserved. Editable reread correctly refuses geometry.trim.shared_support_unsupported because distinct NURBS support evidence/owner also_on is not available. No full shared-different-support success claimed. Same/value-equal support importer is the NEXT authorized separate slice.

IGES numerical fix uses object-local17-significant-digit FloatWriter with a complete controller FileProtocol and initializes registry before guarded units under the existing reentrant backend/message lock. It changes neither model precision nor geometry tolerances. Fresh standalone IGES analytical test, actual effective format, success/failure/cancellation unit restoration all pass. Earlier truncated-output evidence and native crash remain preserved. The incomplete base protocol must not be used.

SHA256 source snapshot:
- _geometry.py:637FBDA575BDFF363153EA6496E7BDAC5840281AC7F821A4D3CEA9A5AC88241C
- geometry_export.py:656345D58070EFD887D15842479320B3AA217871A9DE2678FFD5E861607C3657
- _surface_trims.py:D3CC7C8385ED86B8A72F5F688F3644EAAF1987A009BE2D149C5A01E1DFBA27BB
- _native.py:7D7B406625CE57FCA86C496EE7E8B631F6B267D7A0EA9DFC5661C8916B2C0E64
- tests/test_surface_interchange.py:EB058CF4EF16A33E95789FD6B86B2DE48979AC3E6A88995DDDF01C4F91065020

Review: parent independent review active; worker verification is not final acceptance. No installed-wheel rebuild, Git delivery, qualification, performance claim, release or publication by this worker.

## 2026-10-27 same-support and transport slice: frozen handoff

State: verified against the assigned same/value-equal NURBS support subset and known transport repairs; independent final review remains parent-owned. No next graph or Ruled reconstruction implementation has started. Production code is held while that review runs.

Final full command: task venv `python -m pytest -q --tb=short`, cwd C:/Github/ANYfileio-occt, with core/geometry/provider source PYTHONPATH and actual registered metadata. **167 passed**, **11.141 s process wall**. Evidence: `C:/ANYworkspaceWork/anyfileio-geometry-20261027/shared-full02/`. Focused shared-support suite: **25 passed**, **4.125 s process wall**, shared-transport02. Cleanup receipts verify zero owned processes remaining.

Implemented:
- Every shared native NURBS edge gathers all incident pcurves in FORWARD edge parameters. Supports must be value-equal; normalized knots, controls, weights and retained domains must be exactly equal. Lossless binary coefficient transport is checked with rational arithmetic. One owner CurveOnSurface and one owner edge are reused in every incident loop; coedge orientation remains explicit. No sampling, fitting or coordinate welding establishes sharing.
- Shared BREP/IGES/STEP fixtures cover original/value-equal distinct supports, public shared-edge reversal, nondefault output units and ranged native chart domains. Expected topology is exactly 2 faces, 7 edges, 6 vertices. Equal-looking but different degree-elevated or geometrically changed pcurve definitions refuse, as does cancellation during incidence gathering. Independent coincident patches remain 2/8/8.
- Strict shared admission is intentionally scoped to two or more incident NURBS faces. The existing single-face extraction/chart transport was restored unchanged after the first broad application rejected previously admitted numerical native domains. Shared-full01 preserves that regression evidence (23 failures,143 passes); no owner tolerance was relaxed to repair it.
- STEP AsIs had duplicated unowned face-boundary topology: both STEPControl and XCAF read the old fixture as 2 shells,2 faces,8 edges,8 vertices, with zero shared native TShapes. Evidence shared-step-probe01. Explicit declared sheets preserved topology. The adopted minimal transport fix groups only original-edge-connected unowned faces into valid OPEN native carrier shells, without sewing, flipping, capping or inferring source structural sheets. Carrier diagnostics state that distinction. All original unowned shared-support fixtures now pass STEP too.
- Exact native emissions in all formats are reread before publication and checked for material counts and shell loss/closed-carrier changes. This is a minimum post-file count gate, NOT a claim of a complete oriented graph proof. Existing explicit approximation graph/certificate gates remain unchanged. The complete exact graph gate with independent work budget is the next parent-scoped milestone.

Corrected prior false coverage:
The old free-curve STEP fixture wrote an unowned Arc/Spline/NURBS set sharing two endpoints plus one independent CAD point. Actual native counts changed from E3/V3 to E3/V7, with zero wires both before/after: this was genuine vertex-identity loss, not harmless wire carrier grouping. Evidence free-curves-probe01. The new exact gate correctly refuses it atomically. Parent adopted a BREP family fixture plus a dedicated existing-destination-preserved STEP refusal regression; no gate was weakened. BREP asserts three native edges and three native vertices, shared endpoint incidence across all three curves, and retention of the independent CAD point. Owner reconstruction adds one Arc construction control, intentionally distinct from the coincident independent CAD point; source CAD topology counts and generated owner construction points are not conflated.

Changed in this slice: geometry_import.py, approved geometry_export.py transport/count gate, new tests/test_shared_supports.py, the specifically authorized free-curve fixture delta in tests/test_native_geometry.py, and documentation. Frozen surface conversion and IGES formatting files remain unchanged from the prior milestone.

SHA256:
- geometry_import.py: 7A99CA01F62BDB03CB7A010FD6C5F607B8D6ED196C483C93A3A005CD85B85F7C
- geometry_export.py: E14FCB3036D9BC760A8127734E399B1F004C2A6136A9A6D9DE0E54729763FDF5
- _surface_trims.py: D3CC7C8385ED86B8A72F5F688F3644EAAF1987A009BE2D149C5A01E1DFBA27BB
- _native.py: 7D7B406625CE57FCA86C496EE7E8B631F6B267D7A0EA9DFC5661C8916B2C0E64
- tests/test_shared_supports.py: E0160A64A40AF14F9F177C637D3A6BC535E984316C67DB3FF4D530F1FF770216
- tests/test_native_geometry.py: E6B996E94DA064A07FA1A7823FB36BCB32B77D9AA43BA0194280312162C5DA9F

Limits retained: differing-support shared NURBS reconstruction, periodic/seam sharing, nonrepresentable chart transport, arbitrary natural-family interior trims and unowned free-curve STEP wireframe transport are not claimed as successful. Material count equality alone does not prove graph identity; robust complete exact graph validation is reserved for the next reviewed slice. No source changes in other repositories, Git integration, installed-wheel acceptance, qualification, release or publication by this worker.

## Complete topology witness milestone: early design checkpoint

Read next-topology-worker-brief.txt and review-exact-graphgate-design.txt. The additionally referenced exact-topology-next-contract.txt is absent at its stated evidence path; parent notified. No production edits yet. Existing accepted167-source/172-installed artifacts remain frozen.

Implementation direction: new _topology.py will extract native identity-plus-location entities and EVERY direct use/orientation into bounded graph records, preserving compound/group structure by default. Ordered face outer/hole cycles, free wires, edge endpoints, shell memberships/closedness, isolated vertices and repeated uses will be explicit. A deterministic bounded refinement/backtracking matcher will accept one independently verified complete bijection, allowing coincident independent automorphisms. Physical attributes only anchor/prune candidate correspondence; they never weld nodes. Extraction, candidates, cyclic canonicalization, refinement, search and verification consume max_topology_work with cancellation checkpoints. Existing curve/trim bounds remain independent.

Concrete interface boundary needing parent adoption: exported STEP product scenes are not recoverable from bare native.read_shape's compound alone. Geometry export knows source part compounds and its synthetic root; XCAF _xde.read already exposes target product/occurrence definitions and placements, but automatic STEP root/unowned products are additional transport containers beyond the adopted open-shell exception. Meaningful part products must be distinguished from those precise source-generated wrappers; arbitrary compounds/products cannot simply be flattened. Proposed API consumes explicit source group/root roles from geometry_export and the existing target XCAF scene, or typed-refuses unsupported scene proof. No _xde edit proposed yet. Native extraction/matcher can proceed with conservative container preservation while that contract is resolved.

A separate correspondence detail needs an explicit geometry-anchor policy: physical point proposals must preserve world embedding under serialization/unit rounding while allowing exact coincident twins. Existing greedy nearest/tie-refusal is inadequate. Proposed bounded candidate construction uses exact rational stored affine placement/unit coordinates with parent-adopted candidate pruning policy, followed by full incidence proof and explicit edge reversal. This is not a geometric fidelity certificate.

Acceptance and resource limits retained:50 focused calls with15 reserved for checks/handoff; no numerical campaign, source/owner tolerances unchanged. No Ruled reconstruction or naked STEP wireframe repair in this milestone.


## Full graph witness continuation, 2026-10-27

Partial implementation, not accepted: new `_topology.py` extracts placed native identities, repeated uses, explicit edge directions, ordered wire chains/cycles, outer/hole loops, shells/solids/compound memberships. Bounded exact-color refinement and iterative constrained search admit coincident automorphisms; independent complete multiedge verification checks the witness. Rational physical-coordinate nearest proposals precede orientation refinement to prevent material reversal. All matching uses the separate max_topology_work option. Actual-file graph verification now precedes publication for exact and approximate paths; fitted trim certification receives the graph edge/direction correspondence and retains its independent actual-curve/pcurve box proof.

Checks: topology-extractor02 7 passed (1.421s wall). topology-integration02 32 passed/1 failed (4.828s); remaining XCAF product membership location-datum binding. Three failed scene executions retained; affected probe stopped pending concrete adopted continuation. New IsPartner plus exact stored affine equality repair coded, not yet checked. topology-adversarial02 73 passed/9 failed (7.625s): all11 new graph cases pass; remaining source tests include known scene binding, BREP product proof restriction (removed unnecessary refusal), previously unguarded STEP approximate wireframe transport loss requiring discrimination, and legacy trim error-message expectations. No tolerance changes. Evidence folders under C:/ANYworkspaceWork/anyfileio-geometry-20261027.

Remaining: validate the changed scene binding, add actual-file tamper/atomicity/budget tests, discriminate free polyline STEP transport, preserve/adapt compatibility diagnostics, run combined focused/full gates after parallel Ruled owner freeze, review and handoff hashes. IGES declared product boundaries remain unsupported; closed/seam edge direction now fails typed rather than guessing. Full material proof does not establish geometric fidelity or recover historical IDs.


## Graph checkpoint after integration, 2026-10-27 00:20 UTC

**Implemented, partially verified; final acceptance blocked by raw IGES coordinate-unit interface.** Frozen graph/bridge candidate hashes: `C:/ANYworkspaceWork/anyfileio-geometry-20261027/topology-checkpoint-hashes.json`. No `_native`, `_xde`, core or owner edits in this slice.

Actual commands (all task-supervised, source PYTHONPATH, exact commands in each command.json):
- `python -m pytest tests/test_shared_supports.py tests/test_topology_interchange.py tests/test_native_geometry.py -q --tb=short`: **111 passed**, topology-focused03, **9.235s process wall**, clean owned-process cleanup.
- After bounded preallocation/rootplacement bookkeeping and two added tests: `python -m pytest tests/test_topology_interchange.py tests/test_shared_supports.py tests/test_native_geometry.py tests/test_surface_interchange.py -q --tb=short`: **157 passed / 7 failed**, topology-final-focused01, **14.344s process wall**, clean cleanup. All seven failures are nonmetre IGES natural-grid/ellipse coordinate proposals; no scientific tolerance changed.
- Single discriminating `topology-grid-probe.py`: topology-grid01 **1.625s** (expected refusal). Both graphs58nodes, identical color counts; source coordinates0..2m, raw IGES cm reader returned numeric0..2 alreadymetres, while effective-unit ratio cm=.01 incorrectly produces proposal0...02m. The public raw_coordinates contract in `_native.read_shape` needs a concrete unit-setting repair; parent notified. No third blind retry.
- `topology-freebranch-probe.py`: topology-freebranch01 **1.406s**, actual prior unsupported STEP wireframe loss **E32/V33 -> E32/V64**. Saved raw actual STEP and source BREP in evidence root; existing bounded success fixture now BREP, STEP has atomic typed-refusal regression.

XCAF binding repair verified: exact retained IsPartner TShape plus exact12stored affine coefficient equality, no coordinate-based identity. Each product ORIENTED USE has its own node, preserving per-group repeated multiplicity. Ambiguous multiple placed native identity candidates refuse conservatively, never pickfirst. Sourceparts STEP product names, identity placements, flat hierarchy, full grouped material uses verified. BREP full compound/use graph preserves boundaries, explicit product-name loss diagnostic. IGES declared parts refuse. Unknown/non-FORWARD/REVERSED orientations, branched/incomplete wires and unproved closed/seam edge parameter direction refuse.

Graph acceptance remains separate from geometry bounds: minimum rational world-distance candidates are proposals only, all exact ties retained; complete injective graph witness proves topology up to relabeling. Fitted trims use this witness and unchanged actual source/3D/pcurve enclosure. Work budget covers extraction, adjacency, sorting comparisons, candidates and search/backtracking. No claim of universal fast graph isomorphism. Isolated vertex motion needs a separate geometric fidelity proof.

Review: parent independent graph review not yet run. Full combined suite pending parallel Ruled slice freeze and raw IGES interface repair; no installed-wheel rebuild in this worker slice. Previous failed evidence and accepted wheels preserved.


### Adopted narrow raw-IGES reader repair checkpoint

Parent authorized `_native.py` reader-only delta: per-model ChangeGlobalSection().SetCascadeUnit BEFORE TransferRoots, verify actual CascadeUnit and UnitValue; preserve existing guard and fail closed for unknown-header overrides. Implemented. Fresh topology-iges-raw01 failed9tests before transfer because UnitValue was incorrectly assumed metres independent of cascade; discriminating iges-header01 (0.812s) showed underCascade1: CM UnitValue10, MM1, INCH25.4. Correct interpretation is source_millimetres/CascadeUnit. New getter validation checks this exact expected ratio.

Fresh topology-iges-raw02: **6 failure/cancel guard checks passed, 3 analytical success checks failed**, 1.718s wall. Getter takes requested rawcm10/mm1/in25.4 correctly, but actual raw file coordinates imply **0.002m for a2m input**, ALL3units. This exposes a second writer unit issue, previously masked by reader conversion: writer model CASCADE state must be inspected/set before AddShape, not merely its process-global guard. No writer edit yet (outside reader-only adopted delta); parent notified concrete proposal. No third blind retry. Raw physical-coordinate oracle remains1e-12m. Reader repair changes known-header behavior to actual physical interpretation; current candidate must NOT ship until matching writer repair and full regression gates.

Continuation code/evidence hashes: topology-native-checkpoint-hashes.json. New tests are9parameterized fresh rawcm/mm/in success/failure/cancel cases; six effective-setting/restoration paths pass, three true analytical file checks intentionally expose unresolved production writer fault. Independent review/full combined/installed checks remain pending.


## Frozen graph/native candidate handoff, 2026-10-27 00:28 UTC

**Verified against focused assigned criteria; independent review and final combined/installed acceptance pending.** This supersedes the raw-IGES blocker above. Parent adopted writer model SetCascadeUnit(1000) BEFORE AddShape, plus reader per-model units before TransferRoots. Both getters and UnitValue(source_mm/CascadeUnit) verified; existing guarded settings, locking and local17digit formatting retained. Unknown/unproved header overrides and inconsistent named/numeric units refuse typed.

Final command: `C:/ANYworkspaceWork/anyfileio-geometry-20261026/venv/Scripts/python.exe -m pytest tests/test_topology_interchange.py tests/test_shared_supports.py tests/test_native_geometry.py tests/test_surface_interchange.py -q --tb=short`, cwd C:/Github/ANYfileio-occt, PYTHONPATH C:/Github/ANYfileIO/src;C:/Github/ANYgeometry/src;C:/Github/ANYfileio-occt/src. **175 passed**, **14.047s process wall**, topology-freeze01/result.json; owned cleanup verified zero active processes. Exact supervisor command retained in command.json, complete diagnostics in stdout.jsonl/stdout.stderr.txt.

Independent physical IGES writer proof: iges-independent01 **9 passed**,1.531s. Parses literal IGESGeom_Line.EndPoint BEFORE Transfer and validates numeric UnitFlag/name: source2m emitscm200,mm2000,in78.740...; exact rational declared physical factor times literal coordinate agrees2m within1e-12m. Tests also verify actual writerCascade1000 and readerCascade10/1/25.4, normalized reads, success/failure/cancellation global restoration. Final175test run includes these proof cases plus two real byte-edited inconsistent/unknown header refusals. Prior mutual reader/writer unit-error evidence remains preserved, never reused as acceptance.

Owned changes: new _topology.py/test_topology_interchange.py, geometry_export.py, narrow _trim_bounds.py verifier integration, adopted narrow _native.py IGES unit repair, minimal authorized old freebranch test change in test_native_geometry.py, README/status. No owner/core/_xde edits. Parallel Ruled import changes belong to separate owner and are not included in this worker's focused acceptance claim. Final source hashes in topology-final-hashes.json.

Supported proof: distinct/repeated material uses, automorphisms of independent coincident copies, edge endpoints/directions, ordered open wires and closed cycles, face outer versus holes, shell/solid/compound use graphs, isolated vertices, admitted flat named STEP part uses and BREP compound boundaries. Extra open transport shells are enumerated under the one bounded work budget; no declared shell can disappear/reassign. Matching uses exact rational world-coordinate minimum proposals among unoriented compatible roles (all ties kept), then full graph bijection and independent multiedge verification. This proves topology up to relabeling, not historical ID recovery or geometric accuracy.

Precise current limits: unsupported native INTERNAL/EXTERNAL uses; closed/seam edge parameter direction without separate admitted proof; branched/incomplete wire order; ambiguous retainedTShape plus exactplacement product binding; IGES declared product boundaries; known naked STEP connected wireframe vertex splitting. These refuse, never heal/weld/project. Product root/flat organization/identity placements are writer-specific; no arbitrary scene preservation claim. Isolated point movement and exact geometric fidelity remain separate proof scope.

Not run by this worker: full combined suite including parallel Ruled producer/import slice (parent schedules after both freezes), new wheels/installed verification, independent review. Source graphs/native files now frozen pending primary review.

## CAD product reference geometry affiliation — 2026-10-27

The demonstrated single free-line STEP -> editable -> STEP failure is repaired
through public groups and versioned Part provenance, not inferred Members.
Import captures only native loose edges and isolated points while occurrence
membership is known. Each binding records the destination model UUID and Part
ID, exact group members and source document/occurrence/prototype identity.
Export validates the binding and emits those references inside that Part's CAD
compound. Carrier geometry is unchanged; later unowned additions remain outside.
Malformed, stale, copied-to-another-context or structurally reassigned bindings
typed-refuse. Native persistence retains affiliation. No owner/core or reference
ID recipe change is included. STEP graph/scene validation remains mandatory.

Focused checks and source/frozen-wheel deltas are recorded in
`C:/ANYworkspaceWork/anyfileio-geometry-20261027/cad-reference-geometry-task.txt`.
Initial connected6 cases and expanded15 cases passed; final affected regression
results and frozen hashes are recorded there at handoff. Independent review,
combined source and installed acceptance remain primary-owned. General model
copy/topology replacement needs explicit remapping, currently refused.

Review follow-up: native scene wires containing both face-owned and outside
edges now typed-refuse before owner conversion, preventing an uncovered edge
from silently moving to unowned output. One real STEP specimen was attempted;
its writer emits a geometric curve set, so preservation of the original mixed
native wire is not claimed. A native BREP leaf injected at the live scene
boundary verifies the preconversion refusal. Added multi-Part mixed-product
membership and shared-corner reference tests; the latter uses the unchanged
actual-file topology gate and preserves an existing destination on refusal.
Focused receipts `reference-geometry-mixed04` and
`reference-geometry-membership05` supplement, rather than replace, the previous
frozen candidate's combined/installed evidence. Public owner group ordering was
verified as numeric `(kind,id)` sorting; no ordering repair was needed.

Final accounting guard: entirely free wires must have unique direct native edge
uses and a complete ordered walk matching both the material identity set and
use cardinality before owner conversion. Native BREP scene fixtures demonstrate
branched/disconnected/repeated-use refusal and a complete two-edge chain's
successful ordered Member import. That chain's re-export retains the existing
typed Member parent-range limit and preserves the destination. Four focused
cases passed in `reference-geometry-free-wire07`; the initial extra export
expectation failure is preserved in `reference-geometry-free-wire06`. No wire
reordering, healing, range-policy change or new STEP transport probe is included.

## Actual serialized export references — 2026-10-27

Editable CAD reports now bind to the actual written document's canonical
`cad-import-v1` ID, published as `output_document_id`. The source model/revision
remains independent report evidence. A rich optional topology correspondence
retains every material entity and product-group witness; the old raw-file tuple
and default edge-map API remain compatible for approximation consumers.
One topology Work ledger covers raw validation, canonical document proof and
charged identity lookup. Public live `read_cad(..., retain_source=False)` supplies
the exact manifest/tables; digest checks bind it before and after reconciliation,
and every exit closes the live document. No canonical refs are invented.

STEP Parts map to actual occurrences; Sheet/Member carriers map to shell/wire.
BREP Parts project the exact witness-matched compound's carrier closure, with
owner-bound container-addressability loss and existing name loss. Material
references resolve in the actual manifest and editable import mappings where
that import supports the entity kind. BREP editable structural reconstruction
is not newly promised. Different source handles aliasing one material prototype
reference refuse; no coordinate-only attribution or historical-ID claim is made.
Every source V/E/F must map or refuse, including coordinate-equal replacement
vertices whose native identities were lost.

Exact native IsSame identity has priority. The only wrapper exception (root
adopted after measured backend wrapper mismatch) requires retained TShape,
literal coefficient-identity of every nonzero-power datum in both chains, and
one unique canonical ref. Cached-identity cancelling chains and ambiguous tables
refuse. Frozen literal guards and all geometry algorithms/tolerances are unchanged.

Focused evidence: `output-references-final10` passed150 affected tests in15.359s;
the subsequent source-completeness and actual-record-reuse refinements passed all
23 new tests in `output-references-records12`,7.141s. Both cleanup checks verified
zero processes. Three old bounded-polyline positives need explicit root-adopted
5m topology work for the added complete document proof; defaults, deviation,
segments and depth are unchanged. Prior1m exhaustion and strict-IsSame-only
failed evidence remain preserved. Details/hashes/source delta are in
`C:/ANYworkspaceWork/anyfileio-geometry-20261027/output-reference-task.txt`.
Primary independent review, combined source and installed acceptance are pending;
prior broad counts remain bound to their original frozen snapshots.

## BREP native file-record association repair — staged candidate

The incidence-only identity candidate above was invalidated by independent
two-Arc compound-reordering evidence: geometrically different automorphic curves
were assigned to the wrong report refs. Its passing counts are preserved, not
reused as acceptance of that attribution. The new staged implementation supports
BREP editable export through native ShapeSet record provenance; STEP/IGES editable
export explicitly refuses until its retained transfer lineage is established.
Assets, imports and native persistence retain their separate existing routes.

An immutable whole-native-definition/use snapshot precedes writer preparation.
Two positive unit transforms retain public ModifiedShape entity history;
orientation is validated as explicit pinned native uses. Separate native table
and root streams avoid the observed BytesIO continuation failure. Opaque native
entity records link source TShapes to the actual literal read, rather than
guessing TopExp ranks or geometric matches. Payload bytes/digest and decoded
literal raw/canonical geometry expectations are frozen BEFORE I/O. Established
15-digit native trim-domain encoding is retained. Actual raw geometry, every
retained face pcurve, and normalization are checked against those expectations.
Unproved seam representations refuse. The same retained read/history supplies
free/fitted certificates and canonical refs; no independent endpoint/canonical
pairing remains. Existing bounds functions and literal-location guards are frozen.

Focused final evidence: `identity/association-final09`89passed33.406s (includes
work/literal guards and five unchanged asset-unit cases), followed by
`association-ordinary10`1passed1.812s proving ordinary BRepTools reads the new
file and its centimetre arcs represent +/-1m. Earlier `association-clipped07`
30passed52.969s validates pinned raw/canonical import history at that snapshot.
Two obsolete phase-spy failures and all earlier failed capability checks remain
preserved. Details/source hashes/remaining staged limits are in the external
association implementation handoff. Independent review and primary combined/
installed acceptance are pending; no blanket format restoration is claimed.

### Member whole-edge station admission (2026-10-27)

Removed the export guard that mistook Member station placement for an edge-local
trim. Whole current edge geometry, orientation, ordered wire assembly, native
record association and atomic output gates are unchanged. The write report now
explicitly records loss of persistent Member stations and edge-use history.
Native JSON keeps exact station semantics. Ordinary BREP import explicitly
reports structural grouping loss; automatic Member reconstruction is open.

Focused verification: `identity/member-station/final03`, 38 passed, process wall
5.719 seconds, exit 0, cleanup 0. Tests cover unequal chains, public reverse and
split operations, retained/reversed NURBS domains, source/output units, shared
and coincident identities, actual refs, native persistence, cancellation, late
failure and a native scene carrier cycle. Initial 12 failed assertions assumed
ordinary BREP reconstructs Members; those failures remain preserved. The adopted
export-only scope instead tests its existing explicit grouping-loss contract.
Primary full/installed checks and independent review are pending for this slice.

### Independent BREP physical precision guard (2026-10-27)

The actual ShapeSet probe confirmed successful old exports with vertex drift
0.0042724609375 m at a 1e12 m offset against an owner local residual 1e-8 m.
Those inputs now refuse atomically. A source-native snapshot before transforms
and encoding is compared to the same pinned actual raw and canonical records,
using exact physical unit ratios and half the smaller owner length/surface
residual as a physical reserve. Full pole/frame/domain data and all incident
pcurves participate; endpoint samples and native UVBounds do not establish
acceptance. The existing record/payload checks and optional literal approximation
certificates remain separate and unchanged. Work uses the existing shared ledger.

Two exact surface combinations are intentionally precision-unverified: Coons
with different boundary resolutions, and the millimetre panel emitted in inches.
Their actual pcurve enclosures leave the active NURBS surface basis. They now
have explicit atomic-refusal regressions; previous full positive oracles and
failed receipts are preserved under `identity/precision-repair`. No general
surface extrapolation or new tolerance was adopted. Bare mm lines/points to
inches retain an independent literal SI oracle. Other limitations are documented
in README. Primary installed/integration checks and independent review pending.

Primary verification subsequently completed on providerwheel
2ad63f633917d3c9fe52a11c765737ff4d455c1ae0a1e902c92dd7f5e627354f:
493 source and 512 installed tests pass, no failures or warnings. Claude subscription
mathematical review found no bound counterexample; evaluator scope is now gated
to the verified loaded bundle for out-of-domain affine continuation, and stronger
test discriminators address the review. Exact evidence and remaining scope:
`C:/ANYworkspaceWork/anyfileio-geometry-20261027/identity/review-final/verification-index.json`.
The two surface refusals above remain; no general extrapolation/full parity,
compiled-owner, Linux/GitHub CI or publication claim follows.
