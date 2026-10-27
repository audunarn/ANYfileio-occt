"""Native-authored clipped rational section BREP; no owner exporter fixture."""
import pytest
pytest.importorskip('OCP')
from fractions import Fraction as Q
from anyfileio.geometry import GeometryReadOptions,GeometryInterchangeError
from anyfileio_occt import _native
from anyfileio_occt.geometry_import import import_geometry,SECTION_CLIPPED_IMPORT_METHOD
from test_native_geometry import read


def clipped_native(reverse=False,retained_domain=False,separate_supports=False,height_offset=0.):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge,BRepBuilderAPI_MakeVertex,BRepBuilderAPI_MakeWire,BRepBuilderAPI_MakeFace
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound,TopoDS
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Pnt,gp_Pln,gp_Ax3,gp_Dir
    from OCP.Geom import Geom_Plane
    from anygeometry.nurbs import NurbsSurface
    from anyfileio_occt._geometry import bspline_curve,surface_to_native
    support=surface_to_native(NurbsSurface(1,1,(0,0,1,1),(0,0,1,1),(((0,0,height_offset),(0,1,height_offset)),((1,0,height_offset),(1,1,1+height_offset)))))
    plane=Geom_Plane(gp_Pln(gp_Ax3(gp_Pnt(0,0,.5+height_offset),gp_Dir(0,0,1),gp_Dir(1,0,0))))
    second_support=support.Copy() if separate_supports else support
    second_plane=plane.Copy() if separate_supports else plane
    builder=BRep_Builder();loc=TopLoc_Location();a,b=Q(5,8),Q(7,8)
    points={'a':(a,0,0),'b':(b,0,0),'c':(b,1,b),'d':(a,1,a),
        'p':(b,Q(1,2)/b,Q(1,2)),'q':(a,Q(1,2)/a,Q(1,2)),
        'A':(a,0,.5),'B':(b,0,.5),'C':(b,1,.5),'D':(a,1,.5)}
    points={key:(float(p[0]),float(p[1]),float(p[2])+height_offset) for key,p in points.items()}
    vertices={key:BRepBuilderAPI_MakeVertex(gp_Pnt(*p)).Vertex() for key,p in points.items()}
    def line(x,y,s=None):
        if s is None:return BRepBuilderAPI_MakeEdge(vertices[x],vertices[y]).Edge()
        curve=bspline_curve([points[x],points[y]],1,(0,0,1,1))
        e=BRepBuilderAPI_MakeEdge(curve,vertices[x],vertices[y],0.,1.).Edge()
        if s is not None:
            builder.UpdateEdge(e,bspline_curve([points[x][:2],points[y][:2]],1,(0,0,1,1),None,2),s,loc,1e-7)
            builder.Range(e,s,loc,0.,1.)
        return e
    basis_a,basis_b=(Q(1,2),Q(1)) if retained_domain else (a,b)
    first,last=(.25,.75) if retained_domain else (0.,1.)
    weights=(float(basis_a),float((basis_a+basis_b)/2),float(basis_b))
    controls=((float(basis_a),float(Q(1,2)/basis_a),.5),
        (float(2*basis_a*basis_b/(basis_a+basis_b)),float(1/(basis_a+basis_b)),.5),(float(basis_b),float(Q(1,2)/basis_b),.5))
    controls=tuple((x,y,z+height_offset) for x,y,z in controls)
    start,end='q','p'
    if reverse:controls=controls[::-1];weights=weights[::-1];start,end=end,start
    trace=BRepBuilderAPI_MakeEdge(bspline_curve(controls,2,(0,0,0,1,1,1),weights),vertices[start],vertices[end],first,last).Edge()
    for s in (support,second_support,plane,second_plane):
        builder.UpdateEdge(trace,bspline_curve([p[:2] for p in controls],2,(0,0,0,1,1,1),weights,2),s,loc,1e-7)
        builder.Range(trace,s,loc,first,last)
    forward=trace.Reversed() if reverse else trace
    ab,bp,pc,cd,dq,qa=[line(x,y,second_support if x+y in ('pc','cd','dq') else support) for x,y in ('ab','bp','pc','cd','dq','qa')]
    AB,Bp,pC,CD,Dq,qA=[line(x,y) for x,y in ('AB','Bp','pC','CD','Dq','qA')]
    def face(s,items):
        wire=BRepBuilderAPI_MakeWire()
        for e in items:wire.Add(TopoDS.Edge_s(e))
        return BRepBuilderAPI_MakeFace(s,wire.Wire(),True).Face()
    output=TopoDS_Compound();builder.MakeCompound(output)
    for f in (face(support,[ab,bp,forward.Reversed(),qa]),face(second_support,[forward,pc,cd,dq]),
              face(plane,[AB,Bp,forward.Reversed(),qA]),face(second_plane,[forward,pC,CD,Dq])):builder.Add(output,f)
    return output


