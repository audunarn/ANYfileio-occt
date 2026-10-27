"""Post-serialization conservative certificates for explicitly fitted NURBS trims.

A union-box diameter bounds both Hausdorff directions and normalized-parameter
error for the source curve, actual file 3D curve and actual file trim curve.
No sampled distances or native fitter tolerance establish acceptance.
"""
from __future__ import annotations
from fractions import Fraction as Q
from dataclasses import dataclass
import math
import numpy as np
from anyfileio.geometry import GeometryApproximation,GeometryDiagnostic
from . import _native as native
from ._geometry import refuse,outward_norm_squared
from ._units import _CANONICAL_SCALES

METHOD='native pcurve fit + serialized source/3D/trim union-box enclosure'

@dataclass
class _Work:
    limit:int
    used:int=0
    def charge(self,amount=1):
        self.used+=amount
        if self.used>self.limit:
            refuse('Serialized trim proof exceeded max_segments work budget','geometry.approximation.budget')

def _stored(value):
    try: result=float(value)
    except OverflowError: refuse('Exact file chart coefficient overflows','geometry.bounds.precision')
    if not math.isfinite(result) or Q(result)!=value:
        refuse('Exact file chart coefficient is not representable','geometry.exact.coefficient_unrepresentable')
    return result

def _knots(curve):
    return tuple(curve.Knot(i) for i in range(1,curve.NbKnots()+1) for _ in range(curve.Multiplicity(i)))

def _identity_location_coefficients(location):
    """Require literal identity factors, not a rounded cached composite.

    Distinct nonidentity datum transforms can round to an identity composite.
    General exact affine transport is unavailable, even if factors cancel.
    """
    while not location.IsIdentity():
        if location.FirstPower()!=0:
            transform=location.FirstDatum().Transformation()
            if any(transform.Value(row,column)!=float(row==column)
                   for row in (1,2,3) for column in (1,2,3,4)):
                return False
        location=location.NextLocation()
    return True


def _native_curve(edge,reverse=False):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.GeomAbs import GeomAbs_BSplineCurve,GeomAbs_BezierCurve
    from anygeometry.nurbs import NurbsCurve
    if not _identity_location_coefficients(edge.Location()):
        refuse('Located fitted curve needs exact coefficient transport','geometry.bounds.location_unsupported')
    representation=TopLoc_Location()
    BRep_Tool.Curve_s(edge,representation,0.,0.)
    if not _identity_location_coefficients(representation):
        refuse('Curve representation location needs exact coefficient transport','geometry.bounds.location_unsupported')
    # The adaptor can apply representation locations and round poles. Only
    # identity affine coefficients may reach that conversion in a literal proof.
    c=BRepAdaptor_Curve(edge)
    if c.GetType()==GeomAbs_BSplineCurve:
        bs=c.BSpline()
        if bs.IsPeriodic(): refuse('Periodic fitted curve proof is unavailable','geometry.bounds.periodic_unsupported')
        degree,knots=bs.Degree(),_knots(bs)
    elif c.GetType()==GeomAbs_BezierCurve:
        bs=c.Bezier(); degree=bs.Degree(); knots=(0.,)*(degree+1)+(1.,)*(degree+1)
    else: refuse('Serialized fitted edge must retain a bounded NURBS/Bezier definition','geometry.bounds.curve_unsupported')
    controls=tuple((bs.Pole(i).X(),bs.Pole(i).Y(),bs.Pole(i).Z()) for i in range(1,bs.NbPoles()+1))
    weights=tuple(bs.Weight(i) for i in range(1,bs.NbPoles()+1)) if bs.IsRational() else None
    domain=(c.FirstParameter(),c.LastParameter())
    if reverse: domain=domain[::-1]
    try: return NurbsCurve(degree,knots,controls,weights,domain)
    except Exception as error: refuse(f'File curve is outside public owner bounds capability: {error}','geometry.bounds.curve_unsupported')

