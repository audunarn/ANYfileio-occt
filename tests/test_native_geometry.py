"""Real native round trips and refusal paths; no native mocks."""
from pathlib import Path
import numpy as np
import pytest
pytest.importorskip('OCP')
from anyfileio.cad import CadReadOptions,CadTessellationOptions,CadWriteOptions,CadOperationError,CadOperationCancelled
from anyfileio.geometry import GeometryWriteOptions,GeometryReadOptions,GeometryInterchangeError
from anyfileio_occt import _native as native
from anyfileio_occt.backend import get_backend
from anyfileio_occt.geometry_export import export_geometry
from anyfileio_occt.geometry_import import import_geometry

def read(path,unit=None,mode='live'):
    from anyfileio.cad_operations import read_cad
    return read_cad(path,options=CadReadOptions(mode=mode,retain_source=False,
        source_length_unit_override=unit))

@pytest.mark.parametrize('fmt,unit',[('step','mm'),('step','m'),('iges','mm'),('iges','m'),('brep','mm')])
def test_native_units_roundtrip(tmp_path,fmt,unit):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    p=tmp_path/('box.'+fmt)
    native.write_shape(BRepPrimAPI_MakeBox(1.,2.,3.).Shape(),p,fmt,unit)
    with read(p,unit if fmt=='brep' else None) as d:
        assert d.manifest.world_bounds_m==pytest.approx((0,0,0,1,2,3),abs=1e-10)
        assert d.manifest.topology_counts['solid']==1
        meshes=get_backend().tessellate(d,options=CadTessellationOptions(include_edges=True))
        t=meshes[0].tessellation
        assert len(t.triangles)==12
        assert len(t.face_owners)==6 and len(t.edge_owners)==12
        with pytest.raises(GeometryInterchangeError,match='geometry.solid.unsupported'):
            import_geometry(d,options=GeometryReadOptions())

def square():
    from anygeometry import GeometryModel
    m=GeometryModel()
    v=[m.add_point(*p) for p in [(0,0,0),(2,0,0),(2,1,0),(0,1,0)]]
    m.add_face(m.add_polyline(v,close=True))
    return m

@pytest.mark.parametrize('fmt',['brep'])
def test_editable_square_roundtrip(tmp_path,fmt):
    m=square(); revision=m.revision; p=tmp_path/('square.'+fmt)
    report=export_geometry(m,p,options=GeometryWriteOptions(output_length_unit='mm'))
    assert m.revision==revision and report.source_model_id==m.model_id
    with read(p,'mm' if fmt=='brep' else None) as d:
        result=import_geometry(d,options=GeometryReadOptions())
    g=result.geometry
    assert g.model_id!=m.model_id
    assert len(g.edges)==4 and len(g.faces)==1
    assert g.validate_topology()==()
    assert np.ptp(np.array([v.position for v in g.vertices.values()]),axis=0)==pytest.approx((2,1,0),abs=1e-10)
    assert len(report.geometry_to_cad)==9
    with pytest.raises(TypeError): report.geometry_to_cad['x']='y'

def test_holes_import_export(tmp_path):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Pnt
    def loop(points):
        p=BRepBuilderAPI_MakePolygon()
        for x,y in points: p.Add(gp_Pnt(x,y,0))
        p.Close(); return p.Wire()
    maker=BRepBuilderAPI_MakeFace(loop([(0,0),(4,0),(4,4),(0,4)]),True)
    maker.Add(loop([(1,1),(1,2),(2,2),(2,1)]))
    p=tmp_path/'hole.step'; native.write_shape(maker.Face(),p,'step')
    with read(p,'m') as d: result=import_geometry(d,options=GeometryReadOptions())
    assert len(next(iter(result.geometry.faces.values())).holes)==1
    q=tmp_path/'hole-again.brep'; export_geometry(result.geometry,q,options=GeometryWriteOptions())
    with read(q,'m') as d: again=import_geometry(d,options=GeometryReadOptions())
    assert len(next(iter(again.geometry.faces.values())).holes)==1

def test_shared_edges_are_identity_based(tmp_path):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    from OCP.gp import gp_Pnt
    # Two coincident independent CAD faces remain independent; no coordinate weld.
    def face():
        p=BRepBuilderAPI_MakePolygon()
        for xy in [(0,0),(1,0),(1,1),(0,1)]: p.Add(gp_Pnt(*xy,0))
        p.Close(); return BRepBuilderAPI_MakeFace(p.Wire()).Face()
    b=BRep_Builder(); s=TopoDS_Compound(); b.MakeCompound(s); b.Add(s,face()); b.Add(s,face())
    p=tmp_path/'coincident.brep'; native.write_shape(s,p,'brep')
    with read(p,'m') as d: g=import_geometry(d,options=GeometryReadOptions()).geometry
    assert len(g.vertices)==8 and len(g.edges)==8 and len(g.faces)==2

def test_free_curve_families(tmp_path):
    from anygeometry import GeometryModel
    from anygeometry.exact_curves import EllipticArc
    from anygeometry.nurbs import NurbsCurve
    m=GeometryModel()
    a=m.add_point(0,0,0); b=m.add_point(1,0,0); c=m.add_point(.5,1,0)
    m.add_arc(a,c,b)
    m.add_spline(a,[c],b)
    curve=NurbsCurve(2,(0,0,0,1,1,1),((0,0,0),(.5,.4,0),(1,0,0)),(1,.7,1))
    m.add_curve(a,b,curve)
    p=tmp_path/'curves.brep'; export_geometry(m,p,options=GeometryWriteOptions())
    with read(p,'m') as d:
        assert d.manifest.topology_counts['edge']==3
        assert d.manifest.topology_counts['vertex']==3
        result=import_geometry(d,options=GeometryReadOptions()); g=result.geometry
    assert len(g.edges)==3
    endpoints={v for edge in g.edges.values() for v in (edge.start,edge.end)}
    assert len(endpoints)==2
    assert all({edge.start,edge.end}==endpoints for edge in g.edges.values())
    native_vertices=[h for ref,handles in result.report.cad_to_geometry.items() if ref.kind=='vertex' for h in handles]
    assert len(native_vertices)==3
    retained=[h for h in native_vertices if np.array_equal(g.vertices[h.id].position,(.5,1,0))]
    assert len(retained)==1 and retained[0].id not in endpoints
    # Importing an analytic CAD circle adds one owner Arc control. It must not
    # coordinate-weld that generated control to the independent CAD point.
    arc=next(edge.curve for edge in g.edges.values() if hasattr(edge.curve,'via_vertex'))
    assert arc.via_vertex!=retained[0].id
    assert g.vertices[arc.via_vertex].position==pytest.approx((.5,1,0),abs=1e-12,rel=0)
    assert g.validate_topology()==()

