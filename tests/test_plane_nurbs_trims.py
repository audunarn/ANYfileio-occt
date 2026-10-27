"""Bounded implicit section trims; public owner construction and actual BREP."""
import numpy as np
import pytest
pytest.importorskip('OCP')
from anyfileio.geometry import GeometryWriteOptions,GeometryReadOptions,GeometryInterchangeError,write_geometry
from anyfileio_occt.geometry_import import import_geometry
from test_native_geometry import read


def section_model(different_frame=False):
    from anygeometry import GeometryModel,Plane,plan_plane_split,apply_plane_split
    from anygeometry.entities import OrientedEdge
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    model=GeometryModel()
    support=NurbsSurface(1,1,(0,0,1,1),(0,0,1,1),(((0,0,0),(0,1,0)),((1,0,0),(1,1,1))))
    corners=((0,0),(1,0),(1,1),(0,1))
    vertices=[model.add_point(*support.evaluate(*uv)) for uv in corners]
    edges=[model.add_curve(vertices[i],vertices[(i+1)%4],CurveOnSurface(support,NurbsCurve(1,(0,0,1,1),(uv,corners[(i+1)%4])))) for i,uv in enumerate(corners)]
    face=model.add_face(edges,surface=support)
    plane=Plane((0,0,.5),(1,0,0),(0,1,0))
    result=apply_plane_split(model,plan_plane_split(model,[face],plane),policy='imprint')
    trace=model.edges[result.trace_edges[0]]
    a,b=trace.start,trace.end
    if model.vertices[a].position[0]>.75: a,b=b,a
    def use(start,end):
        if {start,end}=={trace.start,trace.end}: return OrientedEdge(trace.id,start==trace.start)
        return OrientedEdge(model.add_line(start,end),True)
    lower=[model.add_point(0,0,.5),model.add_point(1,0,.5),b,a,model.add_point(0,1,.5)]
    upper=[b,model.add_point(1,1,.5),a]
    for index,ids in enumerate((lower,upper)):
        frame=Plane((1,1,.5),(0,1,0),(-1,0,0)) if different_frame and index==1 else plane
        model.add_face_from_loop([use(x,y) for x,y in zip(ids,ids[1:]+ids[:1])],surface=frame)
    return model


def test_public_four_face_fixture():
    from anygeometry.support_curves import PlaneNurbsCurve
    model=section_model()
    traces=[e for e in model.edges.values() if isinstance(e.curve,PlaneNurbsCurve)]
    assert traces and all(len(model.faces_using_edge(e.id))==4 for e in traces)
    assert not model.validate_topology()


def test_bounded_brep_roundtrip(tmp_path):
    from anygeometry.serialization import to_dict
    from anygeometry.support_curves import PlaneNurbsCurve
    model=section_model(); before=to_dict(model); path=tmp_path/'section.brep'
    opts=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.002,max_segments=100000)
    report=write_geometry(path,model,options=opts)
    assert report.approximations and max(r.bound_m for r in report.approximations)<=.002
    assert to_dict(model)==before
    with read(path,'m') as document:
        result=import_geometry(document,options=GeometryReadOptions(fidelity='approximate',max_deviation_m=.002,max_segments=100000))
    traces=[e for e in result.geometry.edges.values() if isinstance(e.curve,PlaneNurbsCurve)]
    assert traces and all(len(result.geometry.faces_using_edge(e.id))==4 for e in traces)
    assert result.report.approximations and not result.geometry.validate_topology()
    assert all(r.method=='public whole-open section reconstruction + input 3D/all-pcurve union-box enclosure' for r in result.report.approximations)
    assert all(r.method=='native pcurve fit + serialized source/3D/trim union-box enclosure' for r in report.approximations)
    for edge in traces:
        points=edge.curve.evaluate(np.linspace(0,1,17))
        assert np.max(abs(points[:,0]*points[:,1]-.5))<1e-12


@pytest.fixture(scope='module')
def cached_section(tmp_path_factory):
    model=section_model(); path=tmp_path_factory.mktemp('section')/'source.brep'
    write_geometry(path,model,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.01,max_segments=20000))
    return model,path