def options(**changes):
    settings=dict(fidelity='approximate',max_deviation_m=.01,max_segments=100000,max_depth=48)
    settings.update(changes);return GeometryReadOptions(**settings)


@pytest.mark.parametrize('reverse',[False,True])
def test_native_clipped_four_face_domain(tmp_path,reverse):
    from anygeometry.support_curves import PlaneNurbsCurve
    import numpy as np
    path=tmp_path/'clipped.brep';_native.write_shape(clipped_native(reverse),path,'brep','m');before=path.read_bytes()
    with read(path,'m') as document:result=import_geometry(document,options=options())
    model=result.geometry;traces=[e for e in model.edges.values() if isinstance(e.curve,PlaneNurbsCurve)]
    assert len(traces)==1 and len(model.faces_using_edge(traces[0].id))==4
    assert len(model.faces)==4 and len(model.edges)==13 and len(model.vertices)==10
    assert not model.validate_topology()
    curve=traces[0].curve
    assert curve.domain not in ((0.,1.),(1.,0.))
    assert (curve.domain[0]>curve.domain[1])==reverse
    points=curve.evaluate(np.linspace(0,1,9))
    assert points[:,0]*points[:,1]==pytest.approx(np.full(9,.5),abs=1e-12)
    assert result.report.approximations[0].method==SECTION_CLIPPED_IMPORT_METHOD
    assert result.report.approximations[0].bound_m<=.01 and path.read_bytes()==before


def test_default_depth_is_explicit_refusal(tmp_path):
    path=tmp_path/'clipped.brep';_native.write_shape(clipped_native(),path,'brep','m');before=path.read_bytes()
    with read(path,'m') as document:
        with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
            import_geometry(document,options=options(max_depth=24))
    assert path.read_bytes()==before


def test_previous_20k_budget_explicitly_refuses_cooperative_work(tmp_path):
    path=tmp_path/'limited.brep';_native.write_shape(clipped_native(),path,'brep','m');before=path.read_bytes()
    with read(path,'m') as document:
        with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
            import_geometry(document,options=options(max_segments=20000))
    assert path.read_bytes()==before


@pytest.mark.parametrize('reverse',[False,True])
def test_retained_native_basis_and_subdomain(tmp_path,reverse):
    from anygeometry.support_curves import PlaneNurbsCurve
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopoDS import TopoDS
    shape=clipped_native(reverse,retained_domain=True);edges=_native.shape_map(shape,'edge');faces=_native.shape_map(shape,'face')
    for i in range(1,edges.Extent()+1):
        edge=TopoDS.Edge_s(edges.FindKey(i))
        if sum(_native.shape_map(faces.FindKey(j),'edge').Contains(edge) for j in range(1,5))==4:
            curve=BRepAdaptor_Curve(edge)
            assert (curve.FirstParameter(),curve.LastParameter())==(.25,.75)
            assert curve.BSpline().FirstParameter()==0 and curve.BSpline().LastParameter()==1
    path=tmp_path/'retained.brep';_native.write_shape(shape,path,'brep','m');before=path.read_bytes()
    with read(path,'m') as document:result=import_geometry(document,options=options())
    trace=next(e for e in result.geometry.edges.values() if isinstance(e.curve,PlaneNurbsCurve))
    assert (trace.curve.domain[0]>trace.curve.domain[1])==reverse
    assert len(result.geometry.faces_using_edge(trace.id))==4 and not result.geometry.validate_topology()
    assert path.read_bytes()==before