def test_unknown_brep_units_refused(tmp_path):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    p=tmp_path/'box.brep'; native.write_shape(BRepPrimAPI_MakeBox(1,1,1).Shape(),p,'brep')
    with pytest.raises(CadOperationError,match='cad.units.required'): read(p)

def test_cancellation_and_external_refusal(tmp_path):
    m=square(); p=tmp_path/'cancel.step'
    with pytest.raises(CadOperationCancelled): export_geometry(m,p,options=GeometryWriteOptions(),cancellation=lambda:True)
    assert not p.exists()
    with pytest.raises(GeometryInterchangeError,match='geometry.external_transform_undefined'):
        export_geometry(m,p,options=GeometryWriteOptions(coordinate_space='external'))
    assert not p.exists()

def test_actual_shared_edge_survives(tmp_path):
    from anygeometry import GeometryModel
    from anygeometry.surfaces import Plane
    m=GeometryModel(); vs=[m.add_point(*p) for p in [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(2,0,0),(2,1,0)]]
    a,b,c,d,e,f=vs
    ab=m.add_line(a,b); bc=m.add_line(b,c); cd=m.add_line(c,d); da=m.add_line(d,a)
    be=m.add_line(b,e); ef=m.add_line(e,f); fc=m.add_line(f,c)
    plane=Plane((0,0,0),(1,0,0),(0,1,0))
    m.add_face([ab,bc,cd,da],surface=plane)
    m.add_face([be,ef,fc,bc],surface=plane)
    p=tmp_path/'shared.brep'; export_geometry(m,p,options=GeometryWriteOptions())
    with read(p,'m') as doc: g=import_geometry(doc,options=GeometryReadOptions()).geometry
    assert len(g.vertices)==6 and len(g.edges)==7 and len(g.faces)==2
    assert sorted(len(g.faces_using_edge(eid)) for eid in g.edges)==[1,1,1,1,1,1,2]

def test_non_metre_surface_inch_chart_extrapolation_refuses_atomically(tmp_path):
    from anygeometry.serialization import to_dict
    from anyfileio.geometry import GeometryInterchangeError
    m=square(); m.set_document_settings(units='mm')
    before=to_dict(m);p=tmp_path/'millimetres.brep';p.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.precision.unproved'):
        export_geometry(m,p,options=GeometryWriteOptions(output_length_unit='in'))
    assert p.read_bytes()==b'old' and to_dict(m)==before

def test_conservative_curve_bound_and_budget():
    from anygeometry.nurbs import NurbsCurve
    from anyfileio_occt._geometry import bounded_polyline
    from anygeometry.entities import EntityRef
    c=NurbsCurve(2,(0,0,0,1,1,1),((0,0,0),(.5,.1,0),(1,0,0)))
    opts=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.1,max_segments=128)
    segments,report=bounded_polyline(c,opts,EntityRef('edge',1))
    assert len(segments)>1 and report.bound_m<=.1
    for a,b,p,q in segments:
        points=c.evaluate(np.linspace(a,b,11))
        assert max(np.linalg.norm(x-p) for x in points)<=report.bound_m
    with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
        bounded_polyline(c,GeometryWriteOptions(fidelity='approximate',max_deviation_m=1e-9,max_segments=2),EntityRef('edge',1))

def test_closed_circle_is_split_without_coordinate_welding(tmp_path):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Circ,gp_Ax2,gp_Pnt,gp_Dir
    s=BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(0,0,0),gp_Dir(0,0,1)),1)).Edge()
    p=tmp_path/'circle.brep'; native.write_shape(s,p,'brep')
    with read(p,'m') as d: g=import_geometry(d,options=GeometryReadOptions()).geometry
    assert len(g.edges)==4 and g.validate_topology()==()

def test_nurbs_patch_exact_trim_roundtrip(tmp_path):
    from anygeometry import GeometryModel
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    s=NurbsSurface(1,1,(0,0,1,1),(0,0,1,1),(((0,0,0),(0,1,.2)),((1,0,0),(1,1,0))))
    m=GeometryModel(); uv=[(0.,0.),(1.,0.),(1.,1.),(0.,1.)]
    vs=[m.add_point(*s.evaluate(*p)) for p in uv]; es=[]
    for i in range(4):
        pc=NurbsCurve(1,(0,0,1,1),(uv[i],uv[(i+1)%4]))
        es.append(m.add_curve(vs[i],vs[(i+1)%4],CurveOnSurface(s,pc)))
    m.add_face(es,surface=s)
    p=tmp_path/'patch.brep'; export_geometry(m,p,options=GeometryWriteOptions())
    with read(p,'m') as d: g=import_geometry(d,options=GeometryReadOptions()).geometry
    assert len(g.faces)==1 and g.validate_topology()==()
    assert isinstance(next(iter(g.faces.values())).surface,NurbsSurface)

def test_translation_modes_and_closed_session(tmp_path):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    p=tmp_path/'source.step'; native.write_shape(BRepPrimAPI_MakeBox(1,2,3).Shape(),p,'step')
    for mode in ['manifest_only','preview']:
        d=read(p,mode=mode)
        assert d.manifest.topology_counts['face']==6
        if mode=='preview': assert len(d.tessellation.prototype_meshes)==1
        d.close()
    with read(p) as d:
        target=tmp_path/'translated.iges'
        report=get_backend().translate(d,target,options=CadWriteOptions(mode='translate',target_format='iges',target_length_unit='cm'))
        assert report.output_sha256==native.digest(target)
        with read(target) as output: assert output.manifest.world_bounds_m==pytest.approx((0,0,0,1,2,3),abs=1e-10)
    with pytest.raises(CadOperationError,match='cad.session.required'):
        get_backend().tessellate(d,options=CadTessellationOptions())

def test_declared_part_sheet_member_export(tmp_path):
    m=square(); part=m.add_part(name='panel'); m.add_sheet([1],part_id=part)
    a=m.add_point(3,0,0); b=m.add_point(4,0,0); e=m.add_line(a,b)
    m.add_member([e],part_id=part)
    p=tmp_path/'structural.brep'; export_geometry(m,p,options=GeometryWriteOptions())
    with read(p,'m') as d:
        assert d.manifest.topology_counts['shell']==1
        assert d.manifest.topology_counts['face']==1
        assert d.manifest.topology_counts['edge']==5

def test_owner_change_during_conversion_refused(tmp_path):
    m=square(); p=tmp_path/'changed.brep'; calls=[0]
    def cancelled():
        calls[0]+=1
        if calls[0]==3: m.add_point(5,5,5)
        return False
    with pytest.raises(GeometryInterchangeError,match='geometry.revision.changed'):
        export_geometry(m,p,options=GeometryWriteOptions(),cancellation=cancelled)
    assert not p.exists()

