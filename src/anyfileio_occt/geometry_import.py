"""CAD topology to a new editable owner model; solids are never peeled."""
from __future__ import annotations
import math
import hashlib
import json
from dataclasses import replace
from fractions import Fraction as Q
import numpy as np
from anyfileio.cad import CadEntityRef
from anyfileio.geometry import GeometryReadOptions,GeometryImportReport,GeometryImportResult
from . import _native as native
from ._geometry import refuse
from .backend import document_shape,VERSION
SECTION_IMPORT_METHOD='public whole-open section reconstruction + input 3D/all-pcurve union-box enclosure'
SECTION_CLIPPED_IMPORT_METHOD='public clipped-open section-domain reconstruction + input 3D/all-pcurve union-box enclosure'

def xyz(p): return (p.X(),p.Y(),p.Z())
def expanded_knots(curve):
    return tuple(curve.Knot(i) for i in range(1,curve.NbKnots()+1) for _ in range(curve.Multiplicity(i)))


def _bounded_section(edge,incident,surfaces,face_map,endpoints,model,options,cancellation,work,*,raw_target=None):
    """Public open-domain proposals under one cooperative world-proof budget."""
    from anygeometry.errors import GeometryError
    from anygeometry.nurbs import NurbsSurface
    from anygeometry.surfaces import Plane
    from anygeometry.support_curves import PlaneNurbsCurve
    from anygeometry.plane_nurbs import plane_nurbs_section
    from anygeometry.surface_capabilities import capabilities
    from anygeometry.tolerance import feature_extent
    from OCP.TopoDS import TopoDS
    from ._trim_bounds import _native_curve,_native_trim,_certify
    if options.fidelity!='approximate' or options.max_deviation_m is None:
        refuse('Implicit plane/NURBS reconstruction requires bounded approximation','geometry.exact.composition_unavailable')
    try:
        from anygeometry.curve_parameter_matching import bounded_section_work,match_curve_parameter_regions,CurveParameterMatchError
    except ImportError:
        refuse('Plane/NURBS reconstruction requires the public cooperative owner work capability','geometry.owner.parameter_matching_missing')
    callback_error=None
    def checked_cancellation():
        nonlocal callback_error
        try:return False if cancellation is None else cancellation()
        except BaseException as error:
            callback_error=error
            raise
    def charged_checkpoint():
        work.charge();native.checkpoint(checked_cancellation)
    def query(callback):
        native.checkpoint(checked_cancellation);work.charge()
        remaining=work.limit-work.used
        if remaining<=0:refuse('Section query exceeded max_segments','geometry.approximation.budget')
        try:
            with bounded_section_work(max_work=remaining,max_depth=options.max_depth,checkpoint=charged_checkpoint):
                return callback()
        except CurveParameterMatchError as error:
            if error is callback_error:raise
            if error.reason in ('budget_exhausted','depth_exhausted','precision_exhausted'):
                refuse(f'Public section work refused: {error.reason}','geometry.approximation.budget')
            refuse(f'Public section work is unresolved: {error.reason}','geometry.trim.parameter_inconclusive')
        except GeometryError as error:
            if error is callback_error:raise
            refuse(f'Public owner section query refused: {error}','geometry.trim.section_unsupported')
    supports=[surfaces[i] for i in incident if isinstance(surfaces[i],NurbsSurface)]
    planes=[surfaces[i] for i in incident if isinstance(surfaces[i],Plane)]
    support=supports[0];plane=planes[0]
    if any(s!=support for s in supports):refuse('Section has distinct NURBS supports','geometry.trim.shared_support_unsupported')
    coeff=capabilities(plane).implicit.coefficients;pivot=next(i for i,x in enumerate(coeff) if x)
    for p in planes:
        other=capabilities(p).implicit.coefficients
        if any(x*other[pivot]!=y*coeff[pivot] for x,y in zip(coeff,other)):
            refuse('Section has distinct planar supports','geometry.trim.support_mismatch')
    section=query(lambda:plane_nurbs_section(plane,support))
    candidates=[];masters=[];closed=[]
    fit=model.tolerance.effective_curve_fit_residual(feature_extent(np.asarray(endpoints)))
    def fits(curve):
        for end,point in enumerate(endpoints):
            lo,hi=query(lambda:curve.end_box(end))
            squared=sum(max(abs(Q(float(l))-Q(float(x))),abs(Q(float(h))-Q(float(x))))**2 for l,h,x in zip(lo,hi,point))
            if squared>Q(fit)**2:return False
        return True
    for index,path in enumerate(section.paths):
        native.checkpoint(checked_cancellation);work.charge()
        base=query(lambda:PlaneNurbsCurve.from_plane(plane,support,index))
        if path.closed:
            closed.append(base)
            continue
        masters.append(base)
        for curve in (base,base.subcurve(1.,0.)):
            work.charge()
            if fits(curve):candidates.append(curve)
    if len(candidates)>1:refuse('Multiple whole open sections match unchanged endpoints','geometry.trim.section_domain_ambiguous')
    if not candidates or closed:
        fi=next(i for i in incident if isinstance(surfaces[i],NurbsSurface))
        actual=_native_trim(edge,TopoDS.Face_s(face_map.FindKey(fi)))
        targets=[query(lambda:actual.pcurve.bounds(t,t)) for t in (0.,1.)]
        def locate(base,target):
            before=work.used
            result=query(lambda:match_curve_parameter_regions(base,target,2.**-40,
                max_boxes=work.limit-work.used,max_depth=options.max_depth,param_resolution=2.**-44))
            if result.work_used!=work.used-before-1:
                refuse('Owner parameter matcher returned inconsistent work accounting','geometry.owner.parameter_matching_invalid')
            return result
        for base in closed:
            first=locate(base,targets[0])
            if not first.regions:continue # Only proved-empty excludes an alternative.
            second=locate(base,targets[1])
            if second.regions:
                refuse('A closed section path possibly matches both endpoints','geometry.trim.closed_section_unsupported')
        if not candidates:
            domains=[]
            for base in masters:
                first=locate(base,targets[0])
                if not first.regions:continue
                second=locate(base,targets[1])
                if not second.regions:continue
                if len(first.regions)!=1 or len(second.regions)!=1:
                    refuse('Multiple possible endpoint parameter regions remain','geometry.trim.section_domain_ambiguous')
                parameters=[r.regions[0].lower+(r.regions[0].upper-r.regions[0].lower)/2 for r in (first,second)]
                if parameters[0]==parameters[1]:refuse('Endpoint regions do not resolve an open domain','geometry.trim.parameter_inconclusive')
                work.charge();domains.append(base.subcurve(*parameters))
            if not domains:refuse('No open section matches the endpoint UV boxes','geometry.trim.section_domain_no_match')
            if len(domains)!=1:refuse('Multiple possible public section domains remain','geometry.trim.section_domain_ambiguous')
            curve=domains[0]
            if not fits(curve):refuse('Proposed domain does not meet unchanged world endpoints','geometry.trim.parameter_inconclusive')
            candidates.append(curve)
    if raw_target is None:refuse('Literal BREP correspondence is required','geometry.bounds.raw_source_unavailable')
    raw_edge,raw_faces,ratio,reverse=raw_target
    targets=[_native_curve(raw_edge,reverse)]+[_native_trim(raw_edge,face,reverse) for face in raw_faces]
    bound=query(lambda:_certify(candidates[0],targets,Q(1),ratio,options,work,checked_cancellation))
    return candidates[0],bound