@pytest.mark.parametrize('unit',['mm','cm'])
def test_nondefault_literal_units(tmp_path,unit):
    from anygeometry.support_curves import PlaneNurbsCurve
    import numpy as np
    path=tmp_path/'units.brep';_native.write_shape(clipped_native(True),path,'brep',unit);before=path.read_bytes()
    with read(path,unit) as document:result=import_geometry(document,options=options())
    trace=next(e for e in result.geometry.edges.values() if isinstance(e.curve,PlaneNurbsCurve))
    assert len(result.geometry.faces_using_edge(trace.id))==4
    points=trace.curve.evaluate(np.linspace(0,1,9))
    assert points[:,0]*points[:,1]==pytest.approx(np.full(9,.5),abs=1e-12)
    assert not result.geometry.validate_topology() and path.read_bytes()==before


def test_owner_without_cooperative_api_refuses_whole_and_clipped(tmp_path,monkeypatch):
    import sys
    from test_plane_nurbs_trims import native_four_faces
    whole=tmp_path/'whole.brep';clipped=tmp_path/'clipped.brep'
    _native.write_shape(native_four_faces(),whole,'brep','m');_native.write_shape(clipped_native(),clipped,'brep','m')
    monkeypatch.setitem(sys.modules,'anygeometry.curve_parameter_matching',None)
    for path in (whole,clipped):
        with read(path,'m') as document:
            with pytest.raises(GeometryInterchangeError,match='geometry.owner.parameter_matching_missing'):
                import_geometry(document,options=options())


@pytest.mark.parametrize('reason',['inconclusive','budget_exhausted','precision_exhausted'])
def test_matching_failures_charge_actual_work_and_never_partial(tmp_path,monkeypatch,reason):
    import anygeometry.curve_parameter_matching as matching
    from anyfileio_occt import _trim_bounds
    path=tmp_path/'clipped.brep';_native.write_shape(clipped_native(),path,'brep','m');before=path.read_bytes()
    works=[];actual=_trim_bounds._Work
    class Tracked(actual):
        def __init__(self,*args):super().__init__(*args);works.append(self)
    monkeypatch.setattr(_trim_bounds,'_Work',Tracked)
    charged=[]
    original=matching.match_curve_parameter_regions
    def failed(*args,**kwargs):
        start=works[0].used
        result=original(*args,**kwargs)
        charged.append(works[0].used-start)
        assert charged[-1]==result.work_used>0
        raise matching.CurveParameterMatchError(reason,'deliberate public failure')
    monkeypatch.setattr(matching,'match_curve_parameter_regions',failed)
    code='geometry.trim.parameter_inconclusive' if reason=='inconclusive' else 'geometry.approximation.budget'
    with read(path,'m') as document:
        with pytest.raises(GeometryInterchangeError,match=code):import_geometry(document,options=options())
    assert len(charged)==1 and charged[0]>0 and path.read_bytes()==before


def test_all_possible_regions_stay_ambiguous(tmp_path,monkeypatch):
    import anygeometry.curve_parameter_matching as matching
    from dataclasses import replace
    path=tmp_path/'clipped.brep';_native.write_shape(clipped_native(),path,'brep','m');before=path.read_bytes()
    original=matching.match_curve_parameter_regions
    def ambiguous(*args,**kwargs):
        result=original(*args,**kwargs)
        if not result.regions:return result
        return replace(result,regions=result.regions+(matching.ParameterRegion(.9,.95),),candidates=result.candidates+(result.candidates[0],))
    monkeypatch.setattr(matching,'match_curve_parameter_regions',ambiguous)
    with read(path,'m') as document:
        with pytest.raises(GeometryInterchangeError,match='geometry.trim.section_domain_ambiguous'):
            import_geometry(document,options=options())
    assert path.read_bytes()==before