def _native_trim(edge,face,reverse=False):
    from OCP.BRep import BRep_Tool
    from OCP.Geom2d import Geom2d_BSplineCurve,Geom2d_BezierCurve,Geom2d_TrimmedCurve
    from OCP.TopLoc import TopLoc_Location
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    from .geometry_import import surface_from_native
    if not _identity_location_coefficients(face.Location()):
        refuse('Located fitted trim needs exact coefficient transport','geometry.bounds.location_unsupported')
    representation=TopLoc_Location()
    BRep_Tool.Surface_s(face,representation)
    if not _identity_location_coefficients(representation):
        refuse('Surface representation location needs exact coefficient transport','geometry.bounds.location_unsupported')
    try: support=surface_from_native(face)
    except Exception as error: refuse(f'File trim support cannot be bounded exactly: {error}','geometry.bounds.support_unsupported')
    from anygeometry.surfaces import Plane
    if not isinstance(support,(NurbsSurface,Plane)): refuse('Fitted trim proof requires an explicit file NURBS or planar support','geometry.bounds.support_unsupported')
    pc=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.)
    if pc is None: refuse('Serialized face lost its pcurve','geometry.trim.pcurve_missing')
    while isinstance(pc,Geom2d_TrimmedCurve): pc=pc.BasisCurve()
    if isinstance(pc,Geom2d_BSplineCurve):
        if pc.IsPeriodic(): refuse('Periodic file pcurve cannot be certified','geometry.bounds.periodic_unsupported')
        degree,knots=pc.Degree(),_knots(pc)
    elif isinstance(pc,Geom2d_BezierCurve):
        degree=pc.Degree(); knots=(0.,)*(degree+1)+(1.,)*(degree+1)
    else: refuse('Serialized pcurve must retain an explicit bounded NURBS/Bezier definition','geometry.bounds.pcurve_unsupported')
    ur,vr=(support.u_range,support.v_range) if isinstance(support,NurbsSurface) else ((0.,1.),(0.,1.))
    controls=tuple(tuple(_stored((Q(x)-Q(r[0]))/(Q(r[1])-Q(r[0]))) for x,r in zip(
        (pc.Pole(i).X(),pc.Pole(i).Y()),(ur,vr))) for i in range(1,pc.NbPoles()+1))
    weights=tuple(pc.Weight(i) for i in range(1,pc.NbPoles()+1)) if pc.IsRational() else None
    domain=BRep_Tool.Range_s(edge,face)
    if reverse: domain=domain[::-1]
    try:
        curve=NurbsCurve(degree,knots,controls,weights,domain)
        return CurveOnSurface(support,curve) if isinstance(support,NurbsSurface) else _PlaneTrim(support,curve)
    except Exception as error: refuse(f'File pcurve is outside public owner bounds capability: {error}','geometry.bounds.pcurve_unsupported')


class _PlaneTrim:
    """Full literal file pcurve lifted through the public outward plane enclosure."""
    def __init__(self,support,pcurve): self.support,self.pcurve=support,pcurve
    def bounds(self,a,b):
        from anygeometry.surface_capabilities import capabilities
        lo,hi=self.pcurve.bounds(a,b)
        box=capabilities(self.support).enclosure(tuple(zip(lo,hi)))
        return box.lower,box.upper

def _box(curve,a,b,ratio):
    values=curve.bounds(a,b)
    if len(values)==6: lower,upper=values[:3],values[3:]
    else: lower,upper=values
    if len(lower)!=3 or len(upper)!=3: refuse('Owner bounds is not a world 3D box','geometry.bounds.invalid')
    if not all(math.isfinite(float(v)) for v in (*lower,*upper)):
        refuse('Owner bounds is nonfinite','geometry.bounds.invalid')
    lo=tuple(Q(float(v))*ratio for v in lower); hi=tuple(Q(float(v))*ratio for v in upper)
    if any(a>b for a,b in zip(lo,hi)): refuse('Owner bounds is reversed','geometry.bounds.invalid')
    return lo,hi

def _certify(source,targets,source_ratio,target_ratio,options,work,cancellation):
    pending=[(0.,1.,0)]; worst=0.
    while pending:
        native.checkpoint(cancellation); work.charge(1+len(targets))
        a,b,depth=pending.pop()
        boxes=[_box(source,a,b,source_ratio)]+[_box(c,a,b,target_ratio) for c in targets]
        lo=tuple(min(box[0][i] for box in boxes) for i in range(3))
        hi=tuple(max(box[1][i] for box in boxes) for i in range(3))
        squared=sum((h-l)**2 for l,h in zip(lo,hi))
        bound=outward_norm_squared(squared,cancellation)
        if squared<=Q(options.max_deviation_m)**2 and bound<=options.max_deviation_m:
            worst=max(worst,bound)
        else:
            if depth>=options.max_depth: refuse('Serialized trim proof exceeded max_depth','geometry.approximation.budget')
            mid=(a+b)/2
            if mid==a or mid==b: refuse('Trim proof subdivision has no representable progress','geometry.bounds.precision')
            pending.extend([(mid,b,depth+1),(a,mid,depth+1)])
    return worst