def test_native_session_thread_affinity(tmp_path):
    import concurrent.futures
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    p=tmp_path/'thread.step'; native.write_shape(BRepPrimAPI_MakeBox(1,1,1).Shape(),p,'step')
    with read(p) as d:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(get_backend().tessellate,d,options=CadTessellationOptions())
            with pytest.raises(CadOperationError,match='cad.session.wrong_thread'): future.result()

def test_reversed_pcurve_domain(tmp_path):
    from anygeometry import GeometryModel
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    s=NurbsSurface(1,1,(0,0,1,1),(0,0,1,1),(((0,0,0),(0,1,.2)),((1,0,0),(1,1,0))))
    m=GeometryModel(); uv=[(0.,0.),(1.,0.),(1.,1.),(0.,1.)]
    vs=[m.add_point(*s.evaluate(*p)) for p in uv]; es=[]
    for i in range(4):
        pc=NurbsCurve(1,(0,0,1,1),(uv[(i+1)%4],uv[i]),domain=(1,0))
        es.append(m.add_curve(vs[i],vs[(i+1)%4],CurveOnSurface(s,pc)))
    m.add_face(es,surface=s)
    p=tmp_path/'reversed.brep'; export_geometry(m,p,options=GeometryWriteOptions())
    with read(p,'m') as d: g=import_geometry(d,options=GeometryReadOptions()).geometry
    assert len(g.faces)==1 and g.validate_topology()==()

def test_exact_native_bezier_extrusion_import_reexport(tmp_path):
    from anyfileio_occt._geometry import bspline_curve
    from OCP.Geom import Geom_SurfaceOfLinearExtrusion
    from OCP.gp import gp_Dir
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    surface=Geom_SurfaceOfLinearExtrusion(bspline_curve([(0,0,0),(.5,.4,0),(1,0,0)],2,[0,0,0,1,1,1]),gp_Dir(0,0,1))
    face=BRepBuilderAPI_MakeFace(surface,0.,1.,0.,2.,1e-9).Face()
    p=tmp_path/'extrusion.brep'; native.write_shape(face,p,'brep')
    with read(p,'m') as d: result=import_geometry(d,options=GeometryReadOptions())
    assert result.geometry.validate_topology()==()
    q=tmp_path/'extrusion-again.brep'; export_geometry(result.geometry,q,options=GeometryWriteOptions())
    with read(q,'m') as d: again=import_geometry(d,options=GeometryReadOptions()).geometry
    # Manifest bounds are conservative OCCT boxes (including kernel gaps),
    # so compare the actual support coordinates for the geometric criterion.
    support=next(iter(again.faces.values())).surface
    for u,v in [(0.,0.),(.5,.5),(1.,1.)]:
        assert support.evaluate(u,v)==pytest.approx((u,.8*u*(1-u),2*v),abs=1e-12)

def test_bound_norm_handles_subnormal_and_huge():
    from anyfileio_occt._geometry import bounded_polyline
    from anygeometry.entities import EntityRef
    class Small:
        def evaluate(self,t): return np.stack([t*1e-200,np.zeros_like(t),np.zeros_like(t)],axis=-1)
        def bounds(self,a,b): return ((a*1e-200,0,0),(b*1e-200,0,0))
    result,report=bounded_polyline(Small(),GeometryWriteOptions(fidelity='approximate',max_deviation_m=1e-199),EntityRef('edge',1))
    assert report.bound_m>=1e-200
    class Huge:
        def evaluate(self,t): return np.zeros(np.shape(t)+(3,))
        def bounds(self,a,b): return ((-1e308,-1e308,0),(1e308,1e308,0))
    with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
        bounded_polyline(Huge(),GeometryWriteOptions(fidelity='approximate',max_deviation_m=1e308,max_depth=1),EntityRef('edge',1))

def test_specialized_curve_bounded_file_export(tmp_path):
    from anygeometry import GeometryModel,Cylinder,CylinderIntersectionCurve
    first=Cylinder((0,0,0),(0,0,1),(1,0,0),1,5)
    second=Cylinder((0,0,0),(0,1,0),(1,0,0),2,5)
    curve=CylinderIntersectionCurve(first,second,.2,1.2,1)
    m=GeometryModel(); a,b=m.add_points(curve.evaluate(np.array([0.,1.]))); m.add_curve(a,b,curve)
    p=tmp_path/'branch.brep'
    with pytest.raises(GeometryInterchangeError,match='geometry.exact.unsupported'):
        export_geometry(m,p,options=GeometryWriteOptions())
    assert not p.exists()
    report=export_geometry(m,p,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.1,max_segments=512,max_topology_work=5000000))
    assert len(report.approximations)==1
    assert report.approximations[0].bound_m<=.1
    assert 'reread CAD endpoint enclosure' in report.approximations[0].method
    # Editable STEP has no proved source-to-file record association.
    step=tmp_path/'branch.step'; step.write_bytes(b'preserved')
    with pytest.raises(GeometryInterchangeError,match='geometry.association_unproved'):
        export_geometry(m,step,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.1,max_segments=512))
    assert step.read_bytes()==b'preserved'


def test_general_nonplanar_composition_never_fits_silently(tmp_path):
    from anygeometry import GeometryModel
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    s=NurbsSurface(1,1,(0,0,1,1),(0,0,1,1),(((0,0,0),(0,1,.2)),((1,0,0),(1,1,0))))
    c=CurveOnSurface(s,NurbsCurve(1,(0,0,1,1),((0,0),(1,1))))
    m=GeometryModel(); a,b=m.add_points(c.evaluate(np.array([0.,1.]))); m.add_curve(a,b,c)
    with pytest.raises(GeometryInterchangeError,match='geometry.exact.composition_unavailable'):
        export_geometry(m,tmp_path/'composition.brep',options=GeometryWriteOptions())

@pytest.mark.parametrize('kind',['cylinder','cone'])
def test_analytic_patch_trim_chart_and_interior(tmp_path,kind):
    from anygeometry import GeometryModel,Cylinder,Cone,OrientedEdge
    import math
    m=GeometryModel()
    s=Cylinder((0,0,0),(0,0,1),(1,0,0),2.,3.,.2,math.pi/2) if kind=='cylinder' else Cone((0,0,0),(0,0,1),(1,0,0),2.,3.,4.,.2,math.pi/2)
    lower=m.add_points(s.evaluate(u,0) for u in (0,.5,1)); upper=m.add_points(s.evaluate(u,1) for u in (0,.5,1))
    es=(m.add_arc(*lower),m.add_line(lower[-1],upper[-1]),m.add_arc(*upper),m.add_line(lower[0],upper[0]))
    m.add_face_from_loop(tuple(OrientedEdge(e,f) for e,f in zip(es,(True,True,False,False))),(0,1,2,3),surface=s)
    p=tmp_path/(kind+'.brep'); export_geometry(m,p,options=GeometryWriteOptions())
    with read(p,'m') as d: g=import_geometry(d,options=GeometryReadOptions()).geometry
    restored=next(iter(g.faces.values())).surface
    for u,v in [(0,0),(.5,.5),(1,1)]: assert restored.evaluate(u,v)==pytest.approx(s.evaluate(u,v),abs=1e-11)
    assert g.validate_topology()==()