def test_cancellation_inside_matching_preserves_input(tmp_path,monkeypatch):
    import anygeometry.curve_parameter_matching as matching
    from anyfileio.cad import CadOperationCancelled
    path=tmp_path/'clipped.brep';_native.write_shape(clipped_native(),path,'brep','m');before=path.read_bytes()
    original=matching.match_curve_parameter_regions;state={'stop':False,'units':0}
    def interrupted(*args,**kwargs):
        state['units']+=1;state['stop']=True
        return original(*args,**kwargs)
    monkeypatch.setattr(matching,'match_curve_parameter_regions',interrupted)
    with read(path,'m') as document:
        with pytest.raises(CadOperationCancelled):import_geometry(document,options=options(),cancellation=lambda:state['stop'])
    assert state['units']==1 and path.read_bytes()==before


def test_wrong_native_uv_path_and_finite_work_refuse(tmp_path):
    from OCP.BRep import BRep_Tool,BRep_Builder
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt2d
    from OCP.BRepTools import BRepTools
    shape=clipped_native();faces=_native.shape_map(shape,'face');edges=_native.shape_map(shape,'edge')
    for i in range(1,edges.Extent()+1):
        edge=TopoDS.Edge_s(edges.FindKey(i))
        if sum(_native.shape_map(faces.FindKey(j),'edge').Contains(edge) for j in range(1,5))!=4:continue
        face=TopoDS.Face_s(faces.FindKey(1));pc=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.).Copy()
        for k in range(1,pc.NbPoles()+1):pc.SetPole(k,gp_Pnt2d(.1,.2))
        BRep_Builder().UpdateEdge(edge,pc,face,1e-7)
    path=tmp_path/'wrong.brep';assert BRepTools.Write_s(shape,str(path));before=path.read_bytes()
    with read(path,'m') as document:
        with pytest.raises(GeometryInterchangeError,match='geometry.trim.section_domain_no_match'):
            import_geometry(document,options=options())
    assert path.read_bytes()==before
    _native.write_shape(clipped_native(),path,'brep','m')
    with read(path,'m') as document:
        with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
            import_geometry(document,options=options(max_segments=100))


def test_certified_uv_representatives_are_proposals_world_and_raw_proof_decide(tmp_path,monkeypatch):
    import anygeometry.curve_parameter_matching as matching
    from anyfileio_occt import _trim_bounds
    from anyfileio_occt.backend import document_shape
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS
    path=tmp_path/'clipped.brep';_native.write_shape(clipped_native(),path,'brep','mm')
    original=matching.match_curve_parameter_regions;records=[]
    def recorded(master,target,tolerance,**kwargs):
        result=original(master,target,tolerance,**kwargs)
        for candidate in result.candidates:
            low,high=candidate.chart_box
            maximum=sum(max(abs(a-Q(float(d))),abs(b-Q(float(c))))**2 for a,b,c,d in zip(low,high,*target))
            assert maximum==candidate.residual_squared<=Q(tolerance)**2
        records.append(result);return result
    monkeypatch.setattr(matching,'match_curve_parameter_regions',recorded)
    actual=_trim_bounds._certify;proofs=[]
    def certified(source,targets,source_ratio,target_ratio,*args):
        assert source.domain not in ((0.,1.),(1.,0.))
        assert len(targets)==5 and source_ratio==Q(1) and target_ratio==Q(1,1000)
        proofs.append(1);return actual(source,targets,source_ratio,target_ratio,*args)
    monkeypatch.setattr(_trim_bounds,'_certify',certified)
    with read(path,'mm') as document:
        shape=document_shape(document);vertices=_native.shape_map(shape,'vertex')
        positions={tuple((BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertices.FindKey(i))).X(),BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertices.FindKey(i))).Y(),BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertices.FindKey(i))).Z())) for i in range(1,vertices.Extent()+1)}
        result=import_geometry(document,options=options())
        assert {tuple(v.position) for v in result.geometry.vertices.values()}==positions
    assert len(records)==2 and len(proofs)==1