def _stored_chart(value):
    try: result=float(value)
    except OverflowError: refuse('Exact imported chart coefficient overflows','geometry.exact.coefficient_unrepresentable')
    if not math.isfinite(result) or Q(result)!=value:
        refuse('Exact imported chart coefficient is not representable','geometry.exact.coefficient_unrepresentable')
    return result

def _native_pcurve_definition(edge,face,support):
    """Lossless stored chart definition in FORWARD native edge parameters."""
    from OCP.BRep import BRep_Tool
    from OCP.Geom2d import Geom2d_BSplineCurve,Geom2d_BezierCurve,Geom2d_TrimmedCurve,Geom2d_Line
    from anygeometry.nurbs import NurbsCurve
    curve=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.)
    if curve is None: refuse('NURBS face has no exact pcurve','geometry.trim.pcurve_missing')
    domain=BRep_Tool.Range_s(edge,face)
    if not all(math.isfinite(t) for t in domain) or domain[0]>=domain[1]:
        refuse('Native trim domain is not a finite directed interval','geometry.trim.pcurve_domain_unsupported')
    while isinstance(curve,Geom2d_TrimmedCurve): curve=curve.BasisCurve()
    if isinstance(curve,Geom2d_BSplineCurve):
        if curve.IsPeriodic(): refuse('Periodic shared pcurve needs explicit seam transport','geometry.trim.periodic_unsupported')
        degree,knots=curve.Degree(),expanded_knots(curve)
        points=[(Q(curve.Pole(i).X()),Q(curve.Pole(i).Y())) for i in range(1,curve.NbPoles()+1)]
        weights=tuple(curve.Weight(i) for i in range(1,curve.NbPoles()+1)) if curve.IsRational() else None
    elif isinstance(curve,Geom2d_BezierCurve):
        degree=curve.Degree(); knots=(0.,)*(degree+1)+(1.,)*(degree+1)
        points=[(Q(curve.Pole(i).X()),Q(curve.Pole(i).Y())) for i in range(1,curve.NbPoles()+1)]
        weights=tuple(curve.Weight(i) for i in range(1,curve.NbPoles()+1)) if curve.IsRational() else None
    elif isinstance(curve,Geom2d_Line):
        line=curve.Lin2d(); origin=line.Location(); direction=line.Direction()
        points=[(Q(origin.X())+Q(t)*Q(direction.X()),Q(origin.Y())+Q(t)*Q(direction.Y())) for t in domain]
        degree=1; knots=(domain[0],domain[0],domain[1],domain[1]); weights=None
    else:
        refuse('Native trim needs a lossless B-spline/Bezier/line chart definition','geometry.trim.pcurve_representation_unsupported')
    ranges=(support.u_range,support.v_range)
    controls=tuple(tuple(_stored_chart((value-Q(r[0]))/(Q(r[1])-Q(r[0]))) for value,r in zip(point,ranges)) for point in points)
    try: return NurbsCurve(degree,knots,controls,weights,domain)
    except Exception as error: refuse(f'Imported exact chart is outside owner capability: {error}','geometry.trim.pcurve_representation_unsupported')

def _ruled_refuse(reason):
    refuse('Exact shared ruled reconstruction unavailable: '+reason,
        'geometry.trim.shared_support_unsupported')


def _identity_coefficients(location):
    # A nonempty TopLoc container may carry an exactly identity transformation.
    # Admit that definition, not a merely small/near-identity placement.
    transform=location.Transformation()
    return all(transform.Value(i,j)==(1. if i==j else 0.) for i in range(1,4) for j in range(1,5))