def test_xcaf_occurrences_transforms_and_coincident_instances(tmp_path):
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDataStd import TDataStd_Name
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf,gp_Vec,gp_Pnt
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
    from anyfileio_occt._xde import write_document
    doc=TDocStd_Document(TCollection_ExtendedString('BinXCAF')); XCAFDoc_DocumentTool.SetLengthUnit_s(doc,1.)
    tool=XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()); root=tool.NewShape()
    TDataStd_Name.Set_s(root,TCollection_ExtendedString('Assembly'))
    polygon=BRepBuilderAPI_MakePolygon()
    for x,y in [(0,0),(1,0),(1,1),(0,1)]: polygon.Add(gp_Pnt(x,y,0))
    polygon.Close(); definition=tool.AddShape(BRepBuilderAPI_MakeFace(polygon.Wire()).Face(),False)
    TDataStd_Name.Set_s(definition,TCollection_ExtendedString('Panel'))
    for x in [0.,0.,3.]:
        transform=gp_Trsf(); transform.SetTranslation(gp_Vec(x,0,0))
        tool.AddComponent(root,definition,TopLoc_Location(transform))
    tool.UpdateAssemblies(); p=tmp_path/'assembly.step'; write_document(doc,p,'mm')
    with read(p) as d:
        assert len(d.manifest.occurrences)==4
        assert len(d.manifest.prototypes)==2
        assert [o.parent_id for o in d.manifest.occurrences]==[None,1,1,1]
        assert sorted(o.accumulated_transform[0,3] for o in d.manifest.occurrences)==[0,0,0,3]
        mesh=get_backend().tessellate(d,options=CadTessellationOptions())
        assert len(mesh)==2 and sum(len(m.tessellation.triangles) for m in mesh)==2
        g=import_geometry(d,options=GeometryReadOptions()).geometry
        assert len(g.faces)==3 and len(g.edges)==12 and len(g.vertices)==12
        assert len(g.parts)==3 and len(g.sheets)==3
        assert max(v.position[0] for v in g.vertices.values())==pytest.approx(4)
        target=tmp_path/'translated.step'
        get_backend().translate(d,target,options=CadWriteOptions(mode='translate',target_format='step',target_length_unit='m'))
    with read(target) as again:
        assert len(again.manifest.occurrences)==4
        assert max(o.accumulated_transform[0,3] for o in again.manifest.occurrences)==pytest.approx(3)

def test_native_step_declared_parts_import_and_native_persistence(tmp_path):
    from anyfileio_occt._xde import write_groups
    from anyfileio.geometry import write_geometry,read_geometry
    p=tmp_path/'parts.step';write_groups([('Panel',native_panel_shape())],p)
    with read(p) as d:
        assert any(o.name=='Panel' for o in d.manifest.occurrences)
        result=import_geometry(d,options=GeometryReadOptions())
    m=result.geometry
    assert len(m.parts)==1 and len(m.sheets)==1
    assert next(iter(m.parts.values())).name=='Panel'
    assert all(h.model_id==m.model_id for values in result.report.cad_to_geometry.values() for h in values)
    retained=tmp_path/'parts.anygeometry.json';write_geometry(retained,m)
    from anygeometry.serialization import to_dict
    assert to_dict(read_geometry(retained).geometry)==to_dict(m)
    assert_staged_refusal(tmp_path/'again.step',m)

@pytest.mark.parametrize('explicit',[False,True])
def test_owner_extrusion_face_export(tmp_path,explicit):
    from anygeometry import GeometryModel,ExtrudedSurface,BezierDirectrix
    m=GeometryModel(); controls=((0,0,0),(1,1,0),(2,0,0))
    a,c,b=m.add_points(controls); edge=m.add_spline(a,[c],b)
    face,=m.extrude([edge],(0,0,2))
    if explicit: m.set_face_surface(face,ExtrudedSurface(BezierDirectrix(controls),(0,0,2)))
    p=tmp_path/'owner-extrusion.brep'; export_geometry(m,p,options=GeometryWriteOptions())
    with read(p,'m') as d: g=import_geometry(d,options=GeometryReadOptions()).geometry
    s=next(iter(g.faces.values())).surface
    assert g.validate_topology()==()
    points=[s.evaluate(u,v) for u,v in [(0,0),(.5,.5),(1,1)]]
    assert points[1]==pytest.approx((1,.5,1),abs=1e-12)

@pytest.mark.parametrize('family',['ellipse','line_range'])
def test_real_ellipse_and_retained_line_files(tmp_path,family):
    from anygeometry import GeometryModel,EllipticArc,LineRange
    from fractions import Fraction
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopoDS import TopoDS
    from anyfileio_occt.backend import document_shape
    m=GeometryModel()
    c=EllipticArc((3,2,-1),(2,0,0),(.5,1,0),-.3,-2.1) if family=='ellipse' else LineRange((.1,.2,.3),(2.3,1.7,4.5)).subcurve(Fraction(6,7),Fraction(1,7))
    a,b=m.add_points(c.evaluate(np.array([0.,1.]))); m.add_curve(a,b,c)
    p=tmp_path/(family+'.brep'); export_geometry(m,p,options=GeometryWriteOptions())
    with read(p,'m') as d:
        shape=document_shape(d); edges=native.shape_map(shape,'edge'); assert edges.Extent()==1
        curve=BRepAdaptor_Curve(TopoDS.Edge_s(edges.FindKey(1)))
        for t,u in [(curve.FirstParameter(),0.),(curve.LastParameter(),1.)]:
            pnt=curve.Value(t); assert (pnt.X(),pnt.Y(),pnt.Z())==pytest.approx(c.evaluate(np.array([u]))[0],abs=1e-12)

def test_free_nonaffine_pcurve_bounded_export(tmp_path):
    from anygeometry import GeometryModel
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    s=NurbsSurface(1,1,(0,0,1,1),(0,0,1,1),(((0,0,0),(0,1,.2)),((1,0,0),(1,1,0))))
    c=CurveOnSurface(s,NurbsCurve(1,(0,0,1,1),((0,0),(1,1))))
    m=GeometryModel(); a,b=m.add_points(c.evaluate(np.array([0.,1.]))); m.add_curve(a,b,c)
    p=tmp_path/'bounded.brep'; report=export_geometry(m,p,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.1,max_topology_work=5000000))
    assert report.approximations[0].bound_m<=.1
    assert report.approximations[0].source.model_id==m.model_id