def test_inconsistent_owner_work_receipt_refuses(tmp_path,monkeypatch):
    import anygeometry.curve_parameter_matching as matching
    from dataclasses import replace
    path=tmp_path/'clipped.brep';_native.write_shape(clipped_native(),path,'brep','m')
    original=matching.match_curve_parameter_regions
    def wrong(*args,**kwargs):return replace(original(*args,**kwargs),work_used=0)
    monkeypatch.setattr(matching,'match_curve_parameter_regions',wrong)
    with read(path,'m') as document:
        with pytest.raises(GeometryInterchangeError,match='geometry.owner.parameter_matching_invalid'):
            import_geometry(document,options=options())


def test_public_facade_native_persistence_and_brep_cycle(tmp_path):
    from anyfileio.geometry import read_geometry,write_geometry,GeometryWriteOptions
    from anygeometry.serialization import to_dict
    from anygeometry.support_curves import PlaneNurbsCurve
    source=tmp_path/'input.brep';_native.write_shape(clipped_native(True),source,'brep','m');before=source.read_bytes()
    result=read_geometry(source,options=options(source_length_unit_override='m'))
    model=result.geometry;definition=to_dict(model)
    saved=tmp_path/'editable.anygeometry.json';write_geometry(saved,model)
    restored=read_geometry(saved).geometry
    assert to_dict(restored)==definition
    output=tmp_path/'output.brep'
    report=write_geometry(output,restored,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.01,max_segments=20000,max_depth=48))
    assert report.approximations and all(a.bound_m<=.01 for a in report.approximations)
    decoded=read_geometry(output,options=options(source_length_unit_override='m')).geometry
    def cycles(owner):
        answer=[]
        for face in owner.faces.values():
            def cycle(loop):
                points=[]
                for use in loop:
                    edge=owner.edges[use.edge]
                    points.append(tuple(owner.vertices[edge.start if use.forward else edge.end].position))
                return min(tuple(points[i:]+points[:i]) for i in range(len(points)))
            answer.append((cycle(face.loop),tuple(sorted(cycle(h) for h in face.holes))))
        return sorted(answer)
    assert cycles(decoded)==cycles(model)
    assert (len(decoded.faces),len(decoded.edges),len(decoded.vertices))==(4,13,10)
    trace=next(e for e in decoded.edges.values() if isinstance(e.curve,PlaneNurbsCurve))
    assert len(decoded.faces_using_edge(trace.id))==4 and not decoded.validate_topology()
    assert to_dict(restored)==definition and source.read_bytes()==before


