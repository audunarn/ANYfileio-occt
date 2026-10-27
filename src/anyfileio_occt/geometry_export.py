"""Editable model to CAD, with revision checks and no mutation of the owner."""
from __future__ import annotations
from contextlib import nullcontext,contextmanager,ExitStack
from anyfileio.geometry import GeometryWriteOptions,GeometryWriteReport,GeometryDiagnostic
from . import _native as native
from ._geometry import refuse,point,curve_edge,surface_to_native
from ._binding import _load_binding
from .backend import VERSION

def export_geometry(geometry,destination,*,options:GeometryWriteOptions=None,read_lease=None,cancellation=None):
    """Atomically publish through the core facade, including late refusal handling."""
    from anyfileio.geometry import write_geometry
    return write_geometry(destination,geometry,options=options,read_lease=read_lease,cancellation=cancellation)

@contextmanager
def _section_export_scope(geometry,options,cancellation):
    """One shared provider ledger for public owner steps and final proofs."""
    callback_error=None
    def guarded_cancellation():
        nonlocal callback_error
        try: return cancellation() if cancellation is not None else False
        except BaseException as error:
            callback_error=error
            guarded_cancellation._section_callback_error=error
            raise
    from anygeometry.support_curves import PlaneNurbsCurve
    affected=any(isinstance(edge.curve,PlaneNurbsCurve) for edge in geometry.edges.values())
    if not affected:
        yield None,guarded_cancellation if cancellation is not None else None
        return
    if options.validation_mode=='certified':
        refuse('Certified section export needs a public cooperative qualification context',
               'geometry.owner.cooperative_validation_missing')
    if options.fidelity!='approximate':
        # Committed exact conversion refuses this family before evaluating it.
        yield None,guarded_cancellation if cancellation is not None else None
        return
    try:
        from anygeometry.curve_parameter_matching import bounded_section_work,CurveParameterMatchError
    except ImportError:
        refuse('Section export requires the public owner bounded-work capability',
               'geometry.owner.section_work_missing')
    if not callable(bounded_section_work):
        refuse('Section export requires the public owner bounded-work capability',
               'geometry.owner.section_work_missing')
    from anygeometry.errors import GeometryError
    from ._trim_bounds import _Work
    work=_Work(options.max_segments)
    def checkpoint():
        nonlocal callback_error
        try:
            work.charge()
            native.checkpoint(guarded_cancellation)
        except BaseException as error:
            callback_error=error
            raise
    try:
        with bounded_section_work(max_work=options.max_segments,max_depth=options.max_depth,
                                  checkpoint=checkpoint):
            yield work,guarded_cancellation
    except BaseException as error:
        if error is callback_error: raise
        if isinstance(error,CurveParameterMatchError):
            if error.reason in ('budget_exhausted','depth_exhausted','precision_exhausted'):
                refuse(f'Public section export work refused: {error.reason}','geometry.approximation.budget')
            if error.reason=='nested_context':
                refuse('Another owner work context is active','geometry.owner.section_work_conflict')
            refuse(f'Public section export work refused: {error.reason}','geometry.bounds.owner_refused')
        if isinstance(error,GeometryError):
            refuse(f'Public section export enclosure refused: {error}','geometry.bounds.owner_refused')
        raise