def test_public_provider_late_refusal_is_atomic(tmp_path,monkeypatch):
    m=square(); p=tmp_path/'existing.brep'; p.write_bytes(b'preserve')
    real=native.write_shape
    def changed(*args,**kwargs):
        real(*args,**kwargs); m.add_point(9,9,9)
    monkeypatch.setattr(native,'write_shape',changed)
    with pytest.raises(GeometryInterchangeError,match='geometry.revision.changed'):
        export_geometry(m,p,options=GeometryWriteOptions())
    assert p.read_bytes()==b'preserve'
    assert list(tmp_path.iterdir())==[p]

def test_chart_remap_cannot_erase_coordinate_variation(tmp_path):
    from anygeometry import GeometryModel
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    s=NurbsSurface(1,1,(1e16,1e16,1e16+1024,1e16+1024),(0,0,1,1),(((0,0,0),(0,1,.2)),((1,0,0),(1,1,0))))
    c=CurveOnSurface(s,NurbsCurve(1,(0,0,1,1),((.0001,0),(.0002,1))))
    # The owner already refuses this incoherent evaluated proxy in add_curve;
    # exercise the adapter's independent coefficient guard directly as well.
    from types import SimpleNamespace
    from anygeometry.entities import EntityRef
    from anyfileio_occt._geometry import curve_edge,point
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    m=GeometryModel(); a,b=m.add_points(c.evaluate(np.array([0.,1.])))
    edge=SimpleNamespace(start=a,end=b,curve=c,ref=EntityRef('edge',1))
    vertices={i:BRepBuilderAPI_MakeVertex(point(v.position)).Vertex() for i,v in m.vertices.items()}
    with pytest.raises(GeometryInterchangeError,match='geometry.exact.coefficient_unrepresentable'):
        curve_edge(m,edge,vertices,{},GeometryWriteOptions(),None)

def test_loose_native_vertex_tolerance_cannot_redefine_curve(tmp_path):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Pnt
    from OCP.TopExp import TopExp
    from OCP.BRep import BRep_Builder
    edge=BRepBuilderAPI_MakeEdge(gp_Pnt(0,0,0),gp_Pnt(1,0,0)).Edge()
    BRep_Builder().UpdateVertex(TopExp.FirstVertex_s(edge,True),gp_Pnt(1e-4,0,0),1e-3)
    p=tmp_path/'loose.brep'; native.write_shape(edge,p,'brep')
    with read(p,'m') as d:
        with pytest.raises(GeometryInterchangeError,match='geometry.edge.endpoint_mismatch'):
            import_geometry(d,options=GeometryReadOptions())

@pytest.mark.parametrize('offset',[0.,1e8])
@pytest.mark.parametrize('family',['line','circle'])
def test_endpoint_refusal_is_translation_invariant(tmp_path,offset,family):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Pnt,gp_Circ,gp_Ax2,gp_Dir
    from OCP.TopExp import TopExp
    from OCP.BRep import BRep_Builder,BRep_Tool
    edge=BRepBuilderAPI_MakeEdge(gp_Pnt(offset,0,0),gp_Pnt(offset+1,0,0)).Edge() if family=='line' else BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(offset,0,0),gp_Dir(0,0,1)),1.),0.,1.).Edge()
    vertex=TopExp.FirstVertex_s(edge,True); point=BRep_Tool.Pnt_s(vertex)
    BRep_Builder().UpdateVertex(vertex,gp_Pnt(point.X()+1e-4,point.Y(),point.Z()),1e-3)
    p=tmp_path/'loose-translated.brep'; native.write_shape(edge,p,'brep')
    with read(p,'m') as d:
        with pytest.raises(GeometryInterchangeError,match='geometry.edge.endpoint_mismatch'):
            import_geometry(d,options=GeometryReadOptions())

def test_native_writer_stdout_quiet_and_printers_restored(tmp_path,capfd):
    from OCP.Message import Message
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    messenger=Message.DefaultMessenger_s()
    def printers():
        values=messenger.Printers(); return tuple(values.Value(i) for i in range(1,values.Length()+1))
    before=printers(); shape=BRepPrimAPI_MakeBox(1,1,1).Shape()
    native.write_shape(shape,tmp_path/'quiet.step','step')
    assert capfd.readouterr().out==''
    assert printers()==before
    with pytest.raises(CadOperationError): native.write_shape(shape,tmp_path/'bad.step','unsupported')
    assert printers()==before
    assert capfd.readouterr().out==''

def test_xcaf_nested_rotation_composes_once(tmp_path):
    import math
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf,gp_Vec,gp_Pnt,gp_Ax1,gp_Dir
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
    from anyfileio_occt._xde import write_document
    doc=TDocStd_Document(TCollection_ExtendedString('BinXCAF')); XCAFDoc_DocumentTool.SetLengthUnit_s(doc,1.)
    tool=XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()); root=tool.NewShape(); child=tool.NewShape()
    polygon=BRepBuilderAPI_MakePolygon()
    for x,y in [(0,0),(2,0),(2,1),(0,1)]: polygon.Add(gp_Pnt(x,y,0))
    polygon.Close(); definition=tool.AddShape(BRepBuilderAPI_MakeFace(polygon.Wire()).Face(),False)
    translation=gp_Trsf(); translation.SetTranslation(gp_Vec(3,0,0)); tool.AddComponent(child,definition,TopLoc_Location(translation))
    rotation=gp_Trsf(); rotation.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,0,1)),math.pi/2)
    tool.AddComponent(root,child,TopLoc_Location(rotation)); tool.UpdateAssemblies()
    p=tmp_path/'nested.step'; write_document(doc,p)
    with read(p) as d:
        assert [o.parent_id for o in d.manifest.occurrences]==[None,1,2]
        assert d.manifest.occurrences[-1].accumulated_transform[:3,3]==pytest.approx((0,3,0),abs=1e-12)
        g=import_geometry(d,options=GeometryReadOptions()).geometry
        points=np.array([v.position for v in g.vertices.values()])
        assert points.min(axis=0)==pytest.approx((-1,3,0),abs=1e-12)
        assert points.max(axis=0)==pytest.approx((0,5,0),abs=1e-12)