def _topology_fingerprints(shape,edge_map,edge_translation,work,cancellation):
    """Oriented material boundary cycles; no coordinate/box welding participates."""
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_FORWARD,TopAbs_REVERSED,TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.BRepTools import BRepTools,BRepTools_WireExplorer
    from OCP.BRep import BRep_Tool
    faces=native.shape_map(shape,'face'); result=[]; by_id={}
    def cycle(items):
        if not items: refuse('Serialized face has an empty boundary wire','geometry.trim.topology_changed')
        return min(tuple(items[i:]+items[:i]) for i in range(len(items)))
    for fi in range(1,faces.Extent()+1):
        native.checkpoint(cancellation); work.charge()
        original=TopoDS.Face_s(faces.FindKey(fi)); reverse_face=original.Orientation()==TopAbs_REVERSED
        face=TopoDS.Face_s(original.Oriented(TopAbs_FORWARD)); outer=BRepTools.OuterWire_s(face)
        explorer=TopExp_Explorer(face,TopAbs_WIRE); outer_cycle=None; holes=[]
        while explorer.More():
            wire=TopoDS.Wire_s(explorer.Current()); walk=BRepTools_WireExplorer(wire,face); items=[]
            while walk.More():
                native.checkpoint(cancellation); work.charge()
                edge=walk.Current(); index=edge_map.FindIndex(edge)
                if index not in edge_translation: refuse('Serialized boundary edge lacks a bijective source identity','geometry.trim.topology_changed')
                source,reverse_curve=edge_translation[index]
                forward=edge.Orientation()!=TopAbs_REVERSED
                items.append((source,forward!=reverse_curve)); walk.Next()
            if reverse_face: items=[(index,not forward) for index,forward in reversed(items)]
            fingerprint=cycle(items)
            if wire.IsSame(outer): outer_cycle=fingerprint
            else: holes.append(fingerprint)
            explorer.Next()
        if outer_cycle is None: refuse('Serialized face lost its outer boundary','geometry.trim.topology_changed')
        fingerprint=(outer_cycle,tuple(sorted(holes)))
        result.append(fingerprint); by_id[fi]=fingerprint
    from OCP.TopAbs import TopAbs_FACE
    def oriented_fingerprint(current):
        fi=faces.FindIndex(current); fingerprint=by_id[fi]
        if current.Orientation()!=faces.FindKey(fi).Orientation():
            outer,holes=fingerprint
            def flipped(items): return cycle([(index,not forward) for index,forward in reversed(items)])
            fingerprint=(flipped(outer),tuple(sorted(flipped(hole) for hole in holes)))
        return fingerprint
    # Indexed maps count topology identities only. Traversal multiplicity also
    # preserves coincident duplicate components that reuse a topology identity.
    occurrences=[]; traversal=TopExp_Explorer(shape,TopAbs_FACE)
    while traversal.More():
        native.checkpoint(cancellation); work.charge()
        occurrences.append(oriented_fingerprint(traversal.Current())); traversal.Next()
    shells=native.shape_map(shape,'shell'); groups=[]
    for si in range(1,shells.Extent()+1):
        native.checkpoint(cancellation); work.charge()
        explorer=TopExp_Explorer(shells.FindKey(si),TopAbs_FACE); members=[]
        while explorer.More():
            work.charge(); members.append(oriented_fingerprint(explorer.Current())); explorer.Next()
        groups.append((tuple(sorted(members)),bool(BRep_Tool.IsClosed_s(shells.FindKey(si)))))
    return sorted(occurrences),sorted(groups)