def _export_geometry_to_temporary(geometry,destination,*,options:GeometryWriteOptions,read_lease=None,cancellation=None):
    if options.coordinate_space!='model_local':
        refuse('External coordinate transformation is not defined','geometry.external_transform_undefined')
    native.checkpoint(cancellation)
    if native.format_for(destination)!='brep':
        refuse('Editable export lacks proved file-record association for this format','geometry.association_unproved')
    from ._units import _CANONICAL_SCALES
    if geometry.units not in _CANONICAL_SCALES:
        refuse('Geometry units must be a recognized physical length unit','geometry.units.unsupported')
    source_scale=_CANONICAL_SCALES[geometry.units]
    model_id,revision=geometry.model_id,geometry.revision
    with read_lease if read_lease is not None else nullcontext() as token:
        if read_lease is not None and (token.geometry is not geometry or token.model_id!=model_id or token.revision!=revision):
            refuse('Read lease does not match geometry identity/revision','geometry.lease.mismatch')
        with _section_export_scope(geometry,options,cancellation) as (section_work,cancellation), ExitStack() as publication:
            if options.validation_mode=='certified':
                from anygeometry.serialization import to_dict
                to_dict(geometry,certified=True)
            binding=_load_binding()
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex,BRepBuilderAPI_MakeWire,BRepBuilderAPI_MakeFace
            from OCP.BRep import BRep_Builder
            from OCP.TopoDS import TopoDS_Compound,TopoDS_Shell,TopoDS
            from OCP.BRepCheck import BRepCheck_Analyzer
            vertices={i:BRepBuilderAPI_MakeVertex(point(v.position)).Vertex() for i,v in geometry.vertices.items()}
            edges={}; approximations=[]; diagnostics=[]; surface_cache={}
            approximate_edges=set()
            trim_faces={}
            for face in geometry.faces.values():
                for loop in (face.loop,)+face.holes:
                    for oe in loop: trim_faces.setdefault(oe.edge,[]).append(face)
            trim_ids=set(trim_faces)
            # Owner supports are immutable value objects, not native-handle identities.
            # Share the one native support across equal definitions before attaching PCs.
            from anygeometry.nurbs import CurveOnSurface,NurbsSurface
            from anygeometry.support_curves import PlaneNurbsCurve
            from anygeometry.surfaces import Plane
            if any(i in trim_ids and isinstance(e.curve,PlaneNurbsCurve) for i,e in geometry.edges.items()) and native.format_for(destination)!='brep':
                refuse('Bounded plane/NURBS trims are admitted only for BREP','geometry.trim.format_unsupported')
            for edge_id,owners in trim_faces.items():
                curve=geometry.edges[edge_id].curve
                if not isinstance(curve,(CurveOnSurface,PlaneNurbsCurve)): continue
                support=curve.support if isinstance(curve,CurveOnSurface) else curve.surface
                nurbs_faces=[f for f in owners if isinstance(f.surface,NurbsSurface)]
                if not nurbs_faces: continue
                if any(support!=f.surface for f in nurbs_faces):
                    refuse('Curve-on-surface trim belongs to a different face support','geometry.trim.support_mismatch')
                canonical=next((surface_cache[id(f.surface)] for f in nurbs_faces if id(f.surface) in surface_cache),None)
                if canonical is None: canonical=surface_to_native(nurbs_faces[0].surface)
                for f in nurbs_faces: surface_cache[id(f.surface)]=canonical
                surface_cache[id(support)]=canonical
            for i,edge in geometry.edges.items():
                native.checkpoint(cancellation)
                shapes,report=curve_edge(geometry,edge,vertices,surface_cache,options,cancellation,trim=i in trim_ids,work=section_work)
                edges[i]=shapes
                if report is not None: approximations.append(report); approximate_edges.add(i)
            faces={}
            def wire(loop):
                builder=BRepBuilderAPI_MakeWire()
                for oe in loop:
                    pieces=edges[oe.edge]
                    for shape in pieces if oe.forward else reversed(pieces):
                        builder.Add(shape if oe.forward else TopoDS.Edge_s(shape.Reversed()))
                if not builder.IsDone(): refuse('OCCT refused ordered loop','geometry.loop.invalid')
                return builder.Wire()
            for i,face in geometry.faces.items():
                native.checkpoint(cancellation)
                from ._trim_bounds import METHOD as trim_method
                unsupported_trims={r.source.id for r in approximations if r.method!=trim_method}
                if any(oe.edge in unsupported_trims for loop in (face.loop,)+face.holes for oe in loop):
                    refuse('Approximating a trim edge needs a certified trim/support consistency construction','geometry.trim.approximation_unsupported')
                outer=wire(face.loop)
                if face.surface is None:
                    maker=BRepBuilderAPI_MakeFace(outer,True)
                else:
                    surface=surface_cache.get(id(face.surface))
                    if surface is None: surface=surface_to_native(face.surface,geometry,face); surface_cache[id(face.surface)]=surface
                    if isinstance(face.surface,Plane):
                        from ._geometry import attach_section_plane
                        for loop in (face.loop,)+face.holes:
                            for oe in loop:
                                curve=geometry.edges[oe.edge].curve
                                if isinstance(curve,PlaneNurbsCurve):
                                    for piece in edges[oe.edge]: attach_section_plane(piece,surface,curve.plane)
                    from anygeometry.surfaces import RuledSurface,CoonsSurface
                    if isinstance(face.surface,RuledSurface) or isinstance(face.surface,CoonsSurface) and face.surface.has_boundaries:
                        from ._surface_trims import attach_grid_boundaries
                        attach_grid_boundaries(geometry,face,surface,edges,cancellation)
                    from anygeometry.surfaces import ExtrudedSurface
                    from anygeometry.extrusions import EllipseDirectrix
                    if isinstance(face.surface,ExtrudedSurface) and isinstance(face.surface.directrix,EllipseDirectrix):
                        from ._surface_trims import attach_ellipse_extrusion_boundaries
                        attach_ellipse_extrusion_boundaries(geometry,face,surface,edges,cancellation)
                    elif isinstance(face.surface,ExtrudedSurface):
                        from anygeometry.extrusions import BezierDirectrix
                        from anygeometry.curves import Straight,Spline
                        from fractions import Fraction as Q
                        import numpy as np
                        from OCP.BRep import BRep_Builder,BRep_Tool
                        from OCP.TopLoc import TopLoc_Location
                        from ._geometry import bspline_curve
                        s=face.surface
                        if not isinstance(s.directrix,BezierDirectrix):
                            refuse('Elliptic extrusion trims require an exact rational chart construction','geometry.trim.chart_unavailable')
                        ur,vr=s.u_range,s.v_range; length=float(np.linalg.norm(s.vector))
                        logical=[(0,0),(1,0),(1,1),(0,1)]
                        world=[s.evaluate(u,v) for u,v in logical]
                        chart=[(ur[0],length*vr[0]),(ur[1],length*vr[0]),(ur[1],length*vr[1]),(ur[0],length*vr[1])]
                        controls=[tuple(Q(x) for x in p) for p in s.directrix.controls]; degree=len(controls)-1
                        restricted=[]
                        for j in range(degree+1):
                            values=controls
                            for t in [Q(ur[0])]*(degree-j)+[Q(ur[1])]*j:
                                values=[tuple((1-t)*a+t*b for a,b in zip(p,q)) for p,q in zip(values,values[1:])]
                            restricted.append(values[0])
                        updater=BRep_Builder()
                        for loop in (face.loop,)+face.holes:
                            for oe in loop:
                                edge=geometry.edges[oe.edge]; pair=[]; corner_ids=[]
                                for vertex in (edge.start,edge.end):
                                    matches=[k for k,p in enumerate(world) if np.array_equal(p,geometry.vertices[vertex].position)]
                                    if len(matches)!=1: refuse('Extrusion trim is not an exact rectangular boundary','geometry.trim.chart_unavailable')
                                    corner_ids.append(matches[0]); pair.append(chart[matches[0]])
                                if pair[0][1]==pair[1][1]:
                                    if not isinstance(edge.curve,Spline): refuse('Extrusion profile trim must retain its polynomial controls','geometry.trim.chart_unavailable')
                                    level=Q(vr[0] if logical[corner_ids[0]][1]==0 else vr[1])
                                    expected=[tuple(x+level*Q(d) for x,d in zip(p,s.vector)) for p in restricted]
                                    if logical[corner_ids[0]][0]>logical[corner_ids[1]][0]: expected.reverse()
                                    actual=[tuple(Q(float(x)) for x in geometry.vertices[v].position) for v in (edge.start,*edge.curve.control_vertices,edge.end)]
                                    if actual!=expected: refuse('Extrusion boundary polynomial differs from authoritative directrix','geometry.trim.chart_unavailable')
                                elif pair[0][0]==pair[1][0]:
                                    if not isinstance(edge.curve,Straight): refuse('Extrusion generator must be straight','geometry.trim.chart_unavailable')
                                else: refuse('Extrusion diagonal trim needs an exact chart construction','geometry.trim.chart_unavailable')
                                first,last=BRep_Tool.Range_s(edges[oe.edge][0])
                                pc=bspline_curve(pair,1,[first,first,last,last],dimension=2)
                                updater.UpdateEdge(edges[oe.edge][0],pc,surface,TopLoc_Location(),1.e-7)
                                updater.Range(edges[oe.edge][0],surface,TopLoc_Location(),first,last)
                    from anygeometry.surfaces import Cylinder,Cone
                    if isinstance(face.surface,(Cylinder,Cone)):
                        from OCP.BRepAdaptor import BRepAdaptor_Curve
                        from OCP.GeomAbs import GeomAbs_Line,GeomAbs_Circle
                        from OCP.BRep import BRep_Builder
                        from OCP.TopLoc import TopLoc_Location
                        from ._geometry import bspline_curve
                        import math
                        import numpy as np
                        s=face.surface; updater=BRep_Builder()
                        cone_angle=math.atan((s.radius_end-s.radius_start)/s.height) if isinstance(s,Cone) else 0.
                        cosine=math.cos(cone_angle)
                        for loop in (face.loop,)+face.holes:
                            for oe in loop:
                                for edge_shape in edges[oe.edge]:
                                    c=BRepAdaptor_Curve(edge_shape); first,last=c.FirstParameter(),c.LastParameter()
                                    p=c.Value(first); position=np.array([p.X(),p.Y(),p.Z()])-s.origin
                                    angle=math.atan2(float(position@s.circumferential_direction),float(position@s.radial_direction))
                                    angle+=2*math.pi*round((s.start_angle+s.sweep_angle/2-angle)/(2*math.pi))
                                    axial=float(position@s.axis)/cosine
                                    if c.GetType()==GeomAbs_Line:
                                        d=c.Line().Direction(); rate=float(np.array([d.X(),d.Y(),d.Z()])@s.axis)/cosine
                                        pair=[(angle,axial),(angle,axial+(last-first)*rate)]
                                    elif c.GetType()==GeomAbs_Circle:
                                        d=c.Circle().Axis().Direction(); sign=1. if np.array([d.X(),d.Y(),d.Z()])@s.axis>0 else -1.
                                        pair=[(angle,axial),(angle+sign*(last-first),axial)]
                                    else:
                                        refuse('Analytic cylinder/cone trim needs an exact line/circle chart curve','geometry.trim.chart_unavailable')
                                    pc=bspline_curve(pair,1,[first,first,last,last],dimension=2)
                                    updater.UpdateEdge(edge_shape,pc,surface,TopLoc_Location(),1.e-7)
                                    updater.Range(edge_shape,surface,TopLoc_Location(),first,last)
                    from anygeometry.surfaces import CoonsSurface
                    from anygeometry.curves import Straight,Spline
                    if isinstance(face.surface,CoonsSurface) and not face.surface.has_boundaries and len(face.loop)==4 and all(isinstance(geometry.edges[oe.edge].curve,(Straight,Spline)) for oe in face.loop):
                        import numpy as np
                        # Owner-materialized polynomial boundaries preserve their affine
                        # Bernstein parameter. Determine chart orientation from corners.
                        from OCP.Geom2d import Geom2d_BezierCurve
                        from OCP.TColgp import TColgp_Array1OfPnt2d
                        from OCP.gp import gp_Pnt2d
                        from OCP.TopLoc import TopLoc_Location
                        from OCP.BRep import BRep_Builder
                        from ._geometry import bspline_curve
                        from anygeometry.interchange import face_support_for_interchange
                        explicit=face_support_for_interchange(geometry,i)
                        ur,vr=explicit.u_range,explicit.v_range
                        uv=[(ur[0],vr[0]),(ur[1],vr[0]),(ur[1],vr[1]),(ur[0],vr[1])]
                        corners=[]
                        for u,v in uv:
                            p=surface.Value(u,v); corners.append(np.array([p.X(),p.Y(),p.Z()]))
                        updater=BRep_Builder()
                        for j,oe in enumerate(face.loop):
                            edge=geometry.edges[oe.edge]
                            pair=[]
                            for vertex_id in (edge.start,edge.end):
                                matches=[k for k,p in enumerate(corners) if np.array_equal(p,geometry.vertices[vertex_id].position)]
                                if len(matches)!=1: refuse('Materialized Coons chart lacks a unique exact corner correspondence','geometry.trim.chart_unavailable')
                                pair.append(uv[matches[0]])
                            from OCP.BRep import BRep_Tool
                            first,last=BRep_Tool.Range_s(edges[oe.edge][0])
                            pc=bspline_curve(pair,1,[first,first,last,last],dimension=2)
                            updater.UpdateEdge(edges[oe.edge][0],pc,surface,TopLoc_Location(),1.e-7)
                            updater.Range(edges[oe.edge][0],surface,TopLoc_Location(),first,last)
                    maker=BRepBuilderAPI_MakeFace(surface,outer,True)
                for hole in face.holes: maker.Add(wire(hole))
                if not maker.IsDone() or not BRepCheck_Analyzer(maker.Face()).IsValid():
                    refuse(f'OCCT refused face/trim consistency for face {i}','geometry.face.invalid')
                faces[i]=maker.Face()
            builder=BRep_Builder()
            def compound(items):
                result=TopoDS_Compound(); builder.MakeCompound(result)
                for item in items: builder.Add(result,item)
                return result
            from ._reference_geometry import affiliations
            reference_geometry=affiliations(geometry,cancellation)
            all_face_edges={oe.edge for f in geometry.faces.values() for loop in (f.loop,)+f.holes for oe in loop}
            all_member_edges={geometry.member_edge_uses[uid].edge_id for member in geometry.members.values() for uid in member.edge_use_ids}
            incident_vertices={v for e in geometry.edges.values() for v in (e.start,e.end)}
            used_faces=set(); used_edges=set(); used_vertices=set(); owned_parts=[]; group_shapes=[]
            for part in geometry.parts.values():
                items=[]
                for sheet_id in part.sheet_ids:
                    sheet=geometry.sheets[sheet_id]; shell=TopoDS_Shell(); builder.MakeShell(shell)
                    for use_id in sheet.face_use_ids:
                        use=geometry.face_uses[use_id]; shape=faces[use.face_id]
                        builder.Add(shell,shape if int(use.orientation)==1 else shape.Reversed()); used_faces.add(use.face_id)
                    items.append(shell)
                    group_shapes.append(('sheet',sheet_id,'shell',shell))
                for member_id in part.member_ids:
                    member=geometry.members[member_id]; shapes=[]
                    for use_id in member.edge_use_ids:
                        use=geometry.member_edge_uses[use_id]
                        # parent_range places this whole current edge on the Member's
                        # persistent station axis; it is not an edge-local trim.
                        pieces=edges[use.edge_id]; used_edges.add(use.edge_id)
                        shapes.extend(pieces if int(use.orientation)==1 else [s.Reversed() for s in reversed(pieces)])
                    member_wire=BRepBuilderAPI_MakeWire()
                    for shape in shapes: member_wire.Add(TopoDS.Edge_s(shape))
                    if not member_wire.IsDone(): refuse('Declared member is not a CAD wire','geometry.member.invalid')
                    items.append(member_wire.Wire())
                    group_shapes.append(('member',member_id,'wire',member_wire.Wire()))
                for reference in reference_geometry.get(part.id,()):
                    native.checkpoint(cancellation)
                    if reference.kind=='edge':
                        if reference.id in all_face_edges|all_member_edges:
                            refuse('CAD reference edge acquired structural/carrier ownership','geometry.reference_geometry.invalid')
                        items.extend(edges[reference.id]); used_edges.add(reference.id)
                    else:
                        if reference.id in incident_vertices:
                            refuse('CAD reference point acquired an incident edge','geometry.reference_geometry.invalid')
                        items.append(vertices[reference.id]); used_vertices.add(reference.id)
                owned_parts.append(compound(items))
                group_shapes.append(('part',part.id,'part',owned_parts[-1]))
            all_face_edges={oe.edge for f in geometry.faces.values() for loop in (f.loop,)+f.holes for oe in loop}
            topological_vertices={v for e in geometry.edges.values() for v in (e.start,e.end)}
            fmt=native.format_for(destination)
            unowned_faces=[i for i in faces if i not in used_faces]
            face_items=[faces[i] for i in unowned_faces]
            if fmt=='step':
                # STEP's loose-face compound transfer emits independent products and
                # loses shared vertices/edges. Group only existing edge-connected
                # unowned faces in OPEN transport shells, without sewing or flipping.
                adjacency={i:set() for i in unowned_faces}; edge_owners={}
                for i in unowned_faces:
                    for loop in (geometry.faces[i].loop,)+geometry.faces[i].holes:
                        for use in loop: edge_owners.setdefault(use.edge,set()).add(i)
                for owners in edge_owners.values():
                    for i in owners: adjacency[i].update(owners-{i})
                face_items=[]; remaining=set(unowned_faces)
                for seed in unowned_faces:
                    if seed not in remaining: continue
                    component=set(); pending=[seed]
                    while pending:
                        native.checkpoint(cancellation); i=pending.pop()
                        if i in component: continue
                        component.add(i); pending.extend(adjacency[i]-component)
                    remaining-=component
                    if len(component)==1: face_items.append(faces[seed]); continue
                    shell=TopoDS_Shell(); builder.MakeShell(shell)
                    for i in sorted(component): builder.Add(shell,faces[i])
                    from OCP.BRep import BRep_Tool
                    if BRep_Tool.IsClosed_s(shell) or not BRepCheck_Analyzer(shell).IsValid():
                        refuse('Unowned connected faces need a valid open transport shell; declare intended shell ownership explicitly','geometry.topology.transport_unsupported')
                    face_items.append(shell)
                    diagnostics.append(GeometryDiagnostic('geometry.cad.transport_shell',
                        'Existing edge-connected unowned faces grouped in an open STEP carrier; no structural sheet is inferred',
                        tuple(geometry.handle('face',i) for i in sorted(component))))
            items=owned_parts+face_items
            items += [s for i,pieces in edges.items() if i not in all_face_edges|used_edges for s in pieces]
            # Construction/control points remain visible as disconnected CAD vertices.
            items += [v for i,v in vertices.items() if i not in topological_vertices|used_vertices]
            shape=compound(items)
            if not items: refuse('Cannot export an empty geometry model','geometry.model.empty')
            native_vertices=native.shape_map(shape,'vertex')
            native_edges=native.shape_map(shape,'edge')
            native_faces=native.shape_map(shape,'face')
            source_entities={}
            for i,v in vertices.items():
                index=native_vertices.FindIndex(v)
                if not index:
                    refuse('Source vertex identity was lost during native construction','geometry.output.references_missing')
                source_entities[geometry.handle('vertex',i)]=(v,)
            for i,pieces in edges.items():
                source_entities[geometry.handle('edge',i)]=tuple(pieces)
            for i,f in faces.items():
                source_entities[geometry.handle('face',i)]=(f,)
            part_entities=[]
            for kind,identifier,cad_kind,group_shape in group_shapes:
                handle=geometry.handle(kind,identifier)
                if kind=='part':part_entities.append((handle,group_shape))
                else:source_entities[handle]=(group_shape,)
            if geometry.model_id!=model_id or geometry.revision!=revision:
                refuse('Geometry changed during conversion','geometry.revision.changed')
            unit=options.output_length_unit or 'm'; fmt=native.format_for(destination)
            from ._association import Snapshot,writing
            from ._topology import Work
            topology_work=Work(options.max_topology_work,cancellation)
            from ._precision import Source as PrecisionSource
            precision=PrecisionSource(shape,geometry.units,geometry.tolerance,topology_work)
            snapshot=Snapshot(shape,source_scale,topology_work)
            snapshot.precision=precision
            output_shape=snapshot.si.shape
            if fmt=='step' and owned_parts:
                from ._xde import write_groups
                groups=[(part.name or f'Part {part.id}',native.scaled(part_shape,source_scale)) for part,part_shape in zip(geometry.parts.values(),owned_parts)]
                unowned=items[len(owned_parts):]
                if unowned: groups.append(('Unowned geometry',native.scaled(compound(unowned),source_scale)))
                write_groups(groups,destination,unit,cancellation)
            else:
                with writing(snapshot):native.write_shape(output_shape,destination,fmt,unit,cancellation)
            from ._topology import verify_file,Work
            if snapshot.capsule is None:refuse('Native writer returned no file-record provenance','geometry.association_unproved')
            from ._trim_bounds import METHOD as trim_method
            scene_groups=[(part.name or f'Part {part.id}',part_shape) for part,part_shape in zip(geometry.parts.values(),owned_parts)]
            unowned=items[len(owned_parts):]
            if scene_groups and unowned: scene_groups.append(('Unowned geometry',compound(unowned)))
            try:
                # Literal target selection and report reconciliation now share
                # one actual retained read, established below.
                from ._association import actual_association
                association=actual_association(shape,destination,unit,snapshot.capsule,topology_work,cancellation)
                publication.callback(association.close)
                topology=association.topology
            except Exception as error:
                if error is getattr(cancellation,'_section_callback_error',None): raise
                if any(r.method==trim_method for r in approximations) and getattr(error,'code',None) in ('geometry.topology.changed','geometry.topology.direction_unsupported'):
                    refuse('Material topology changed: vertex correspondence welded/split or oriented use incidence lost', 'geometry.trim.topology_changed')
                raise
            diagnostics+=topology[3]
            if approximations:
                from ._geometry import verify_serialized_polylines
                from ._trim_bounds import verify_fitted_trims,METHOD as trim_method
                groups={geometry.edges[i].ref:tuple(native_edges.FindIndex(e) for e in edges[i]) for i in approximate_edges}
                fitted=[r for r in approximations if r.method==trim_method]
                polylines=[r for r in approximations if r.method!=trim_method]
                approximations=[]
                if polylines:
                    approximations+=verify_serialized_polylines(shape,destination,fmt,unit,
                        groups,polylines,cancellation,source_scale,work=section_work,association=association)
                if fitted:
                    sources={geometry.edges[i].ref:geometry.edges[i].curve for i in approximate_edges}
                    verified,fit_diagnostics=verify_fitted_trims(shape,destination,fmt,unit,groups,sources,
                        fitted,options,cancellation,source_scale,topology=topology,work=section_work,association=association)
                    approximations+=verified; diagnostics+=fit_diagnostics
                from dataclasses import replace
                approximations=[replace(r,source=geometry.handle(r.source.kind,r.source.id)) for r in approximations]
                diagnostics=[replace(d,entities=tuple(geometry.handle(e.kind,e.id) for e in d.entities)) for d in diagnostics]
            from ._output_references import reconcile
            output_id,mapping,reference_diagnostics,reference_losses,output_sha=reconcile(
                geometry,shape,destination,fmt,unit,source_scale,source_entities,part_entities,
                scene_groups,topology_work,cancellation,association=association)
            diagnostics+=reference_diagnostics
            if geometry.model_id!=model_id or geometry.revision!=revision:
                refuse('Geometry changed during CAD writing','geometry.revision.changed')
            return GeometryWriteReport(fmt,model_id,revision,output_sha,geometry.units,unit,
                mapping,tuple(approximations),('model UUID/revision and persistent topology IDs','origin and CRS metadata',
                'feature history, groups, tags, attachments and junctions','construction/control vertex roles',
                'member/sheet names and application metadata',
                'persistent member station ranges and edge-use history; any reconstructed member stations derive from imported edge lengths')+reference_losses,
                diagnostics=tuple(diagnostics),backend_version=VERSION,binding_version=binding.distribution_version,occt_version='7.9.3',output_document_id=output_id)