@pytest.mark.parametrize('fmt',['brep'])
def test_explicit_bounded_noniso_nurbs_trims(tmp_path,fmt):
    from anygeometry import GeometryModel
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    from anygeometry.serialization import to_dict
    s=NurbsSurface(1,1,(0,0,1,1),(0,0,1,1),(((0,0,0),(0,1,.2)),((1,0,0),(1,1,0))))
    uv=[(.125,.125),(.875,.25),(.75,.875),(.25,.75)]
    m=GeometryModel(); vs=m.add_points(s.evaluate(*p) for p in uv); es=[]
    for i in range(4):
        c=CurveOnSurface(s,NurbsCurve(1,(0,0,1,1),(uv[i],uv[(i+1)%4])))
        es.append(m.add_curve(vs[i],vs[(i+1)%4],c))
    m.add_face(es,surface=s); before=to_dict(m)
    p=tmp_path/('trimmed.'+fmt)
    with pytest.raises(GeometryInterchangeError,match='geometry.exact.composition_unavailable'):
        export_geometry(m,p,options=GeometryWriteOptions())
    report=export_geometry(m,p,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.1))
    assert len(report.approximations)==4
    assert all(a.bound_m<=.1 and 'source/3D/trim' in a.method for a in report.approximations)
    tolerances=[d for d in report.diagnostics if d.code=='geometry.native_fit.edge_tolerance']
    assert len(tolerances)==4
    assert all(d.entities[0].model_id==m.model_id for d in tolerances)
    assert to_dict(m)==before
    with read(p,'m' if fmt=='brep' else None) as doc:
        restored=import_geometry(doc,options=GeometryReadOptions()).geometry
    assert len(restored.faces)==1 and len(restored.edges)==4 and restored.validate_topology()==()

def _noniso_trim_model():
    from anygeometry import GeometryModel
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    s=NurbsSurface(1,1,(0,0,1,1),(0,0,1,1),(((0,0,0),(0,1,.2)),((1,0,0),(1,1,0))))
    uv=[(.125,.125),(.875,.25),(.75,.875),(.25,.75)]
    m=GeometryModel(); vs=m.add_points(s.evaluate(*p) for p in uv); es=[]
    for i in range(4):
        es.append(m.add_curve(vs[i],vs[(i+1)%4],CurveOnSurface(s,NurbsCurve(1,(0,0,1,1),(uv[i],uv[(i+1)%4])))))
    m.add_face(es,surface=s)
    return m

@pytest.mark.parametrize('limits',[{'max_segments':31},{'max_depth':1}])
def test_bounded_trim_limits_preserve_destination(tmp_path,limits):
    m=_noniso_trim_model(); p=tmp_path/'preserve.brep'; p.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
        export_geometry(m,p,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.01,**limits))
    assert p.read_bytes()==b'old' and list(tmp_path.iterdir())==[p]

def test_bounded_trim_cancellation_after_file_preserves_destination(tmp_path,monkeypatch):
    from anyfileio_occt import _trim_bounds
    m=_noniso_trim_model(); p=tmp_path/'preserve.brep'; p.write_bytes(b'old'); state={'stop':False}
    real=_trim_bounds._box
    def box(*args):
        result=real(*args); state['stop']=True; return result
    monkeypatch.setattr(_trim_bounds,'_box',box)
    with pytest.raises(CadOperationCancelled):
        export_geometry(m,p,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.1),cancellation=lambda:state['stop'])
    assert p.read_bytes()==b'old' and list(tmp_path.iterdir())==[p]

def test_bounded_trim_actual_file_pcurve_payload_tamper_is_atomic(tmp_path,monkeypatch):
    from OCP.BRep import BRep_Tool,BRep_Builder
    from OCP.TopoDS import TopoDS
    from OCP.BRepTools import BRepTools
    from anyfileio_occt._geometry import bspline_curve
    m=_noniso_trim_model(); p=tmp_path/'preserve.brep'; p.write_bytes(b'old'); real=native.write_shape; tampered=[]
    def changed(shape,path,fmt,unit='m',cancellation=None):
        real(shape,path,fmt,unit,cancellation)
        result,_=native.read_shape(path,fmt,'m' if fmt=='brep' else None)
        face=TopoDS.Face_s(native.shape_map(result,'face').FindKey(1)); edge=TopoDS.Edge_s(native.shape_map(face,'edge').FindKey(1))
        pc=bspline_curve([(.125,.125),(.5,.8),(.875,.25)],2,[0,0,0,1,1,1],dimension=2)
        BRep_Builder().UpdateEdge(edge,pc,face,1e-7)
        assert BRepTools.Write_s(result,str(path))
        tampered.append(True)
    monkeypatch.setattr(native,'write_shape',changed)
    with pytest.raises(GeometryInterchangeError,match='geometry.association.payload_changed'):
        export_geometry(m,p,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.1,max_segments=1000))
    assert p.read_bytes()==b'old'

    assert tampered==[True]

def test_committed_export_does_not_serialize_owner(tmp_path,monkeypatch):
    import anygeometry
    import anygeometry.serialization as persistence
    m=square()
    def forbidden(*args,**kwargs): raise AssertionError('normal CAD export must not serialize the owner')
    monkeypatch.setattr(anygeometry,'to_dict',forbidden); monkeypatch.setattr(persistence,'to_dict',forbidden)
    monkeypatch.setattr(anygeometry,'read_geometry',forbidden)
    export_geometry(m,tmp_path/'shallow.brep',options=GeometryWriteOptions())

def test_certified_export_calls_owner_certified_gate(tmp_path,monkeypatch):
    import anygeometry.serialization as persistence
    calls=[]; m=square()
    def gate(geometry,*,certified=False):
        calls.append((geometry,certified)); raise GeometryInterchangeError('certified gate marker')
    monkeypatch.setattr(persistence,'to_dict',gate)
    with pytest.raises(GeometryInterchangeError,match='certified gate marker'):
        export_geometry(m,tmp_path/'certified.brep',options=GeometryWriteOptions(validation_mode='certified'))
    assert calls==[(m,True)]

def test_step_external_entity_refuses_before_transfer(tmp_path,monkeypatch):
    import OCP.STEPCAFControl as caf
    from OCP.StepBasic import StepBasic_DocumentFile
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from anyfileio_occt import _xde
    p=tmp_path/'external.step'; native.write_shape(BRepPrimAPI_MakeBox(1,1,1).Shape(),p,'step')
    real=caf.STEPCAFControl_Reader; transferred=[]
    class Reader:
        def __init__(self): self.native=real()
        def ReadFile(self,path):
            status=self.native.ReadFile(path)
            self.native.Reader().StepModel().AddEntity(StepBasic_DocumentFile())
            return status
        def Reader(self): return self.native.Reader()
        def Transfer(self,*args): transferred.append(True); raise AssertionError('external source must not transfer')
    monkeypatch.setattr(caf,'STEPCAFControl_Reader',Reader)
    with pytest.raises(CadOperationError,match='cad.source.external_references_unsupported'):
        _xde.read(p)
    assert not transferred