def _prove_ruled_border(edge,face,support,cancellation):
    """Exact finite-line / retained-PC / natural-border proof, without mutation.

    PC knots and surface-knot crossings partition the path into affine world
    pieces. Exact collinearity and strictly increasing finite-line parameters
    prove equality of the entire oriented point set, not sampled proximity.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.BRep import BRep_Tool
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_FORWARD
    from OCP.TopLoc import TopLoc_Location
    from ._surface_trims import _linear_parameter
    edge=TopoDS.Edge_s(edge.Oriented(TopAbs_FORWARD))
    location=TopLoc_Location(); BRep_Tool.Curve_s(edge,location,0.,0.)
    if not _identity_coefficients(location): _ruled_refuse('located border needs exact coefficient transport')
    curve=BRepAdaptor_Curve(edge)
    if curve.GetType()!=GeomAbs_Line: _ruled_refuse('every border must retain a native Line definition')
    first,last=curve.FirstParameter(),curve.LastParameter()
    if not all(math.isfinite(t) for t in (first,last)) or first>=last:
        _ruled_refuse('finite directed native line range required')
    line=curve.Line(); o=tuple(map(Q,xyz(line.Location()))); d=tuple(map(Q,xyz(line.Direction())))
    ends=tuple(tuple(x+Q(t)*v for x,v in zip(o,d)) for t in (first,last))
    vertices=(TopExp.FirstVertex_s(edge,True),TopExp.LastVertex_s(edge,True))
    if any(v.IsNull() for v in vertices): _ruled_refuse('native line lost an endpoint identity')
    proxies=tuple(tuple(map(Q,xyz(BRep_Tool.Pnt_s(v)))) for v in vertices)
    if ends!=proxies: _ruled_refuse('native line range and topology endpoints differ in stored coefficients')
    pc=_native_pcurve_definition(edge,face,support)
    if pc.degree!=1 or (pc.weights is not None and len(set(pc.weights))!=1):
        _ruled_refuse('border pcurve must be polynomial piecewise affine')
    p0,p1=map(Q,pc.domain)
    interior=[Q(k) for k in pc.knots if p0<Q(k)<p1]
    if len(interior)!=len(set(interior)): _ruled_refuse('border pcurve has a discontinuous knot')
    stations=sorted({Q(0),Q(1)}|{(k-p0)/(p1-p0) for k in interior})
    points=[pc.exact_point(t) for t in stations]
    if any(not 0<=x<=1 for point in points for x in point): _ruled_refuse('border leaves the normalized chart')
    borders=[(axis,value) for axis in (0,1) for value in (Q(0),Q(1))
             if all(point[axis]==value for point in points)]
    if len(borders)!=1: _ruled_refuse('pcurve does not identify one natural chart border')
    fixed,_=borders[0]; union=set(stations)
    if fixed==1:
        u0,u1=map(Q,support.u_range)
        knots={(Q(k)-u0)/(u1-u0) for k in support.knots_u if u0<Q(k)<u1}
        for a,b,left,right in zip(stations,stations[1:],points,points[1:]):
            native.checkpoint(cancellation)
            if left[0]==right[0]: continue
            for knot in knots:
                fraction=(knot-left[0])/(right[0]-left[0])
                if 0<fraction<1: union.add(a+fraction*(b-a))
    parameters=[]
    for t in sorted(union):
        native.checkpoint(cancellation)
        parameter=_linear_parameter(support.exact_point(*pc.exact_point(t)),*ends)
        if parameter is None: _ruled_refuse('pcurve lift differs from the finite native line')
        parameters.append(parameter)
    if parameters[0]!=0 or parameters[-1]!=1 or any(b<=a for a,b in zip(parameters,parameters[1:])):
        _ruled_refuse('pcurve does not cover the oriented native line exactly once')


def _shared_ruled_support(face,support,cancellation):
    """Exact same-chart polynomial ruled reconstruction only for shared import."""
    from anygeometry.surfaces import RuledSurface
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRep import BRep_Tool
    location=TopLoc_Location(); BRep_Tool.Surface_s(face,location)
    if not _identity_coefficients(location): _ruled_refuse('located support needs exact coefficient transport')
    if support.degree_u!=1 or support.degree_v!=1 or any(len(row)!=2 for row in support.controls):
        _ruled_refuse('degree (1,1) with exactly two V pole rows required')
    if support.weights is not None and len({w for row in support.weights for w in row})!=1:
        _ruled_refuse('nonconstant rational weights are not a polynomial ruled definition')
    count=len(support.controls); ku=tuple(map(Q,support.knots_u)); kv=tuple(map(Q,support.knots_v))
    us=tuple(sorted(set(ku))); vs=tuple(sorted(set(kv)))
    if (len(us)!=count or len(vs)!=2 or ku!=(us[0],)+us+(us[-1],)
            or kv!=(vs[0],vs[0],vs[1],vs[1])):
        _ruled_refuse('clamped endpoints and simple U knots required')
    if tuple(map(Q,support.u_range))!=(us[0],us[-1]) or tuple(map(Q,support.v_range))!=vs:
        _ruled_refuse('full native chart ranges required')
    if any((k-us[0])/(us[-1]-us[0])!=Q(i,count-1) for i,k in enumerate(us)):
        _ruled_refuse('exact uniform normalized U stations required')
    explorer=TopExp_Explorer(face,TopAbs_EDGE); seen=set(); index=TopTools_IndexedMapOfShape()
    while explorer.More():
        native.checkpoint(cancellation); edge=TopoDS.Edge_s(explorer.Current()); identifier=index.Add(edge)
        if identifier in seen: _ruled_refuse('repeated border use requires a seam contract')
        seen.add(identifier); _prove_ruled_border(edge,face,support,cancellation); explorer.Next()
    if not seen: _ruled_refuse('surface has no retained borders')
    return RuledSurface(tuple(row[0] for row in support.controls),tuple(row[1] for row in support.controls))


def _reconstruct_shared_ruled_faces(surfaces,edge_faces,face_map,cancellation):
    """Attempt only shared-face components containing an unequal support pair."""
    from OCP.TopoDS import TopoDS
    seeds=set(); adjacent={}
    for incident in edge_faces.values():
        if len(incident)<2: continue
        for fi in incident: adjacent.setdefault(fi,set()).update(set(incident)-{fi})
        if any(surfaces[fi]!=surfaces[incident[0]] for fi in incident): seeds.update(incident)
    selected=set(); pending=list(seeds)
    while pending:
        native.checkpoint(cancellation); fi=pending.pop()
        if fi in selected: continue
        selected.add(fi); pending.extend(adjacent[fi]-selected)
    replacements={fi:_shared_ruled_support(TopoDS.Face_s(face_map.FindKey(fi)),surfaces[fi],cancellation)
                  for fi in sorted(selected)}
    surfaces.update(replacements)
    return {ei:[fi for fi in incident if fi not in replacements] for ei,incident in edge_faces.items()
            if any(fi not in replacements for fi in incident)}


def nurbs_from_native(curve,first,last):
    from anygeometry.nurbs import NurbsCurve
    copy=curve.Copy()
    if copy.IsPeriodic(): copy.SetNotPeriodic()
    copy.Segment(first,last)
    return NurbsCurve(copy.Degree(),expanded_knots(copy),
        tuple(xyz(copy.Pole(i)) for i in range(1,copy.NbPoles()+1)),
        tuple(copy.Weight(i) for i in range(1,copy.NbPoles()+1)) if copy.IsRational() else None)

def surface_from_native(face):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane,GeomAbs_Cylinder,GeomAbs_Cone,GeomAbs_BSplineSurface,GeomAbs_BezierSurface
    from anygeometry.surfaces import Plane,Cylinder,Cone
    from anygeometry.nurbs import NurbsSurface
    adaptor=BRepAdaptor_Surface(face,False); kind=adaptor.GetType()
    if kind==GeomAbs_Plane:
        s=adaptor.Plane(); pos=s.Position()
        return Plane(xyz(pos.Location()),xyz(pos.XDirection()),xyz(pos.YDirection()))
    if kind==GeomAbs_Cylinder:
        s=adaptor.Cylinder(); pos=s.Position()
        from OCP.BRepTools import BRepTools
        u0,u1,v0,v1=BRepTools.UVBounds_s(face)
        origin=np.asarray(xyz(pos.Location()))+v0*np.asarray(xyz(pos.Direction()))
        return Cylinder(origin,xyz(pos.Direction()),xyz(pos.XDirection()),s.Radius(),v1-v0,u0,u1-u0)
    if kind==GeomAbs_Cone:
        s=adaptor.Cone(); pos=s.Position(); angle=s.SemiAngle()
        # Match native cone v's axial/radial scale with ANYgeometry's axial chart.
        from OCP.BRepTools import BRepTools
        u0,u1,v0,v1=BRepTools.UVBounds_s(face)
        origin=np.asarray(xyz(pos.Location()))+v0*math.cos(angle)*np.asarray(xyz(pos.Direction()))
        return Cone(origin,xyz(pos.Direction()),xyz(pos.XDirection()),
            s.RefRadius()+v0*math.sin(angle),s.RefRadius()+v1*math.sin(angle),
            (v1-v0)*math.cos(angle),u0,u1-u0)
    if kind in (GeomAbs_BSplineSurface,GeomAbs_BezierSurface):
        from OCP.GeomConvert import GeomConvert
        s=adaptor.BSpline() if kind==GeomAbs_BSplineSurface else GeomConvert.SurfaceToBSplineSurface_s(adaptor.Bezier())
        if s.IsUPeriodic() or s.IsVPeriodic(): refuse('Periodic NURBS support needs exact chart seam decomposition','geometry.surface.periodic_unsupported')
        ku=tuple(s.UKnot(i) for i in range(1,s.NbUKnots()+1) for _ in range(s.UMultiplicity(i)))
        kv=tuple(s.VKnot(i) for i in range(1,s.NbVKnots()+1) for _ in range(s.VMultiplicity(i)))
        controls=tuple(tuple(xyz(s.Pole(i,j)) for j in range(1,s.NbVPoles()+1)) for i in range(1,s.NbUPoles()+1))
        weights=tuple(tuple(s.Weight(i,j) for j in range(1,s.NbVPoles()+1)) for i in range(1,s.NbUPoles()+1)) if s.IsURational() or s.IsVRational() else None
        return NurbsSurface(s.UDegree(),s.VDegree(),ku,kv,controls,weights)
    from OCP.GeomAbs import GeomAbs_SurfaceOfExtrusion
    if kind==GeomAbs_SurfaceOfExtrusion:
        from OCP.BRep import BRep_Tool
        from OCP.BRepTools import BRepTools
        from OCP.Geom import Geom_SurfaceOfLinearExtrusion,Geom_BSplineCurve,Geom_BezierCurve,Geom_TrimmedCurve,Geom_Ellipse,Geom_Circle
        from OCP.GeomConvert import GeomConvert
        from anygeometry.surfaces import ExtrudedSurface
        from anygeometry.extrusions import EllipseDirectrix
        native_surface=BRep_Tool.Surface_s(face)
        if not isinstance(native_surface,Geom_SurfaceOfLinearExtrusion): refuse('Located extrusion support could not be materialized exactly')
        basis=native_surface.BasisCurve()
        while isinstance(basis,Geom_TrimmedCurve): basis=basis.BasisCurve()
        u0,u1,v0,v1=BRepTools.UVBounds_s(face)
        direction=np.asarray(xyz(native_surface.Direction()))
        if isinstance(basis,Geom_BezierCurve): basis=GeomConvert.CurveToBSplineCurve_s(basis)
        if isinstance(basis,Geom_BSplineCurve):
            if basis.IsPeriodic(): refuse('Periodic extrusion basis requires exact seam decomposition')
            # A rational tensor product preserves the original native chart exactly.
            poles=[np.asarray(xyz(basis.Pole(i))) for i in range(1,basis.NbPoles()+1)]
            weights=tuple((basis.Weight(i),basis.Weight(i)) for i in range(1,basis.NbPoles()+1)) if basis.IsRational() else None
            return NurbsSurface(basis.Degree(),1,expanded_knots(basis),(v0,v0,v1,v1),
                tuple((tuple(p+direction*v0),tuple(p+direction*v1)) for p in poles),weights)
        if isinstance(basis,(Geom_Ellipse,Geom_Circle)):
            position=basis.Position()
            major=basis.MajorRadius() if isinstance(basis,Geom_Ellipse) else basis.Radius()
            minor=basis.MinorRadius() if isinstance(basis,Geom_Ellipse) else basis.Radius()
            profile=EllipseDirectrix(tuple(np.asarray(xyz(position.Location()))+direction*v0),
                tuple(np.asarray(xyz(position.XDirection()))*major),tuple(np.asarray(xyz(position.YDirection()))*minor),u0,u1-u0)
            return ExtrudedSurface(profile,tuple(direction*(v1-v0)))
        refuse('Native extrusion basis is not a supported exact public profile')
    refuse(f'Unsupported native surface type {kind}','geometry.surface.unsupported')

def import_geometry(document,*,options:GeometryReadOptions,cancellation=None):
    state=document._backend_state_for('occt')
    instances=getattr(state,'instances',None)
    if instances is None:
        return _import_shape(document,options=options,cancellation=cancellation)
    if native.shape_map(document_shape(document),'solid').Extent():
        refuse('Editable geometry import rejects solids atomically','geometry.solid.unsupported')
    from anygeometry import GeometryModel
    from anygeometry.entities import OrientedEdge
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_FORWARD,TopAbs_REVERSED,TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.BRepTools import BRepTools_WireExplorer
    model=GeometryModel(); mapping={}; m=document.manifest
    occurrence_by_id={o.id:o for o in m.occurrences}
    for oid,shape,refs in instances:
        native.checkpoint(cancellation)
        # A loose wire partly reusing a face boundary has neither an admitted
        # physical Member nor a lossless reference-wire carrier in the owner.
        # Reject before conversion, rather than silently orphaning its extras.
        edge_map=native.shape_map(shape,'edge'); face_edges=set()
        face_map=native.shape_map(shape,'face')
        for fi in range(1,face_map.Extent()+1):
            native.checkpoint(cancellation)
            boundary=native.shape_map(face_map.FindKey(fi),'edge')
            face_edges.update(edge_map.FindIndex(boundary.FindKey(ei)) for ei in range(1,boundary.Extent()+1))
        wire_map=native.shape_map(shape,'wire')
        for wi in range(1,wire_map.Extent()+1):
            native.checkpoint(cancellation)
            boundary=native.shape_map(wire_map.FindKey(wi),'edge')
            material={edge_map.FindIndex(boundary.FindKey(ei)) for ei in range(1,boundary.Extent()+1)}
            if material&face_edges and material-face_edges:
                refuse('A wire mixes face boundary and outside reference edges; product affiliation cannot preserve this carrier',
                       'geometry.reference_geometry.mixed_wire_unsupported')
            if not material&face_edges:
                from OCP.TopoDS import TopoDS_Iterator
                from OCP.TopAbs import TopAbs_EDGE
                wire=TopoDS.Wire_s(wire_map.FindKey(wi))
                children=TopoDS_Iterator(wire); use_ids=set(); use_count=0
                while children.More():
                    native.checkpoint(cancellation)
                    edge=children.Value(); index=edge_map.FindIndex(edge)
                    if edge.ShapeType()!=TopAbs_EDGE or not index or index in use_ids:
                        refuse('Free wire has unsupported or repeated edge uses','geometry.reference_geometry.wire_unsupported')
                    use_ids.add(index); use_count+=1; children.Next()
                walked=set(); walk_count=0; walk=BRepTools_WireExplorer(wire)
                while walk.More():
                    native.checkpoint(cancellation)
                    index=edge_map.FindIndex(walk.Current())
                    if not index or index in walked:
                        refuse('Free wire walk repeats or loses edge identity','geometry.reference_geometry.wire_unsupported')
                    walked.add(index); walk_count+=1; walk.Next()
                if use_ids!=material or walked!=material or walk_count!=use_count:
                    refuse('Free wire walk does not cover its complete native material','geometry.reference_geometry.wire_unsupported')
        result=_import_shape(document,options=options,cancellation=cancellation,
            shape_override=shape,reference_maps=refs)
        inserted=model.insert_model(result.geometry)
        local={cad:tuple(inserted.handle_map[h] for h in handles) for cad,handles in result.report.cad_to_geometry.items()}
        for cad,handles in local.items(): mapping[cad]=mapping.get(cad,())+handles
        occurrence=occurrence_by_id[oid]
        # Capture only actual leaf reference geometry, not inferred structure.
        # An edge inside any native face/wire already has a carrier below.
        edge_map=native.shape_map(shape,'edge'); vertex_map=native.shape_map(shape,'vertex')
        carrier_edges=set(); incident_vertices=set()
        for kind in ('face','wire'):
            carriers=native.shape_map(shape,kind)
            for ci in range(1,carriers.Extent()+1):
                native.checkpoint(cancellation)
                material=native.shape_map(carriers.FindKey(ci),'edge')
                carrier_edges.update(edge_map.FindIndex(material.FindKey(ei)) for ei in range(1,material.Extent()+1))
        for ei in range(1,edge_map.Extent()+1):
            native.checkpoint(cancellation)
            material=native.shape_map(edge_map.FindKey(ei),'vertex')
            incident_vertices.update(vertex_map.FindIndex(material.FindKey(vi)) for vi in range(1,material.Extent()+1))
        reference_handles=[]
        for kind,indices in (('edge',set(range(1,edge_map.Extent()+1))-carrier_edges),
                             ('vertex',set(range(1,vertex_map.Extent()+1))-incident_vertices)):
            for index in sorted(indices):
                native.checkpoint(cancellation)
                reference_handles.extend(local[refs[kind][index]])
        from ._reference_geometry import capture
        # This fresh destination has only the Parts created by this loop. Use
        # public state to bind metadata before immutable Part creation, and
        # verify the allocator result; never publish a guessed Part binding.
        expected_part_id=len(model.parts)+1
        affiliation=capture(model,(model.entity_ref(h.kind,h.id) for h in reference_handles),
            part_id=expected_part_id,document_id=m.document_id,occurrence_id=oid,prototype_id=occurrence.prototype_id)
        part=model.add_part(name=occurrence.name,metadata={'cad_occurrence_id':oid,
            'cad_parent_occurrence_id':occurrence.parent_id,'cad_prototype_id':occurrence.prototype_id,**affiliation})
        if part!=expected_part_id:
            refuse('Import Part allocation cannot preserve reference affiliation','geometry.reference_geometry.invalid')
        # Explicit native shells become sheets. Loose source faces remain singleton
        # sheets in their declared product; no adjacency or structural joint is inferred.
        face_map=native.shape_map(shape,'face'); shell_map=native.shape_map(shape,'shell'); used_faces=set()
        for si in range(1,shell_map.Extent()+1):
            explorer=TopExp_Explorer(shell_map.FindKey(si),TopAbs_FACE); face_ids=[]; orientations=[]
            while explorer.More():
                face=explorer.Current(); fi=face_map.FindIndex(face)
                face_ids.extend(h.id for h in local[refs['face'][fi]])
                orientations.append(-1 if face.Orientation()==TopAbs_REVERSED else 1)
                used_faces.add(fi); explorer.Next()
            sheet=model.add_sheet(face_ids,part_id=part,orientations=orientations)
            mapping[refs['shell'][si]]=mapping.get(refs['shell'][si],())+(model.handle('sheet',sheet),)
        for fi in range(1,face_map.Extent()+1):
            if fi not in used_faces:
                model.add_sheet([h.id for h in local[refs['face'][fi]]],part_id=part)
        wires=native.shape_map(shape,'wire'); edge_map=native.shape_map(shape,'edge')
        face_edges={edge_map.FindIndex(native.shape_map(face_map.FindKey(fi),'edge').FindKey(ei))
            for fi in range(1,face_map.Extent()+1) for ei in range(1,native.shape_map(face_map.FindKey(fi),'edge').Extent()+1)}
        for wi in range(1,wires.Extent()+1):
            wire=TopoDS.Wire_s(wires.FindKey(wi)); chain=[]; walk=BRepTools_WireExplorer(wire); face_trim=False
            while walk.More():
                edge=walk.Current(); ei=edge_map.FindIndex(edge)
                if ei in face_edges: face_trim=True; break
                forward=edge.Orientation()!=TopAbs_REVERSED; handles=local[refs['edge'][ei]]
                chain.extend(OrientedEdge(h.id,forward) for h in (handles if forward else reversed(handles)))
                walk.Next()
            if chain and not face_trim:
                member=model.add_member(chain,part_id=part)
                mapping[refs['wire'][wi]]=mapping.get(refs['wire'][wi],())+(model.handle('member',member),)
        mapping[CadEntityRef(m.document_id,'occurrence',oid)]=(model.handle('part',part),)+tuple(inserted.handle_map.values())
        prototype=CadEntityRef(m.document_id,'prototype',occurrence.prototype_id)
        mapping[prototype]=mapping.get(prototype,())+(model.handle('part',part),)
    from anygeometry.serialization import to_dict
    to_dict(model,certified=options.validation_mode=='certified')
    return GeometryImportResult(model,GeometryImportReport(m.source_format,m.source_sha256,model.model_id,model.revision,
        m.source_length_unit,cad_to_geometry=mapping,metadata_losses=('assembly parent links retained as part metadata; nested structural parts unavailable',
        'CAD colours and layers','Imported shell-to-sheet grouping describes CAD carriers, not evidence of original structural intent'),backend_version=VERSION,binding_version=m.binding_version,occt_version=m.occt_version))

def _import_shape(document,*,options:GeometryReadOptions,cancellation=None,shape_override=None,reference_maps=None):
    if options.coordinate_space!='model_local': refuse('External coordinate transformation is not defined','geometry.external_transform_undefined')
    shape=document_shape(document) if shape_override is None else shape_override; m=document.manifest
    native.checkpoint(cancellation)
    if native.shape_map(shape,'solid').Extent(): refuse('Editable geometry import rejects solids atomically','geometry.solid.unsupported')
    from anygeometry import GeometryModel
    from anygeometry.entities import OrientedEdge
    from anygeometry.serialization import to_dict,from_dict
    from anygeometry.nurbs import NurbsSurface,CurveOnSurface,NurbsCurve
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_FORWARD,TopAbs_REVERSED
    from OCP.TopExp import TopExp
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools,BRepTools_WireExplorer
    from OCP.GeomAbs import GeomAbs_Line,GeomAbs_Circle,GeomAbs_Ellipse,GeomAbs_BSplineCurve,GeomAbs_BezierCurve
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_WIRE,TopAbs_EDGE
    model=GeometryModel(); maps={k:native.shape_map(shape,k) for k in ('vertex','edge','face')}
    vm={}; em={}; mapping={}; surfaces={}; approximations=[]
    cref=lambda kind,i:reference_maps[kind][i] if reference_maps else CadEntityRef(m.document_id,kind,i)
    # Work only on a new owner model, so every refusal is atomic to callers.
    with model.transaction():
        for i in range(1,maps['vertex'].Extent()+1):
            native.checkpoint(cancellation)
            v=TopoDS.Vertex_s(maps['vertex'].FindKey(i)); vm[i]=model.add_point(*xyz(BRep_Tool.Pnt_s(v)))
            mapping[cref('vertex',i)]=(model.entity_ref('vertex',vm[i]),)
        for i in range(1,maps['face'].Extent()+1):
            surfaces[i]=surface_from_native(TopoDS.Face_s(maps['face'].FindKey(i)))
        edge_faces={}; all_edge_faces={}
        for fi,support in surfaces.items():
            face=TopoDS.Face_s(maps['face'].FindKey(fi)); explorer=TopExp_Explorer(face,TopAbs_EDGE)
            while explorer.More():
                ei=maps['edge'].FindIndex(explorer.Current())
                incident=all_edge_faces.setdefault(ei,[])
                if fi in incident: refuse('Repeated pcurve use on one face requires explicit seam transport','geometry.trim.seam_unsupported')
                incident.append(fi)
                if isinstance(support,NurbsSurface): edge_faces.setdefault(ei,[]).append(fi)
                explorer.Next()
        from anygeometry.surfaces import Plane
        section_edges={ei for ei,incident in all_edge_faces.items() if ei in edge_faces
            and any(isinstance(surfaces[fi],Plane) for fi in incident)
            and BRepAdaptor_Curve(TopoDS.Edge_s(maps['edge'].FindKey(ei))).GetType() in (GeomAbs_BSplineCurve,GeomAbs_BezierCurve)}
        if section_edges and m.source_format!='brep': refuse('Bounded plane/NURBS reconstruction is admitted only for BREP','geometry.trim.format_unsupported')
        from ._trim_bounds import _Work
        section_work=_Work(options.max_segments)
        raw_targets={}
        if section_edges:
            from .backend import document_raw_brep,document_brep_association
            from ._topology import compare,Work
            from ._units import _CANONICAL_SCALES
            raw,units=document_raw_brep(document)
            if units.effective_unit not in _CANONICAL_SCALES:
                refuse('Literal BREP physical units are unavailable','geometry.bounds.raw_source_unavailable')
            ratio=Q(str(_CANONICAL_SCALES[units.effective_unit]))
            _,normalization=document_brep_association(document)
            correspondence=compare(raw,shape,ratio,Q(1),Work(options.max_topology_work,cancellation),entity_map=normalization.entity)
            inverse={target:(source,reverse) for source,(target,reverse) in correspondence.items()}
            raw_edges=native.shape_map(raw,'edge'); raw_faces=native.shape_map(raw,'face')
            incidence={}
            for fi in range(1,raw_faces.Extent()+1):
                face=TopoDS.Face_s(raw_faces.FindKey(fi)); walk=TopExp_Explorer(face,TopAbs_EDGE)
                while walk.More():
                    native.checkpoint(cancellation); section_work.charge()
                    index=raw_edges.FindIndex(walk.Current()); incidence.setdefault(index,[]).append(face); walk.Next()
            for ei in section_edges:
                if ei not in inverse: refuse('No literal source edge correspondence','geometry.topology.changed')
                ri,reverse=inverse[ei]
                raw_targets[ei]=(TopoDS.Edge_s(raw_edges.FindKey(ri).Oriented(TopAbs_FORWARD)),incidence.get(ri,[]),ratio,reverse)
        edge_faces=_reconstruct_shared_ruled_faces(surfaces,edge_faces,maps['face'],cancellation)
        edge_pcurves={}
        for ei,incident in edge_faces.items():
            native.checkpoint(cancellation)
            if ei in section_edges: continue
            if len(incident)==1: continue
            canonical=surfaces[incident[0]]
            if any(surfaces[fi]!=canonical for fi in incident):
                refuse('Shared NURBS trim requires owner also_on shared-boundary proof','geometry.trim.shared_support_unsupported')
            edge=TopoDS.Edge_s(maps['edge'].FindKey(ei).Oriented(TopAbs_FORWARD)); definition=None
            for fi in incident:
                native.checkpoint(cancellation)
                face=TopoDS.Face_s(maps['face'].FindKey(fi).Oriented(TopAbs_FORWARD))
                current=_native_pcurve_definition(edge,face,surfaces[fi])
                if definition is not None and current!=definition:
                    refuse('Shared edge has unequal exact incident pcurve definitions','geometry.trim.shared_pcurve_unsupported')
                definition=current
            edge_pcurves[ei]=(canonical,definition)
        for i in range(1,maps['edge'].Extent()+1):
            native.checkpoint(cancellation)
            edge=TopoDS.Edge_s(maps['edge'].FindKey(i).Oriented(TopAbs_FORWARD))
            if BRep_Tool.Degenerated_s(edge): refuse('Degenerate CAD edge needs explicit pole topology handling','geometry.edge.degenerate')
            a=TopExp.FirstVertex_s(edge,True); b=TopExp.LastVertex_s(edge,True)
            if a.IsNull() or b.IsNull(): refuse('Native edge has no endpoint vertices','geometry.edge.invalid')
            start,end=vm[maps['vertex'].FindIndex(a)],vm[maps['vertex'].FindIndex(b)]
            c=BRepAdaptor_Curve(edge); first,last=c.FirstParameter(),c.LastParameter(); kind=c.GetType()
            actual=np.asarray([xyz(c.Value(first)),xyz(c.Value(last))])
            topology=np.asarray([model.vertices[start].position,model.vertices[end].position])
            from anygeometry.tolerance import feature_extent
            scale=feature_extent(np.vstack((actual,topology)))
            limit=model.tolerance.effective_curve_fit_residual(scale)
            if any(math.dist(p,q)>limit for p,q in zip(actual,topology)):
                refuse('Native curve endpoints disagree with topology beyond owner curve-fit policy','geometry.edge.endpoint_mismatch')
            closed=start==end
            splits=4 if closed else 1
            parameters=np.linspace(first,last,splits+1); ids=[]; prev=start
            for j in range(splits):
                lo,hi=float(parameters[j]),float(parameters[j+1])
                final=end if j==splits-1 else model.add_point(*xyz(c.Value(hi)))
                if i in section_edges:
                    if closed: refuse('Closed section paths require a public domain proof','geometry.trim.section_domain_unsupported')
                    curve,bound=_bounded_section(edge,all_edge_faces[i],surfaces,maps['face'],topology,model,options,cancellation,section_work,raw_target=raw_targets[i])
                    try: eid=model.add_curve(prev,final,curve)
                    except Exception as error: refuse(f'Owner section endpoint/chart validation refused: {error}','geometry.trim.invalid')
                    from anyfileio.geometry import GeometryApproximation
                    method=SECTION_IMPORT_METHOD if curve.domain in ((0.,1.),(1.,0.)) else SECTION_CLIPPED_IMPORT_METHOD
                    approximations.append(GeometryApproximation(model.entity_ref('edge',eid),options.max_deviation_m,bound,method))
                elif i in edge_faces:
                    if i not in edge_pcurves:
                        # Preserve the established single-face extraction/chart
                        # transport. New lossless equality admission is scoped
                        # specifically to edges shared by multiple faces.
                        from OCP.Geom2dConvert import Geom2dConvert
                        from OCP.Geom2d import Geom2d_TrimmedCurve
                        fi=edge_faces[i][0]; support=surfaces[fi]; face=TopoDS.Face_s(maps['face'].FindKey(fi))
                        native_pc=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.)
                        if native_pc is None: refuse('NURBS face has no exact pcurve','geometry.trim.pcurve_missing')
                        native_pc=Geom2dConvert.CurveToBSplineCurve_s(Geom2d_TrimmedCurve(native_pc,lo,hi))
                        if native_pc.IsPeriodic(): native_pc.SetNotPeriodic()
                        ur,vr=support.u_range,support.v_range
                        controls=tuple(((native_pc.Pole(k).X()-ur[0])/(ur[1]-ur[0]),(native_pc.Pole(k).Y()-vr[0])/(vr[1]-vr[0])) for k in range(1,native_pc.NbPoles()+1))
                        pc=NurbsCurve(native_pc.Degree(),expanded_knots(native_pc),controls,
                            tuple(native_pc.Weight(k) for k in range(1,native_pc.NbPoles()+1)) if native_pc.IsRational() else None)
                    else:
                        support,pc=edge_pcurves[i]
                    if i in edge_pcurves and splits>1:
                        p0,p1=map(Q,pc.domain)
                        domain=tuple(_stored_chart(p0+(Q(t)-Q(first))*(p1-p0)/(Q(last)-Q(first))) for t in (lo,hi))
                        pc=replace(pc,domain=domain)
                    curve=CurveOnSurface(support,pc)
                    try: eid=model.add_curve(prev,final,curve)
                    except Exception as error:
                        refuse(f'Imported exact pcurve disagrees with topology or owner chart policy: {error}','geometry.trim.invalid')
                elif kind==GeomAbs_Line: eid=model.add_line(prev,final)
                elif kind==GeomAbs_Circle:
                    via=model.add_point(*xyz(c.Value((lo+hi)/2)))
                    eid=model.add_arc(prev,via,final)
                elif kind==GeomAbs_Ellipse:
                    from anygeometry.exact_curves import EllipticArc
                    s=c.Ellipse(); pos=s.Position()
                    curve=EllipticArc(xyz(pos.Location()),tuple(np.asarray(xyz(pos.XDirection()))*s.MajorRadius()),
                        tuple(np.asarray(xyz(pos.YDirection()))*s.MinorRadius()),lo,hi-lo)
                    eid=model.add_curve(prev,final,curve)
                elif kind in (GeomAbs_BSplineCurve,GeomAbs_BezierCurve):
                    from OCP.GeomConvert import GeomConvert
                    geom=c.BSpline() if kind==GeomAbs_BSplineCurve else GeomConvert.CurveToBSplineCurve_s(c.Bezier())
                    eid=model.add_curve(prev,final,nurbs_from_native(geom,lo,hi))
                else: refuse(f'Unsupported native curve type {kind}','geometry.curve.unsupported')
                ids.append(eid); prev=final
            em[i]=ids; mapping[cref('edge',i)]=tuple(model.entity_ref('edge',eid) for eid in ids)
        face_loops={}
        for i,support in surfaces.items():
            native.checkpoint(cancellation)
            face=TopoDS.Face_s(maps['face'].FindKey(i).Oriented(TopAbs_FORWARD))
            outer=BRepTools.OuterWire_s(face); loops=[]
            explorer=TopExp_Explorer(face,TopAbs_WIRE)
            wires=[]
            while explorer.More(): wires.append(TopoDS.Wire_s(explorer.Current())); explorer.Next()
            wires.sort(key=lambda w:0 if w.IsSame(outer) else 1)
            for w in wires:
                ordered=[]; walk=BRepTools_WireExplorer(w,face)
                while walk.More():
                    e=walk.Current(); ei=maps['edge'].FindIndex(e); forward=e.Orientation()!=TopAbs_REVERSED
                    ordered.extend(OrientedEdge(eid,forward) for eid in em[ei] if forward)
                    if not forward: ordered.extend(OrientedEdge(eid,False) for eid in reversed(em[ei]))
                    walk.Next()
                loops.append(tuple(ordered))
            if not loops or len(loops[0])<3: refuse('Native face loop requires exact splitting to at least three edges','geometry.loop.unsupported')
            fid=model.add_face_from_loop(loops[0],surface=support)
            face_loops[fid]=loops[1:]
            mapping[cref('face',i)]=(model.entity_ref('face',fid),)
    # Holes are authored through the public versioned persistence contract, not private stores.
    if any(face_loops.values()):
        payload=to_dict(model)
        for record in payload['faces']:
            record['holes']=[[[oe.edge,oe.forward] for oe in loop] for loop in face_loops[record['id']]]
        canonical=json.dumps({k:v for k,v in payload.items() if k!='checksum'},
            ensure_ascii=False,allow_nan=False,separators=(',',':'),sort_keys=True).encode('utf-8')
        payload['checksum']={'algorithm':'sha256','value':hashlib.sha256(canonical).hexdigest()}
        model=from_dict(payload)
    if options.validation_mode=='certified': to_dict(model,certified=True)
    native.checkpoint(cancellation)
    mapping={cad:tuple(model.handle(ref.kind,ref.id) for ref in references) for cad,references in mapping.items()}
    report=GeometryImportReport(m.source_format,m.source_sha256,model.model_id,model.revision,m.source_length_unit,
        cad_to_geometry=mapping,approximations=tuple(replace(r,source=model.handle(r.source.kind,r.source.id)) for r in approximations),metadata_losses=('CAD assembly hierarchy, names, colours and layers',
        'CAD shell/wire grouping is not inferred as structural parts/sheets/members'),
        backend_version=VERSION,binding_version=m.binding_version,occt_version=m.occt_version)
    return GeometryImportResult(model,report)