@pytest.mark.parametrize('changed',['second_nurbs','second_plane','raw_3d'])
def test_real_import_tamper_reaches_literal_all_incident_certificate(tmp_path,monkeypatch,changed):
    from OCP.BRep import BRep_Tool,BRep_Builder
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt,gp_Pnt2d
    from anyfileio_occt import _trim_bounds
    path=tmp_path/'tampered.brep'
    _native.write_shape(clipped_native(separate_supports=True),path,'brep','mm')
    control_bytes=path.read_bytes()
    with read(path,'mm') as document:
        control=import_geometry(document,options=options(max_depth=48,max_segments=30000))
    assert control.report.approximations and all(r.bound_m<=.01 for r in control.report.approximations)
    assert path.read_bytes()==control_bytes
    # Change literal file geometry AFTER output-unit normalization. In particular
    # OCCT's unit transform may regenerate planar PCs from the unchanged 3D fit.
    shape,_=_native.read_shape(path,'brep','mm',raw_coordinates=True)
    faces=_native.shape_map(shape,'face');edges=_native.shape_map(shape,'edge')
    for i in range(1,edges.Extent()+1):
        edge=TopoDS.Edge_s(edges.FindKey(i))
        if sum(_native.shape_map(faces.FindKey(j),'edge').Contains(edge) for j in range(1,5))!=4:continue
        def pc_data(j):
            pc=BRep_Tool.CurveOnSurface_s(edge,TopoDS.Face_s(faces.FindKey(j)),0.,0.)
            from OCP.Geom2d import Geom2d_TrimmedCurve
            while isinstance(pc,Geom2d_TrimmedCurve):pc=pc.BasisCurve()
            return tuple((pc.Pole(k).X(),pc.Pole(k).Y(),pc.Weight(k)) for k in range(1,pc.NbPoles()+1))
        before=[pc_data(j) for j in range(1,5)]
        if changed=='raw_3d':
            curve=BRepAdaptor_Curve(edge).BSpline().Copy();p=curve.Pole(2)
            curve.SetPole(2,gp_Pnt(p.X(),p.Y(),p.Z()+100));BRep_Builder().UpdateEdge(edge,curve,1e-7)
            assert [pc_data(j) for j in range(1,5)]==before
        else:
            fi=2 if changed=='second_nurbs' else 4
            face=TopoDS.Face_s(faces.FindKey(fi));pc=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.).Copy()
            from OCP.Geom2d import Geom2d_TrimmedCurve
            while isinstance(pc,Geom2d_TrimmedCurve):pc=pc.BasisCurve().Copy()
            p=pc.Pole(2)
            delta=.1 if changed=='second_nurbs' else 100.
            pc.SetPole(2,gp_Pnt2d(p.X()+delta,p.Y()+delta));BRep_Builder().UpdateEdge(edge,pc,face,1e-7)
            after=[pc_data(j) for j in range(1,5)]
            assert after[0]==before[0] # the locator's PC is untouched
            assert all(after[j]==before[j] for j in range(4) if j!=fi-1)
        expected=[pc_data(j) for j in range(1,5)]
    assert BRepTools.Write_s(shape,str(path));before_bytes=path.read_bytes()
    reloaded,_=_native.read_shape(path,'brep','mm',raw_coordinates=True)
    actual_faces=_native.shape_map(reloaded,'face');actual_edges=_native.shape_map(reloaded,'edge')
    from OCP.Geom2d import Geom2d_TrimmedCurve
    for i in range(1,actual_edges.Extent()+1):
        actual_edge=TopoDS.Edge_s(actual_edges.FindKey(i))
        if sum(_native.shape_map(actual_faces.FindKey(j),'edge').Contains(actual_edge) for j in range(1,5))!=4:continue
        observed=[]
        for j in range(1,5):
            pc=BRep_Tool.CurveOnSurface_s(actual_edge,TopoDS.Face_s(actual_faces.FindKey(j)),0.,0.)
            while isinstance(pc,Geom2d_TrimmedCurve):pc=pc.BasisCurve()
            observed.append(tuple((pc.Pole(k).X(),pc.Pole(k).Y(),pc.Weight(k)) for k in range(1,pc.NbPoles()+1)))
        assert observed==expected # actual serialized incident PCs, not alien records
    actual=_trim_bounds._certify;reached=[]
    def checked(source,targets,source_ratio,target_ratio,*args):
        assert len(targets)==5 and source_ratio==Q(1) and target_ratio==Q(1,1000)
        reached.append(True);return actual(source,targets,source_ratio,target_ratio,*args)
    monkeypatch.setattr(_trim_bounds,'_certify',checked)
    with read(path,'mm') as document:
        with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
            import_geometry(document,options=options(max_depth=48,max_segments=30000))
    assert reached==[True] and path.read_bytes()==before_bytes


@pytest.mark.parametrize('cancel',[False,True])
def test_real_import_owner_query_refusal_typed_and_cancel_identity(tmp_path,monkeypatch,cancel):
    from anygeometry.support_curves import PlaneNurbsCurve
    from anygeometry.plane_nurbs import PlaneNurbsNotCertified,CURRENT_WORK
    from anyfileio.cad import CadOperationCancelled
    path=tmp_path/'query.brep';_native.write_shape(clipped_native(),path,'brep','m');before=path.read_bytes()
    failure=CadOperationCancelled('query stop') if cancel else PlaneNurbsNotCertified('deliberate owner enclosure refusal')
    def refused(self):raise failure
    monkeypatch.setattr(PlaneNurbsCurve,'chart_bounds',refused)
    with read(path,'m') as document:
        with pytest.raises(CadOperationCancelled if cancel else GeometryInterchangeError) as error:
            import_geometry(document,options=options())
    if cancel:assert error.value is failure
    else:assert 'geometry.trim.parameter_inconclusive' in str(error.value) and 'enclosure_refused' in str(error.value)
    assert path.read_bytes()==before and CURRENT_WORK.get() is None


