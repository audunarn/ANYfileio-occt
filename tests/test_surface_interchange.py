"""Real exact surface file round trips with independent analytical oracles."""
from pathlib import Path
import numpy as np
import pytest
pytest.importorskip('OCP')
from anyfileio.geometry import write_geometry,read_geometry,GeometryWriteOptions,GeometryReadOptions,GeometryInterchangeError
from anyfileio.cad import CadOperationCancelled


def grid_model(family,reverse=False,reverse_curves=True):
    from anygeometry import GeometryModel
    from anygeometry.entities import OrientedEdge
    from anygeometry.surfaces import RuledSurface,CoonsSurface
    if family=='ruled':
        first=np.array([(0,0,0),(1,0,.5),(2,0,0)],float)
        second=np.array([(0,2,1),(1,2,1.5),(2,2,1)],float)
        surface=RuledSurface(first,second)
        points=np.vstack((first,second[::-1]))
    else:
        bottom=np.array([(0,0,0),(1,0,.5),(2,0,0)],float)
        top=np.array([(0,2,0),(1,2,.5),(2,2,0)],float)
        left=np.array([(0,0,0),(0,1,.25),(0,2,0)],float)
        right=np.array([(2,0,0),(2,1,.25),(2,2,0)],float)
        surface=CoonsSurface(bottom,right,top,left)
        points=np.vstack((bottom,right[1:],top[-2::-1],left[-2:0:-1]))
    model=GeometryModel(); vertices=model.add_points(points); loop=[]
    for i,a in enumerate(vertices):
        b=vertices[(i+1)%len(vertices)]; backwards=reverse_curves and i%2==1
        edge=model.add_line(b,a) if backwards else model.add_line(a,b)
        loop.append(OrientedEdge(edge,not backwards))
    if reverse: loop=[OrientedEdge(e.edge,not e.forward) for e in reversed(loop)]
    model.add_face_from_loop(loop,surface=surface)
    return model


def analytical(family,u,v):
    return np.array((2*u,2*v,min(u,1-u)+(v if family=='ruled' else .5*min(v,1-v))))


@pytest.mark.parametrize('family',['ruled','coons'])
@pytest.mark.parametrize('fmt,unit',[('brep','mm')])
@pytest.mark.parametrize('reverse',[False,True])
def test_natural_grid_surface_files(tmp_path,family,fmt,unit,reverse):
    from anygeometry.serialization import to_dict
    model=grid_model(family,reverse); before=to_dict(model)
    path=tmp_path/(family+'.'+fmt)
    report=write_geometry(path,model,options=GeometryWriteOptions(output_length_unit=unit))
    result=read_geometry(path,options=GeometryReadOptions(source_length_unit_override=unit if fmt=='brep' else None))
    restored=result.geometry; surface=next(iter(restored.faces.values())).surface
    assert len(restored.faces)==1 and len(restored.edges)==len(model.edges)
    assert restored.validate_topology()==()
    for u,v in [(0.,0.),(.25,.25),(.5,.5),(.75,.75),(1.,1.)]:
        assert surface.evaluate(u,v)==pytest.approx(analytical(family,u,v),abs=1e-12,rel=0)
    assert not report.approximations
    assert to_dict(model)==before
    assert restored.model_id!=model.model_id