def _verify_vertex_bijection(source,target,source_edges,target_edges,matches,work,cancellation):
    """Preserve endpoint identity, independently of coordinates and total counts."""
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_FORWARD
    from OCP.TopExp import TopExp
    source_vertices=native.shape_map(source,'vertex'); target_vertices=native.shape_map(target,'vertex')
    forward={}; inverse={}; source_incident=set(); target_incident=set()
    def endpoints(edge,index):
        edge=TopoDS.Edge_s(edge.Oriented(TopAbs_FORWARD))
        vertices=(TopExp.FirstVertex_s(edge,True),TopExp.LastVertex_s(edge,True))
        if any(v.IsNull() for v in vertices):
            refuse('An incident edge lost its endpoint vertex identity','geometry.trim.topology_changed')
        values=tuple(index.FindIndex(v) for v in vertices)
        if any(v<=0 for v in values):
            refuse('An incident edge endpoint is outside the document vertex map','geometry.trim.topology_changed')
        return values
    for si,(ti,reverse) in matches.items():
        native.checkpoint(cancellation); work.charge()
        source_edge=source_edges.FindKey(si); target_edge=target_edges.FindKey(ti)
        left=endpoints(source_edge,source_vertices); right=endpoints(target_edge,target_vertices)
        if reverse: right=right[::-1]
        for source_id,target_id in zip(left,right):
            if source_id in forward and forward[source_id]!=target_id:
                refuse('Serialized vertex correspondence split a shared source endpoint','geometry.trim.topology_changed')
            if target_id in inverse and inverse[target_id]!=source_id:
                refuse('Serialized vertex correspondence welded distinct source endpoints','geometry.trim.topology_changed')
            forward[source_id]=target_id; inverse[target_id]=source_id
        for edge,index,incident in ((source_edge,source_vertices,source_incident),(target_edge,target_vertices,target_incident)):
            vertices=native.shape_map(edge,'vertex')
            for i in range(1,vertices.Extent()+1):
                work.charge(); incident.add(index.FindIndex(vertices.FindKey(i)))
    if set(forward)!=source_incident or set(inverse)!=target_incident:
        refuse('Serialized vertex correspondence is not incident-surjective','geometry.trim.topology_changed')

def verify_fitted_trims(shape,path,fmt,unit,groups,sources,reports,options,cancellation=None,source_scale=1.,*,topology=None,work=None,association=None):
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_FORWARD,TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    if association is None:refuse('Fitted certificate lacks proved literal targets','geometry.association_unproved')
    if topology is not None and topology is not association.topology:
        refuse('Fitted certificate and report target associations differ','geometry.association_unproved')
    topology=association.topology
    output,target_ratio,matches,_=topology
    source_ratio=Q(str(source_scale))
    if work is None: work=_Work(options.max_segments)
    source_edges=native.shape_map(shape,'edge'); target_edges=native.shape_map(output,'edge')
    edge_faces={i:[] for i in range(1,target_edges.Extent()+1)}
    faces=native.shape_map(output,'face')
    for fi in range(1,faces.Extent()+1):
        face=TopoDS.Face_s(faces.FindKey(fi)); explorer=TopExp_Explorer(face,TopAbs_EDGE)
        while explorer.More():
            native.checkpoint(cancellation); work.charge()
            index=target_edges.FindIndex(explorer.Current()); edge_faces[index].append(face); explorer.Next()
    result=[]; diagnostics=[]
    for report in reports:
        source=sources[report.source]; worst=0.; edge_tolerance=Q(0)
        for si in groups[report.source]:
            ti,reverse=matches[si]; edge=TopoDS.Edge_s(target_edges.FindKey(ti).Oriented(TopAbs_FORWARD))
            tolerance=BRep_Tool.Tolerance_s(edge)
            if not math.isfinite(tolerance) or tolerance<0:
                refuse('Serialized fitted edge has an invalid CAD tolerance','geometry.bounds.invalid')
            edge_tolerance=max(edge_tolerance,Q(tolerance)*target_ratio)
            targets=[_native_curve(edge,reverse)]+[_native_trim(edge,face,reverse) for face in edge_faces[ti]]
            if len(targets)<2: refuse('Serialized fitted edge lost face incidence','geometry.trim.incidence_changed')
            worst=max(worst,_certify(source,targets,source_ratio,target_ratio,options,work,cancellation))
        result.append(GeometryApproximation(report.source,options.max_deviation_m,worst,METHOD))
        diagnostics.append(GeometryDiagnostic('geometry.native_fit.edge_tolerance',
            f'Actual serialized CAD edge tolerance {float(edge_tolerance):.17g} m; acceptance uses the separate source/3D/trim enclosure',
            (report.source,)))
    return result,diagnostics