def test_construction_tiny_budget_is_typed_and_tokens_reset(tmp_path,monkeypatch):
    import anygeometry.plane_nurbs as section
    path=tmp_path/'fresh.brep';_native.write_shape(clipped_native(height_offset=2**-10),path,'brep','m')
    original=section.plane_nurbs_section;phase=[]
    def factory(*args,**kwargs):
        assert section.CURRENT_WORK.get() is not None
        phase.append('start');result=original(*args,**kwargs);phase.append('finish');return result
    monkeypatch.setattr(section,'plane_nurbs_section',factory)
    with read(path,'m') as document:
        with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
            import_geometry(document,options=options(max_segments=22))
    assert phase==['start'] and section.CURRENT_WORK.get() is None


@pytest.mark.parametrize('kind',['cad','geometry','base'])
def test_caller_cancellation_during_construction_identity(tmp_path,monkeypatch,kind):
    import anygeometry.plane_nurbs as section
    from anygeometry.errors import GeometryError
    from anyfileio.cad import CadOperationCancelled
    class Stop(BaseException):pass
    stop={'cad':CadOperationCancelled('stop'),'geometry':GeometryError('stop'),'base':Stop()}[kind]
    path=tmp_path/'factory.brep';_native.write_shape(clipped_native(),path,'brep','m');before=path.read_bytes()
    original=section.plane_nurbs_section;phase=[]
    def factory(*args,**kwargs):phase.append(True);return original(*args,**kwargs)
    def cancelled():
        if phase:raise stop
        return False
    monkeypatch.setattr(section,'plane_nurbs_section',factory)
    with read(path,'m') as document:
        with pytest.raises(type(stop)) as error:import_geometry(document,options=options(),cancellation=cancelled)
    assert error.value is stop and phase==[True] and section.CURRENT_WORK.get() is None and path.read_bytes()==before


@pytest.mark.parametrize('alternative',['possible','empty','unresolved'])
def test_declared_closed_path_alternative_not_silently_skipped(tmp_path,monkeypatch,alternative):
    import anygeometry.plane_nurbs as section
    import anygeometry.curve_parameter_matching as matching
    from anygeometry.support_curves import PlaneNurbsCurve
    from dataclasses import replace
    path=tmp_path/'closed-alternative.brep';_native.write_shape(clipped_native(),path,'brep','m')
    original_section=section.plane_nurbs_section;original_factory=PlaneNurbsCurve.from_plane
    original_match=matching.match_curve_parameter_regions;closed_ids=set();queried=[]
    def sections(*args,**kwargs):
        found=original_section(*args,**kwargs)
        return replace(found,paths=found.paths+(replace(found.paths[0],closed=True),))
    def factory(cls,plane,support,path=0):
        curve=original_factory(plane,support,0)
        if path:closed_ids.add(id(curve))
        return curve
    def locate(base,*args,**kwargs):
        if id(base) not in closed_ids:return original_match(base,*args,**kwargs)
        queried.append(True)
        if alternative=='unresolved':raise matching.CurveParameterMatchInconclusive('closed alternative unresolved')
        if alternative=='empty':return matching.ParameterRegionMatch((),(),0)
        return original_match(base,*args,**kwargs)
    monkeypatch.setattr(section,'plane_nurbs_section',sections)
    monkeypatch.setattr(PlaneNurbsCurve,'from_plane',classmethod(factory))
    monkeypatch.setattr(matching,'match_curve_parameter_regions',locate)
    with read(path,'m') as document:
        if alternative=='empty':assert import_geometry(document,options=options()).geometry.faces
        else:
            code='closed_section_unsupported' if alternative=='possible' else 'parameter_inconclusive'
            with pytest.raises(GeometryInterchangeError,match=code):import_geometry(document,options=options())
    assert queried