def ellipse_model(oblique=False,reverse_u=False,reverse_v=False,reverse_face=False,reverse_curves=False,vector_override=None):
    import math
    from anygeometry import GeometryModel
    from anygeometry.entities import OrientedEdge
    from anygeometry.surfaces import ExtrudedSurface
    from anygeometry.extrusions import EllipseDirectrix
    from anygeometry.exact_curves import EllipticArc
    u=(2,0,2) if oblique else (2,0,0); v=(.5,1,0) if oblique else (0,1,0)
    vector=vector_override if vector_override is not None else ((0,0,.25) if oblique else (0,0,2))
    ur=(.75,.25) if reverse_u else (.25,.75)
    vr=(.75,.25) if reverse_v else ((.25,.75) if oblique else (0.,1.))
    directrix=EllipseDirectrix((0,0,0),u,v,-math.pi/2,math.pi)
    surface=ExtrudedSurface(directrix,vector,ur,vr)
    start=directrix.start_angle+ur[0]*directrix.sweep_angle; sweep=(ur[1]-ur[0])*directrix.sweep_angle
    centers=[tuple(level*d for d in vector) for level in vr]
    profiles=[EllipticArc(c,u,v,start,sweep) for c in centers]
    model=GeometryModel(); a,b=model.add_points(profiles[0].evaluate(np.array([0.,1.])))
    c,d=model.add_points(profiles[1].evaluate(np.array([0.,1.])))
    if reverse_curves:
        low=model.add_curve(b,a,EllipticArc(centers[0],u,v,start+sweep,-sweep))
        high=model.add_curve(d,c,EllipticArc(centers[1],u,v,start+sweep,-sweep))
        right=model.add_line(d,b); left=model.add_line(c,a)
    else:
        low=model.add_curve(a,b,profiles[0]); high=model.add_curve(c,d,profiles[1])
        right=model.add_line(b,d); left=model.add_line(a,c)
    loop=[OrientedEdge(low,not reverse_curves),OrientedEdge(right,not reverse_curves),
        OrientedEdge(high,reverse_curves),OrientedEdge(left,reverse_curves)]
    if reverse_face: loop=[OrientedEdge(e.edge,not e.forward) for e in reversed(loop)]
    model.add_face_from_loop(loop,surface=surface)
    return model,surface


def conic_chart_angle(surface,q):
    import math
    start=surface.directrix.start_angle+surface.u_range[0]*surface.directrix.sweep_angle
    sweep=(surface.u_range[1]-surface.u_range[0])*surface.directrix.sweep_angle
    count=math.ceil(abs(sweep)/(math.pi/2)); scaled=q*count; index=min(int(scaled),count-1); local=scaled-index
    middle=start+sweep*(index+.5)/count
    return middle+2*math.atan((2*local-1)*math.tan(sweep/(4*count)))


@pytest.mark.parametrize('fmt,unit',[('brep','mm')])
@pytest.mark.parametrize('case',['ordinary','reversed','oblique','leaning'])
def test_elliptic_extrusion_files(tmp_path,fmt,unit,case):
    from anygeometry.serialization import to_dict
    model,source=ellipse_model(oblique=case=='oblique',reverse_u=case=='reversed',
        reverse_v=case=='reversed',reverse_face=case=='reversed',reverse_curves=True,
        vector_override=(.5,0,2) if case=='leaning' else None)
    before=to_dict(model); path=tmp_path/('ellipse.'+fmt)
    report=write_geometry(path,model,options=GeometryWriteOptions(output_length_unit=unit))
    restored=read_geometry(path,options=GeometryReadOptions(source_length_unit_override=unit if fmt=='brep' else None)).geometry
    actual=next(iter(restored.faces.values())).surface
    for q,r in [(0.,0.),(.25,.25),(.5,.5),(.75,.75),(1.,1.)]:
        theta=conic_chart_angle(source,q); level=source.v_range[0]+r*(source.v_range[1]-source.v_range[0])
        expected=np.array(source.directrix.center)+np.array(source.directrix.u_vector)*np.cos(theta)+np.array(source.directrix.v_vector)*np.sin(theta)+level*np.array(source.vector)
        assert actual.evaluate(q,r)==pytest.approx(expected,abs=1e-12,rel=0)
    assert len(restored.edges)==4 and len(restored.faces)==1 and restored.validate_topology()==()
    assert not report.approximations and to_dict(model)==before


def test_iges_binary64_digits_and_settings(tmp_path):
    from OCP.Interface import Interface_Static
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Pnt
    from anyfileio_occt import _native
    from test_native_geometry import read
    x=float(np.sqrt(2));shape=BRepBuilderAPI_MakeEdge(gp_Pnt(0,0,0),gp_Pnt(x,0,0)).Edge()
    path=tmp_path/'first-operation.iges';_native.write_shape(shape,path,'iges','cm')
    effective_prior=Interface_Static.CVal_s('xstep.cascade.unit')
    from anyfileio_occt.backend import document_shape
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopoDS import TopoDS
    with read(path) as doc:
        curve=BRepAdaptor_Curve(TopoDS.Edge_s(_native.shape_map(document_shape(doc),'edge').FindKey(1)))
        end=curve.Value(curve.LastParameter())
        assert (end.X(),end.Y(),end.Z())==pytest.approx((x,0,0),abs=1e-12,rel=0)
    _native.write_shape(shape,tmp_path/'second.iges','iges','mm')
    assert Interface_Static.CVal_s('xstep.cascade.unit')==effective_prior