def test_step_null_transferred_leaf_is_not_success(tmp_path,monkeypatch):
    from OCP.XCAFDoc import XCAFDoc_ShapeTool
    from OCP.TopoDS import TopoDS_Shape
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from anyfileio_occt import _xde
    p=tmp_path/'null.step'; native.write_shape(BRepPrimAPI_MakeBox(1,1,1).Shape(),p,'step')
    monkeypatch.setattr(XCAFDoc_ShapeTool,'GetShape_s',lambda label:TopoDS_Shape())
    with pytest.raises(CadOperationError,match='cad.read.incomplete'):
        _xde.read(p)

def test_equal_but_distinct_nurbs_support_objects_share_native_support(tmp_path):
    from copy import deepcopy
    from anygeometry import GeometryModel
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    s=NurbsSurface(1,1,(0,0,1,1),(0,0,1,1),(((0,0,0),(0,1,.2)),((1,0,0),(1,1,0))))
    uv=[(0.,0.),(1.,0.),(1.,1.),(0.,1.)]; m=GeometryModel(); vs=m.add_points(s.evaluate(*p) for p in uv); es=[]
    for i in range(4): es.append(m.add_curve(vs[i],vs[(i+1)%4],CurveOnSurface(deepcopy(s),NurbsCurve(1,(0,0,1,1),(uv[i],uv[(i+1)%4])))))
    m.add_face(es,surface=deepcopy(s))
    p=tmp_path/'equal-supports.brep'; export_geometry(m,p,options=GeometryWriteOptions())
    with read(p,'m') as doc: restored=import_geometry(doc,options=GeometryReadOptions()).geometry
    assert len(restored.faces)==1 and restored.validate_topology()==()

@pytest.mark.parametrize('operation',['drop_face','reverse_face'])
def test_bounded_trim_topology_payload_tamper_is_atomic(tmp_path,monkeypatch,operation):
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS
    m=_noniso_trim_model(); p=tmp_path/'preserve.brep'; p.write_bytes(b'old'); real=native.write_shape; tampered=[]
    def changed(shape,path,fmt,unit='m',cancellation=None):
        real(shape,path,fmt,unit,cancellation)
        output,_=native.read_shape(path,fmt,'m' if fmt=='brep' else None)
        face=TopoDS.Face_s(native.shape_map(output,'face').FindKey(1)); builder=BRep_Builder()
        builder.Remove(output,face)
        if operation=='drop_face': builder.Add(output,native.shape_map(face,'wire').FindKey(1))
        else: builder.Add(output,face.Reversed())
        assert BRepTools.Write_s(output,str(path))
        tampered.append(True)
    monkeypatch.setattr(native,'write_shape',changed)
    with pytest.raises(GeometryInterchangeError,match='geometry.association.payload_changed'):
        export_geometry(m,p,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.1))
    assert p.read_bytes()==b'old'

    assert tampered==[True]

@pytest.mark.parametrize('operation',['reassign_shell','duplicate_carrier'])
def test_bounded_trim_shell_and_duplicate_payload_tamper_is_atomic(tmp_path,monkeypatch,operation):
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS,TopoDS_Shell
    m=_noniso_trim_model()
    if operation=='reassign_shell':
        part=m.add_part(); m.add_sheet([1],part_id=part)
    p=tmp_path/'preserve.brep'; p.write_bytes(b'old'); real=native.write_shape; tampered=[]
    def changed(shape,path,fmt,unit='m',cancellation=None):
        real(shape,path,fmt,unit,cancellation); output,_=native.read_shape(path,fmt,'m')
        face=TopoDS.Face_s(native.shape_map(output,'face').FindKey(1)); builder=BRep_Builder()
        if operation=='reassign_shell':
            shell=TopoDS.Shell_s(native.shape_map(output,'shell').FindKey(1))
            shell.Free(True)
            builder.Remove(shell,face); builder.Add(output,face)
        else:
            shell=TopoDS_Shell(); builder.MakeShell(shell); builder.Add(shell,face); builder.Add(output,shell)
        assert BRepTools.Write_s(output,str(path))
        tampered.append(True)
    monkeypatch.setattr(native,'write_shape',changed)
    with pytest.raises(GeometryInterchangeError,match='geometry.association.payload_changed'):
        export_geometry(m,p,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.1))
    assert p.read_bytes()==b'old'

    assert tampered==[True]

@pytest.mark.parametrize('family',['quadric','bezier_quadric','plane_nurbs'])
def test_specialized_public_family_bounded_roundtrip(tmp_path,family):
    import math
    from anygeometry import GeometryModel
    from anygeometry.surfaces import Cylinder,Cone,ExtrudedSurface,Plane
    from anygeometry.extrusions import BezierDirectrix
    if family=='quadric':
        from anygeometry.quadric_supports import cone_support
        from anygeometry.quadric_curves import QuadricIntersectionCurve
        a=math.radians(10); cone=Cone((0,0,0),(math.cos(a),0,math.sin(a)),(0,1,0),.5,1.,5.)
        cyl=Cylinder((0,0,-3),(0,0,1),(1,0,0),2.,6.)
        curve=next(c for c in cone_support(cone,cyl,tolerance=1e-9).curves if isinstance(c,QuadricIntersectionCurve))
    elif family=='bezier_quadric':
        from anygeometry.branch_supports import bezier_quadric_support
        wall=ExtrudedSurface(BezierDirectrix(((0.,0.,0.),(1.,2.,0.),(2.,-1.,0.),(3.,1.,0.))),(.25,0.,1.5))
        pipe=Cylinder((-2.,.4,.6),(1.,0.,0.),(0.,1.,0.),.7,8.)
        curve=bezier_quadric_support(wall,pipe).curves[0]
    else:
        from anygeometry.nurbs import cylinder_to_nurbs
        from anygeometry.support_curves import PlaneNurbsCurve
        support=cylinder_to_nurbs(Cylinder((0,0,0),(0,0,1),(1,0,0),2.,3.,0.,math.pi))
        curve=PlaneNurbsCurve.from_plane(Plane((0,0,1.5),(1,0,.3),(0,1,.2)),support,0)
    curve=curve.subcurve(.1,.9)
    model=GeometryModel(); a,b=model.add_points(curve.evaluate(np.array([0.,1.]))); model.add_curve(a,b,curve)
    path=tmp_path/(family+'.brep')
    with pytest.raises(GeometryInterchangeError,match='geometry.exact.unsupported'):
        export_geometry(model,path,options=GeometryWriteOptions())
    report=export_geometry(model,path,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.5,max_topology_work=5000000 if family=='plane_nurbs' else 1000000))
    assert len(report.approximations)==1 and report.approximations[0].bound_m<=.5
    with read(path,'m') as doc: restored=import_geometry(doc,options=GeometryReadOptions()).geometry
    assert len(restored.edges)>=1 and restored.validate_topology()==()