@pytest.mark.parametrize('operation',['exact','depth','work','cancel','step'])
def test_export_refusals_atomic(tmp_path,cached_section,operation):
    from anygeometry.serialization import to_dict
    from anyfileio.cad import CadOperationCancelled
    from anyfileio_occt import _native
    model,_=cached_section; before=to_dict(model)
    path=tmp_path/('old.step' if operation=='step' else 'old.brep'); path.write_bytes(b'old')
    settings=dict(fidelity='approximate',max_deviation_m=.01,max_segments=20000)
    if operation=='exact': settings=dict()
    if operation=='depth': settings.update(max_depth=1,max_deviation_m=1e-8)
    if operation=='work': settings.update(max_segments=20)
    cancelled=(lambda:True) if operation=='cancel' else None
    with pytest.raises((GeometryInterchangeError,CadOperationCancelled)):
        write_geometry(path,model,options=GeometryWriteOptions(**settings),cancellation=cancelled)
    assert path.read_bytes()==b'old' and to_dict(model)==before


def test_exact_import_refuses_and_input_unchanged(cached_section):
    _,path=cached_section; before=path.read_bytes()
    with read(path,'m') as document:
        with pytest.raises(GeometryInterchangeError,match='geometry.exact.composition_unavailable'):
            import_geometry(document,options=GeometryReadOptions())
    assert path.read_bytes()==before


@pytest.mark.parametrize('settings',[{'max_segments':2},{'max_depth':1}])
def test_import_proof_limits(cached_section,settings):
    _,path=cached_section; before=path.read_bytes()
    with read(path,'m') as document:
        with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
            import_geometry(document,options=GeometryReadOptions(fidelity='approximate',max_deviation_m=.01,**settings))
    assert path.read_bytes()==before