def _loop_vector(model):
    face=next(iter(model.faces.values()))
    points=[model.vertices[model.edges[e.edge].start if e.forward else model.edges[e.edge].end].position for e in face.loop]
    return sum((np.cross(a,b) for a,b in zip(points,points[1:]+points[:1])),np.zeros(3))


def _loop_points(model):
    face=next(iter(model.faces.values()))
    return np.array([model.vertices[model.edges[e.edge].start if e.forward else model.edges[e.edge].end].position for e in face.loop])


@pytest.mark.parametrize('family',['ruled','coons','ellipse'])
@pytest.mark.parametrize('fmt',['brep'])
def test_public_reverse_face_preserves_normal_and_loop(tmp_path,family,fmt):
    from anygeometry import reverse_face
    from anygeometry.surfaces import surface_normal
    if family=='ellipse': model,original=ellipse_model()
    else:
        model=grid_model(family); original=next(iter(model.faces.values())).surface
    original_loop=_loop_vector(model)
    reverse_face(model,next(iter(model.faces)))
    source=next(iter(model.faces.values())).surface
    # Rational conic q and angular owner u differ away from midpoint/endpoints.
    source_u=.25
    if family=='ellipse':
        theta=conic_chart_angle(source,.25)
        directrix_u=(theta-source.directrix.start_angle)/source.directrix.sweep_angle
        source_u=(directrix_u-source.u_range[0])/(source.u_range[1]-source.u_range[0])
    original_normal=surface_normal(original,1-source_u,.25)
    expected_normal=surface_normal(source,source_u,.25)
    assert expected_normal==pytest.approx(-original_normal,abs=1e-12,rel=0)
    assert _loop_vector(model)==pytest.approx(-original_loop,abs=1e-12,rel=0)
    path=tmp_path/('public-reverse.'+fmt)
    write_geometry(path,model)
    restored=read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m' if fmt=='brep' else None)).geometry
    actual=next(iter(restored.faces.values())).surface
    # Public analytical NURBS derivatives avoid the generic surface_normal
    # protocol fallback's finite differences; the acceptance stays1e-12.
    du,dv=actual.derivatives_many(np.array([[.25,.25]])); normal=np.cross(du[0],dv[0]); normal/=np.linalg.norm(normal)
    assert normal==pytest.approx(expected_normal,abs=1e-12,rel=0)
    # Compare orientation dimensionlessly and coordinates in metres. An area
    # vector is measured in m² and amplifies independently rounded vertex data.
    actual_loop=_loop_vector(restored); expected_loop=-original_loop
    assert actual_loop/np.linalg.norm(actual_loop)==pytest.approx(expected_loop/np.linalg.norm(expected_loop),abs=1e-12,rel=0)
    expected_points=_loop_points(model); actual_points=_loop_points(restored)
    assert len(actual_points)==len(expected_points)
    cyclic_error=min(np.max(np.abs(np.roll(actual_points,i,axis=0)-expected_points)) for i in range(len(actual_points)))
    assert cyclic_error<=1e-12


@pytest.mark.parametrize('family',['ruled','coons'])
def test_split_boundary_inside_grid_cell(tmp_path,family):
    model=grid_model(family); first=next(iter(model.edges))
    model.split_edge(first,.25)
    path=tmp_path/'split.brep'; write_geometry(path,model)
    restored=read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m')).geometry
    assert len(restored.edges)==len(model.edges) and restored.validate_topology()==()
    actual=next(iter(restored.faces.values())).surface
    assert actual.evaluate(.25,.25)==pytest.approx(analytical(family,.25,.25),abs=1e-12,rel=0)