@pytest.mark.parametrize('mode',['live','preview','manifest_only'])
def test_real_core_registered_reader_and_renamed_identity(tmp_path,mode):
    from anyfileio.cad_operations import read_cad
    from anyfileio.cad import cad_import_document_id
    from anyfileio.geometry import read_geometry
    first=tmp_path/'original.step'; native.write_shape(native_panel_shape(),first,'step','m')
    second=tmp_path/'renamed.step'; second.write_bytes(first.read_bytes())
    identifiers=[]
    for path in (first,second):
        kwargs={'tessellation_options':CadTessellationOptions()} if mode=='live' else {}
        document=read_cad(path,options=CadReadOptions(mode=mode),**kwargs)
        try:
            identifiers.append(document.manifest.document_id)
            assert document.source_available
            assert document.manifest.document_id==cad_import_document_id(source_sha256=native.digest(path),source_format='step',effective_source_length_unit='m')
            if mode!='manifest_only': assert document.tessellation is not None
        finally:
            document.close(); document.release_source()
        assert path.is_file()
    assert identifiers[0]==identifiers[1]
    restored=read_geometry(first).geometry
    assert len(restored.faces)==1 and restored.validate_topology()==()

@pytest.mark.parametrize('fmt,unit',[('step',None),('iges',None),('brep','m')])
def test_real_core_reader_unretained_source_and_facade(tmp_path,fmt,unit):
    from anyfileio.cad_operations import read_cad
    from anyfileio.geometry import read_geometry
    p=tmp_path/('panel.'+fmt); native.write_shape(native_panel_shape(),p,fmt,'m')
    with read_cad(p,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override=unit)) as document:
        assert not document.source_available
    result=read_geometry(p,options=GeometryReadOptions(source_length_unit_override=unit))
    assert len(result.geometry.faces)==1

def test_missing_public_core_identity_capability_is_typed(tmp_path,monkeypatch):
    import anyfileio.cad as core
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    p=tmp_path/'old-core.brep'; native.write_shape(BRepPrimAPI_MakeBox(1,1,1).Shape(),p,'brep')
    monkeypatch.delattr(core,'cad_import_document_id')
    with pytest.raises(CadOperationError,match='cad.core.capability_missing'):
        read(p,'m')

def test_bounded_trim_same_count_weld_split_payload_is_rejected(tmp_path,monkeypatch):
    from OCP.BRep import BRep_Builder,BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS,TopoDS_Edge,TopoDS_Wire,TopoDS_Face,TopoDS_Compound
    from OCP.TopExp import TopExp
    from OCP.TopAbs import TopAbs_FORWARD,TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    m=_noniso_trim_model(); path=tmp_path/'preserve.brep'; path.write_bytes(b'old'); real=native.write_shape; tampered=[]
    def changed(shape,destination,fmt,unit='m',cancellation=None):
        real(shape,destination,fmt,unit,cancellation)
        old,_=native.read_shape(destination,fmt,'m'); builder=BRep_Builder()
        original_counts=native.counts(old)
        vertices=native.shape_map(old,'vertex'); edges=native.shape_map(old,'edge')
        face=TopoDS.Face_s(native.shape_map(old,'face').FindKey(1)); surface=BRep_Tool.Surface_s(face)
        first=TopoDS.Vertex_s(vertices.FindKey(1)); builder.UpdateVertex(first,2.)
        fourth=TopoDS.Vertex_s(vertices.FindKey(4))
        duplicate=BRepBuilderAPI_MakeVertex(BRep_Tool.Pnt_s(fourth)).Vertex()
        split=[False]
        def replacement(vertex):
            identity=vertices.FindIndex(vertex)
            if identity==2: return first  # weld one distinct source corner
            if identity==4 and not split[0]:
                split[0]=True; return duplicate  # split another to preserve total count
            return vertex
        wire=TopoDS_Wire(); builder.MakeWire(wire)
        for i in range(1,edges.Extent()+1):
            original=TopoDS.Edge_s(edges.FindKey(i).Oriented(TopAbs_FORWARD)); c=BRepAdaptor_Curve(original)
            edge=TopoDS_Edge(); builder.MakeEdge(edge)
            builder.UpdateEdge(edge,BRep_Tool.Curve_s(original,0.,0.),2.)
            builder.UpdateEdge(edge,BRep_Tool.CurveOnSurface_s(original,face,0.,0.),surface,TopLoc_Location(),2.)
            builder.Range(edge,c.FirstParameter(),c.LastParameter())
            a=replacement(TopExp.FirstVertex_s(original,True)); b=replacement(TopExp.LastVertex_s(original,True))
            builder.Add(edge,a.Oriented(TopAbs_FORWARD)); builder.Add(edge,b.Oriented(TopAbs_REVERSED))
            builder.SameParameter(edge,True); builder.SameRange(edge,True)
            builder.Add(wire,edge.Oriented(edges.FindKey(i).Orientation()))
        rebuilt=TopoDS_Face(); builder.MakeFace(rebuilt,surface,TopLoc_Location(),1e-7); builder.Add(rebuilt,wire)
        output=TopoDS_Compound(); builder.MakeCompound(output); builder.Add(output,rebuilt)
        assert native.counts(output)==original_counts
        assert BRepTools.Write_s(output,str(destination))
        tampered.append(True)
    monkeypatch.setattr(native,'write_shape',changed)
    with pytest.raises(GeometryInterchangeError,match='geometry.association.payload_changed'):
        export_geometry(m,path,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.1))
    assert path.read_bytes()==b'old'

    assert tampered==[True]


def native_panel_shape():
    """Independent native STEP/IGES import fixture, not editable export setup."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Pnt
    wire=BRepBuilderAPI_MakePolygon()
    for p in ((0,0,0),(2,0,0),(2,1,0),(0,1,0)):wire.Add(gp_Pnt(*p))
    wire.Close();return BRepBuilderAPI_MakeFace(wire.Wire()).Face()


def assert_staged_refusal(path,model,options=None):
    from anyfileio.geometry import write_geometry
    from anygeometry.serialization import to_dict
    before=to_dict(model);existing=set(path.parent.iterdir());path.write_bytes(b'previous')
    with pytest.raises(GeometryInterchangeError) as error:
        write_geometry(path,model,options=options)
    assert error.value.code=='geometry.association_unproved'
    assert path.read_bytes()==b'previous' and set(path.parent.iterdir())==existing|{path}
    assert to_dict(model)==before


@pytest.mark.parametrize('fmt',['step','iges'])
def test_editable_formats_require_proved_association(tmp_path,fmt):
    assert_staged_refusal(tmp_path/('panel.'+fmt),square(),GeometryWriteOptions(output_length_unit='mm'))