def native_four_faces():
    """Independent native rational hyperbola: u=(1+t)/2,v=1/(1+t)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge,BRepBuilderAPI_MakeVertex,BRepBuilderAPI_MakeWire,BRepBuilderAPI_MakeFace
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound,TopoDS
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Pnt,gp_Pln,gp_Ax3,gp_Dir
    from OCP.Geom import Geom_Plane
    from anygeometry.nurbs import NurbsSurface
    from anyfileio_occt._geometry import bspline_curve,surface_to_native
    support=surface_to_native(NurbsSurface(1,1,(0,0,1,1),(0,0,1,1),(((0,0,0),(0,1,0)),((1,0,0),(1,1,1)))))
    plane=Geom_Plane(gp_Pln(gp_Ax3(gp_Pnt(0,0,.5),gp_Dir(0,0,1),gp_Dir(1,0,0))))
    builder=BRep_Builder(); loc=TopLoc_Location()
    points={'a':(0,0,0),'b':(1,0,0),'c':(1,1,1),'d':(0,1,0),'p':(1,.5,.5),'q':(.5,1,.5),
        'A':(0,0,.5),'B':(1,0,.5),'C':(1,1,.5),'D':(0,1,.5)}
    vertices={key:BRepBuilderAPI_MakeVertex(gp_Pnt(*p)).Vertex() for key,p in points.items()}
    def line(a,b,s=None):
        e=BRepBuilderAPI_MakeEdge(vertices[a],vertices[b]).Edge()
        if s is not None:
            pc=bspline_curve([points[a][:2],points[b][:2]],1,(0,0,1,1),None,2)
            builder.UpdateEdge(e,pc,s,loc,1e-7)
            # Straight3D native line length parameter differs from PC unit range;
            # retain one common normalized full curve domain explicitly.
            curve=bspline_curve([points[a],points[b]],1,(0,0,1,1))
            builder.UpdateEdge(e,curve,1e-7); builder.Range(e,0.,1.); builder.Range(e,s,loc,0.,1.)
        return e
    controls=((.5,1,.5),(2/3,2/3,.5),(1,.5,.5)); weights=(.5,.75,1.)
    trace=BRepBuilderAPI_MakeEdge(bspline_curve(controls,2,(0,0,0,1,1,1),weights),vertices['q'],vertices['p'],0.,1.).Edge()
    for s in (support,plane):
        builder.UpdateEdge(trace,bspline_curve([p[:2] for p in controls],2,(0,0,0,1,1,1),weights,2),s,loc,1e-7)
        builder.Range(trace,s,loc,0.,1.)
    ab,bp,pc,cq,qd,da=[line(a,b,support) for a,b in ('ab','bp','pc','cq','qd','da')]
    AB,Bp,pC,Cq,qD,DA=[line(a,b) for a,b in ('AB','Bp','pC','Cq','qD','DA')]
    def face(s,items):
        w=BRepBuilderAPI_MakeWire()
        for e in items:w.Add(TopoDS.Edge_s(e))
        return BRepBuilderAPI_MakeFace(s,w.Wire(),True).Face()
    output=TopoDS_Compound(); builder.MakeCompound(output)
    for f in (face(support,[ab,bp,trace.Reversed(),qd,da]),face(support,[pc,cq,trace]),
              face(plane,[AB,Bp,trace.Reversed(),qD,DA]),face(plane,[pC,Cq,trace])):builder.Add(output,f)
    return output


def test_independent_native_rational_reference(tmp_path):
    from anyfileio_occt import _native
    from anygeometry.support_curves import PlaneNurbsCurve
    path=tmp_path/'native.brep'; _native.write_shape(native_four_faces(),path,'brep','m')
    with read(path,'m') as document:
        result=import_geometry(document,options=GeometryReadOptions(fidelity='approximate',max_deviation_m=.01,max_segments=20000))
    traces=[e for e in result.geometry.edges.values() if isinstance(e.curve,PlaneNurbsCurve)]
    assert len(traces)==1 and len(result.geometry.faces_using_edge(traces[0].id))==4
    assert len(result.geometry.faces)==4 and not result.geometry.validate_topology()


@pytest.mark.parametrize('unit,output',[('mm','m'),('m','mm')])
def test_physical_units(tmp_path,cached_section,unit,output):
    from anygeometry.serialization import from_dict,to_dict
    from anygeometry.support_curves import PlaneNurbsCurve
    model=from_dict(to_dict(cached_section[0])); model.set_document_settings(units=unit)
    scale=.001 if unit=='mm' else 1.; deviation=.01*scale
    path=tmp_path/'units.brep'
    report=write_geometry(path,model,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=deviation,max_segments=20000,output_length_unit=output))
    with read(path,output) as document:
        result=import_geometry(document,options=GeometryReadOptions(fidelity='approximate',max_deviation_m=deviation,max_segments=20000))
    assert all(a.bound_m<=deviation for a in (*report.approximations,*result.report.approximations))
    trace=next(e.curve for e in result.geometry.edges.values() if isinstance(e.curve,PlaneNurbsCurve))
    points=trace.evaluate(np.linspace(0,1,9))
    assert points[:,2]==pytest.approx(np.full(9,.5*scale),abs=1e-12)
    assert points[:,0]*points[:,1]==pytest.approx(np.full(9,.5*scale**2),abs=1e-12)


@pytest.mark.parametrize('face_index',[1,2,3,4])
def test_actual_every_incident_pcurve_checked(tmp_path,cached_section,monkeypatch,face_index):
    from OCP.BRep import BRep_Tool,BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt2d
    from anyfileio_occt._trim_bounds import _native_curve
    from anyfileio_occt import _native,_trim_bounds
    from anygeometry.serialization import to_dict
    model,_=cached_section; before=to_dict(model);path=tmp_path/'old.brep'; path.write_bytes(b'old'); original=_trim_bounds.verify_fitted_trims;called=[];mutated=[]
    def changed(*args,**kwargs):
        association=kwargs['association'];assert kwargs['topology'] is association.topology
        actual=association.topology[0];called.append(association)
        faces=_native.shape_map(actual,'face'); edges=_native.shape_map(actual,'edge')
        face=TopoDS.Face_s(faces.FindKey(face_index))
        for i in range(1,edges.Extent()+1):
            edge=TopoDS.Edge_s(edges.FindKey(i))
            incident=sum(_native.shape_map(faces.FindKey(j),'edge').Contains(edge) for j in range(1,faces.Extent()+1))
            if incident!=4: continue
            curve_before=_native_curve(edge)
            pc=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.).Copy()
            index=(pc.NbPoles()+1)//2
            p=pc.Pole(index); pc.SetPole(index,gp_Pnt2d(p.X()+.1,p.Y()+.1))
            BRep_Builder().UpdateEdge(edge,pc,face,1e-7)
            target=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.).Pole(index)
            assert (target.X(),target.Y())==(p.X()+.1,p.Y()+.1)
            assert _native_curve(edge)==curve_before
            mutated.append(face_index)
        assert mutated==[face_index]
        return original(*args,**kwargs)
    monkeypatch.setattr(_trim_bounds,'verify_fitted_trims',changed)
    with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
        write_geometry(path,model,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.01,max_segments=20000,max_depth=12))
    assert path.read_bytes()==b'old' and list(tmp_path.iterdir())==[path]
    assert to_dict(model)==before and len(called)==1 and called[0].document.closed


def test_postfile_cancellation(tmp_path,cached_section,monkeypatch):
    from anyfileio_occt import _trim_bounds
    from anyfileio.cad import CadOperationCancelled
    path=tmp_path/'old.brep'; path.write_bytes(b'old'); state={'stop':False}; original=_trim_bounds._box
    def box(*args):
        value=original(*args); state['stop']=True; return value
    monkeypatch.setattr(_trim_bounds,'_box',box)
    with pytest.raises(CadOperationCancelled):
        write_geometry(path,cached_section[0],options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.01),cancellation=lambda:state['stop'])
    assert path.read_bytes()==b'old' and list(tmp_path.iterdir())==[path]


def test_wrong_world_endpoints_refuse_after_public_parameter_proposal():
    from OCP.TopoDS import TopoDS
    from anygeometry import GeometryModel
    from anyfileio_occt import _native
    from anyfileio_occt.geometry_import import _bounded_section,surface_from_native
    from anyfileio_occt._trim_bounds import _Work
    shape=native_four_faces(); faces=_native.shape_map(shape,'face'); edges=_native.shape_map(shape,'edge')
    supports={i:surface_from_native(TopoDS.Face_s(faces.FindKey(i))) for i in range(1,5)}
    for i in range(1,edges.Extent()+1):
        edge=TopoDS.Edge_s(edges.FindKey(i))
        if not all(_native.shape_map(faces.FindKey(j),'edge').Contains(edge) for j in range(1,5)):continue
        # True interior section points, deliberately distinct from whole-path ends.
        endpoints=((.625,.8,.5),(.875,4/7,.5))
        with pytest.raises(GeometryInterchangeError,match='geometry.trim.parameter_inconclusive'):
            _bounded_section(edge,[1,2,3,4],supports,faces,endpoints,GeometryModel(),
                GeometryReadOptions(fidelity='approximate',max_deviation_m=.01,max_depth=48,max_segments=100000),None,_Work(100000))


@pytest.mark.parametrize('tamper',[False,True])
def test_distinct_coplanar_chart_and_only_its_pc(tmp_path,monkeypatch,tamper):
    from anygeometry.serialization import to_dict
    from anygeometry.support_curves import PlaneNurbsCurve
    from anygeometry.surfaces import Plane
    from anyfileio_occt import _native,_trim_bounds
    from anyfileio_occt.geometry_import import surface_from_native
    from OCP.BRep import BRep_Builder,BRep_Tool
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt2d
    from anyfileio_occt._trim_bounds import _native_curve
    model=section_model(different_frame=True); before=to_dict(model)
    path=tmp_path/'frame.brep'; path.write_bytes(b'old'); original=_trim_bounds.verify_fitted_trims; changed_count=[];called=[]
    def changed(*args,**kwargs):
        association=kwargs['association'];assert kwargs['topology'] is association.topology
        actual=association.topology[0];called.append(association)
        faces=_native.shape_map(actual,'face'); edges=_native.shape_map(actual,'edge')
        selected=[]
        for fi in range(1,faces.Extent()+1):
            face=TopoDS.Face_s(faces.FindKey(fi)); support=surface_from_native(face)
            if isinstance(support,Plane) and tuple(support.origin)==(1.,1.,.5):selected.append(face)
        assert len(selected)==1; face=selected[0]
        for ei in range(1,edges.Extent()+1):
            edge=TopoDS.Edge_s(edges.FindKey(ei))
            if sum(_native.shape_map(faces.FindKey(j),'edge').Contains(edge) for j in range(1,5))!=4:continue
            curve_before=_native_curve(edge)
            def pc_data(f):
                value=BRep_Tool.CurveOnSurface_s(edge,f,0.,0.)
                return tuple((value.Pole(k).X(),value.Pole(k).Y(),value.Weight(k)) for k in range(1,value.NbPoles()+1))
            others=[TopoDS.Face_s(faces.FindKey(j)) for j in range(1,5) if not faces.FindKey(j).IsSame(face)]
            other_before=[pc_data(f) for f in others]
            pc=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.).Copy()
            assert min(pc.Pole(k).X() for k in range(1,pc.NbPoles()+1))<0
            index=(pc.NbPoles()+1)//2; p=pc.Pole(index)
            pc.SetPole(index,gp_Pnt2d(p.X()+.1,p.Y()+.1)); BRep_Builder().UpdateEdge(edge,pc,face,1e-7)
            target=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.).Pole(index)
            assert (target.X(),target.Y())==(p.X()+.1,p.Y()+.1)
            assert _native_curve(edge)==curve_before
            assert [pc_data(f) for f in others]==other_before
            changed_count.append(ei)
        assert len(changed_count)==1
        return original(*args,**kwargs)
    if tamper:monkeypatch.setattr(_trim_bounds,'verify_fitted_trims',changed)
    options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.01,max_segments=20000,max_depth=12)
    if tamper:
        with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):write_geometry(path,model,options=options)
        assert path.read_bytes()==b'old' and list(tmp_path.iterdir())==[path]
        assert len(called)==1 and called[0].document.closed
    else:
        write_geometry(path,model,options=options)
        with read(path,'m') as document:
            result=import_geometry(document,options=GeometryReadOptions(fidelity='approximate',max_deviation_m=.01,max_segments=20000))
        trace=next(e for e in result.geometry.edges.values() if isinstance(e.curve,PlaneNurbsCurve))
        assert len(result.geometry.faces_using_edge(trace.id))==4
    assert to_dict(model)==before


def test_raw_brep_same_read_retention_and_session(tmp_path,monkeypatch):
    import hashlib
    import threading
    from anyfileio_occt import _native
    from anyfileio_occt.backend import document_raw_brep
    from anyfileio.cad import CadOperationError
    from anyfileio_occt import _trim_bounds
    from fractions import Fraction as Q
    path=tmp_path/'literal.brep'; _native.write_shape(native_four_faces(),path,'brep','mm')
    original=_native.read_shape; calls=[]
    def tracked(*args,**kwargs):
        calls.append(kwargs.get('raw_coordinates',False)); return original(*args,**kwargs)
    monkeypatch.setattr(_native,'read_shape',tracked)
    certify=_trim_bounds._certify; ratios=[]
    def literal_certificate(source,targets,source_ratio,target_ratio,*args):
        assert source_ratio==Q(1) and target_ratio==Q(1,1000)
        ratios.append(target_ratio)
        lo,hi=targets[0].bounds(0.,1.)
        assert max(hi)>500 # literal millimetres, not a second decoded metre copy
        return certify(source,targets,source_ratio,target_ratio,*args)
    monkeypatch.setattr(_trim_bounds,'_certify',literal_certificate)
    before=path.read_bytes(); digest=hashlib.sha256(before).hexdigest()
    with read(path,'mm') as document:
        raw,units=document_raw_brep(document)
        assert units.effective_unit=='mm' and calls==[True]
        assert document.manifest.source_sha256==digest
        bounds=_native.bounds(raw)
        path.write_bytes(b'changed after the completed single read')
        result=import_geometry(document,options=GeometryReadOptions(fidelity='approximate',max_deviation_m=.01,max_segments=20000))
        assert result.report.source_sha256==digest and calls==[True] and ratios
        assert _native.bounds(raw)==bounds
        errors=[]
        def wrong_thread():
            try:document_raw_brep(document)
            except CadOperationError as error:errors.append(error)
        thread=threading.Thread(target=wrong_thread); thread.start(); thread.join()
        assert len(errors)==1
        state=document._backend_state_for('occt')
    assert state.session.closed and not state.session._resources
    with pytest.raises(CadOperationError):document_raw_brep(document)


def test_literal_large_offset_unit_rounding_reference(tmp_path):
    """Acceptance must bound literal coefficients, even if normalization rounds."""
    from OCP.gp import gp_Trsf,gp_Vec
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from anyfileio_occt import _native
    from anyfileio_occt.backend import document_raw_brep,document_shape
    from anyfileio_occt._trim_bounds import _native_curve,_native_trim,_certify,_Work
    from anyfileio_occt._topology import compare,Work
    from anygeometry.support_curves import PlaneNurbsCurve
    from fractions import Fraction as Q
    from OCP.TopoDS import TopoDS
    import json
    move=gp_Trsf(); move.SetTranslation(gp_Vec(2**20,2**20,0))
    shape=BRepBuilderAPI_Transform(native_four_faces(),move,True).Shape()
    path=tmp_path/'offset.brep'; _native.write_shape(shape,path,'brep','cm'); before=path.read_bytes()
    opts=GeometryReadOptions(fidelity='approximate',max_deviation_m=.01,max_segments=20000)
    with read(path,'cm') as document:
        raw,units=document_raw_brep(document)
        canonical=document_shape(document)
        association=compare(raw,canonical,Q(1,100),Q(1),Work(opts.max_topology_work))
        raw_edges=_native.shape_map(raw,'edge'); faces=_native.shape_map(raw,'face')
        canonical_edges=_native.shape_map(canonical,'edge')
        rounding=[]
        for ri,(ci,reverse) in association.items():
            source=TopoDS.Edge_s(raw_edges.FindKey(ri))
            if sum(_native.shape_map(faces.FindKey(fi),'edge').Contains(source) for fi in range(1,5))!=4:continue
            literal=_native_curve(source); decoded=_native_curve(TopoDS.Edge_s(canonical_edges.FindKey(ci)),reverse)
            rounding.extend(Q(float(a))*Q(1,100)!=Q(float(b)) for p,q in zip(literal.controls,decoded.controls) for a,b in zip(p,q))
        assert any(rounding), 'fixture must actually discriminate binary64 unit normalization'
        try:result=import_geometry(document,options=opts)
        except GeometryInterchangeError as error:
            # Strict endpoint/chart representation limits may refuse. Never
            # silently certify only normalized geometry for this discriminator.
            assert path.read_bytes()==before
            (tmp_path/'raw-reference.json').write_text(json.dumps({'normalization_rounding':True,'decision':'typed_refusal','error':str(error)}))
            return
        records={r.source.id:r for r in result.report.approximations}
        for edge in result.geometry.edges.values():
            if not isinstance(edge.curve,PlaneNurbsCurve):continue
            actual=[]
            for ri in association:
                source=TopoDS.Edge_s(raw_edges.FindKey(ri)); incident=[TopoDS.Face_s(faces.FindKey(fi)) for fi in range(1,faces.Extent()+1) if _native.shape_map(faces.FindKey(fi),'edge').Contains(source)]
                if len(incident)!=4:continue
                reverse=association[ri][1]
                targets=[_native_curve(source,reverse)]+[_native_trim(source,f,reverse) for f in incident]
                actual.append(_certify(edge.curve,targets,Q(1),Q(1,100),opts,_Work(20000),None))
            assert len(actual)==1 and actual[0]<=records[edge.id].bound_m<=.01
        (tmp_path/'raw-reference.json').write_text(json.dumps({'normalization_rounding':True,'decision':'certified_literal_source','bounds':[r.bound_m for r in result.report.approximations]}))
    assert path.read_bytes()==before