@pytest.mark.parametrize('family',['ruled','coons','ellipse'])
def test_source_millimetres_preserve_native_chart_ranges(tmp_path,family):
    from anygeometry.serialization import to_dict
    from anyfileio.cad_operations import read_cad
    from anyfileio.cad import CadReadOptions
    from anyfileio_occt.backend import document_shape
    from anyfileio_occt import _native
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    if family=='ellipse': model,source=ellipse_model()
    else: model=grid_model(family); source=None
    model.set_document_settings(units='mm'); before=to_dict(model)
    path=tmp_path/'source-mm.brep'; report=write_geometry(path,model,options=GeometryWriteOptions(output_length_unit='m'))
    restored=read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m')).geometry
    actual=next(iter(restored.faces.values())).surface
    if source is None: expected=analytical(family,.25,.25)
    else:
        theta=conic_chart_angle(source,.25)
        expected=np.array(source.directrix.u_vector)*np.cos(theta)+np.array(source.directrix.v_vector)*np.sin(theta)+.25*np.array(source.vector)
    assert actual.evaluate(.25,.25)==pytest.approx(expected*.001,abs=1e-12,rel=0)
    assert report.source_unit=='mm' and to_dict(model)==before
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as document:
        shape=document_shape(document); face=TopoDS.Face_s(_native.shape_map(shape,'face').FindKey(1)); surface=BRep_Tool.Surface_s(face)
        edges=_native.shape_map(face,'edge')
        for i in range(1,edges.Extent()+1):
            edge=TopoDS.Edge_s(edges.FindKey(i)); curve=BRepAdaptor_Curve(edge)
            pc=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.); first,last=BRep_Tool.Range_s(edge,face)
            assert (first,last)==pytest.approx((curve.FirstParameter(),curve.LastParameter()),abs=1e-12,rel=0)
            for fraction in (0.,.5,1.):
                uv=pc.Value(first+fraction*(last-first)); p=surface.Value(uv.X(),uv.Y()); q=curve.Value(curve.FirstParameter()+fraction*(curve.LastParameter()-curve.FirstParameter()))
                assert (p.X(),p.Y(),p.Z())==pytest.approx((q.X(),q.Y(),q.Z()),abs=1e-12,rel=0)


@pytest.mark.parametrize('family',['ruled','coons','ellipse'])
def test_surface_boundary_refusal_is_atomic(tmp_path,family):
    from anygeometry import GeometryModel
    from anygeometry.surfaces import RuledSurface,CoonsSurface
    from anygeometry.serialization import to_dict
    if family=='ellipse':
        model,source=ellipse_model(vector_override=(2,0,2))
        expected='geometry.exact.coefficient_unrepresentable'
    else:
        model=GeometryModel(); vertices=model.add_points([(0,0,0),(2,0,0),(2,2,0),(0,2,0)])
        surface=RuledSurface([(-1,-1,0),(3,-1,0)],[(-1,3,0),(3,3,0)]) if family=='ruled' else CoonsSurface(
            np.array([(-1,-1,0),(3,-1,0)]),np.array([(3,-1,0),(3,3,0)]),
            np.array([(-1,3,0),(3,3,0)]),np.array([(-1,-1,0),(-1,3,0)]))
        model.add_face(model.add_polyline(vertices,close=True),surface=surface)
        expected='geometry.trim.chart_unavailable'
    before=to_dict(model); path=tmp_path/'preserve.brep'; path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match=expected): write_geometry(path,model)
    assert path.read_bytes()==b'old' and list(tmp_path.iterdir())==[path]
    assert to_dict(model)==before


@pytest.mark.parametrize('family',['ruled','coons','ellipse'])
def test_surface_chart_cancellation_is_atomic(tmp_path,monkeypatch,family):
    from anyfileio_occt import _surface_trims
    from anygeometry.serialization import to_dict
    model=ellipse_model()[0] if family=='ellipse' else grid_model(family)
    before=to_dict(model); path=tmp_path/'preserve.brep'; path.write_bytes(b'old')
    state={'stop':False}; real=_surface_trims.bspline_curve
    def created(*args,**kwargs):
        result=real(*args,**kwargs); state['stop']=True; return result
    monkeypatch.setattr(_surface_trims,'bspline_curve',created)
    with pytest.raises(CadOperationCancelled): write_geometry(path,model,cancellation=lambda:state['stop'])
    assert path.read_bytes()==b'old' and list(tmp_path.iterdir())==[path]
    assert to_dict(model)==before


@pytest.mark.parametrize('operation',['failure','cancellation'])
def test_iges_object_precision_and_unit_guard_failure_paths(tmp_path,monkeypatch,operation):
    import OCP.IGESData as data
    from OCP.IGESControl import IGESControl_Controller
    from OCP.Interface import Interface_Static
    from anyfileio.cad import CadOperationError
    IGESControl_Controller.Init_s(); previous=Interface_Static.CVal_s('xstep.cascade.unit')
    real=data.IGESData_IGESWriter; formats=[]; state={'stop':False}
    class Serializer:
        def __init__(self,model):
            self.actual=real(model); formats.append(self.actual.FloatWriter().MainFormat())
        def FloatWriter(self): return self.actual.FloatWriter()
        def SendModel(self,protocol): self.actual.SendModel(protocol)
        def Print(self,stream):
            assert self.actual.FloatWriter().MainFormat()=='%.16E'
            if operation=='failure': return False
            result=self.actual.Print(stream); state['stop']=True; return result
    monkeypatch.setattr(data,'IGESData_IGESWriter',Serializer)
    from test_native_geometry import native_panel_shape
    from anyfileio_occt import _native
    path=tmp_path/'native.iges'
    expected=CadOperationError if operation=='failure' else CadOperationCancelled
    with pytest.raises(expected): _native.write_shape(native_panel_shape(),path,'iges','m',cancellation=lambda:state['stop'])
    assert Interface_Static.CVal_s('xstep.cascade.unit')==previous
    assert formats and formats[0]!='%.16E'


@pytest.mark.parametrize('fmt',['brep'])
def test_coons_different_boundary_resolutions_chart_extrapolation_refuses(tmp_path,fmt):
    from anygeometry import GeometryModel
    from anygeometry.surfaces import CoonsSurface
    bottom=np.array([(2*u,0,min(u,1-u)) for u in (0.,.5,1.)])
    top=np.array([(2*u,2,min(u,1-u)) for u in (0.,.25,.5,.75,1.)])
    left=np.array([(0,2*v,.5*min(v,1-v)) for v in (0.,.5,1.)])
    right=np.array([(2,2*v,.5*min(v,1-v)) for v in (0.,.25,.5,.75,1.)])
    support=CoonsSurface(bottom,right,top,left)
    points=np.vstack((bottom,right[1:],top[-2::-1],left[-2:0:-1]))
    model=GeometryModel(); vertices=model.add_points(points)
    model.add_face(model.add_polyline(vertices,close=True),surface=support)
    from anygeometry.serialization import to_dict
    for u,v in [(.125,.375),(.375,.625),(.625,.125),(.875,.875)]:
        assert support.evaluate(u,v)==pytest.approx(analytical('coons',u,v),abs=1e-12,rel=0)
    before=to_dict(model);path=tmp_path/('different-grids.'+fmt);path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.precision.unproved'):
        write_geometry(path,model,options=GeometryWriteOptions(max_topology_work=5000000))
    assert path.read_bytes()==b'old' and to_dict(model)==before and model.validate_topology()==()


def test_different_ruled_supports_preserve_shared_cad_edge_and_refuse_unproved_import(tmp_path):
    from anygeometry import GeometryModel
    from anygeometry.entities import OrientedEdge
    from anygeometry.surfaces import RuledSurface
    from anyfileio.cad_operations import read_cad
    from anyfileio.cad import CadReadOptions
    model=GeometryModel()
    rows=[[(0,0,0),(1,0,.5),(2,0,0)],[(0,2,1),(1,2,1.5),(2,2,1)],[(0,4,0),(1,4,.5),(2,4,0)]]
    ids=[model.add_points(row) for row in rows]
    horizontal=[[model.add_line(row[i],row[i+1]) for i in range(2)] for row in ids]
    left=[model.add_line(ids[j][0],ids[j+1][0]) for j in range(2)]
    right=[model.add_line(ids[j][2],ids[j+1][2]) for j in range(2)]
    for j in range(2):
        loop=([OrientedEdge(e,True) for e in horizontal[j]]+[OrientedEdge(right[j],True)]+
            [OrientedEdge(e,False) for e in reversed(horizontal[j+1])]+[OrientedEdge(left[j],False)])
        model.add_face_from_loop(loop,surface=RuledSurface(rows[j],rows[j+1]))
    path=tmp_path/'shared.brep'; write_geometry(path,model)
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as document:
        assert document.manifest.topology_counts['edge']==10
        assert document.manifest.topology_counts['vertex']==9
        assert document.manifest.topology_counts['face']==2
    with pytest.raises(GeometryInterchangeError,match='geometry.trim.shared_support_unsupported'):
        read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m'))



@pytest.mark.parametrize('family',['ruled','coons','ellipse'])
@pytest.mark.parametrize('fmt',['step','iges'])
def test_surface_staged_format_refusal(tmp_path,family,fmt):
    from test_native_geometry import assert_staged_refusal
    model=ellipse_model()[0] if family=='ellipse' else grid_model(family)
    assert_staged_refusal(tmp_path/('surface.'+fmt),model)
