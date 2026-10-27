"""Exact shared topology on identical NURBS support/chart definitions."""
from copy import deepcopy
import numpy as np
import pytest
pytest.importorskip('OCP')
from anyfileio.geometry import write_geometry,read_geometry,GeometryWriteOptions,GeometryReadOptions,GeometryInterchangeError


def shared_model(distinct=False,reverse=False,ranged=False):
    from anygeometry import GeometryModel,reverse_edge
    from anygeometry.entities import OrientedEdge
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    support=NurbsSurface(1,1,(2,2,6,6) if ranged else (0,0,1,1),(-1,-1,3,3) if ranged else (0,0,1,1),(((0,0,0),(0,1,0)),((2,0,0),(2,1,0))))
    uv=((0,0),(.5,0),(1,0),(0,1),(.5,1),(1,1))
    model=GeometryModel(); vertices=model.add_points(support.evaluate(*p) for p in uv)
    pairs=((0,1),(1,2),(2,5),(5,4),(4,3),(3,0),(1,4)); edges=[]
    for a,b in pairs:
        curve=CurveOnSurface(support,NurbsCurve(1,(0,0,1,1),(uv[a],uv[b])))
        edges.append(model.add_curve(vertices[a],vertices[b],curve))
    model.add_face_from_loop([OrientedEdge(edges[i],True) for i in (0,6,4,5)],(0,1,2,3),surface=support)
    model.add_face_from_loop([OrientedEdge(edges[i],True) for i in (1,2,3)]+[OrientedEdge(edges[6],False)],(0,1,2,3),surface=deepcopy(support) if distinct else support)
    if reverse: reverse_edge(model,edges[6])
    return model,edges[6]


@pytest.mark.parametrize('fmt,unit',[('brep','mm')])
@pytest.mark.parametrize('distinct',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_equal_support_shared_edge_roundtrip(tmp_path,fmt,unit,distinct,reverse):
    from anygeometry.serialization import to_dict
    model,shared=shared_model(distinct,reverse); before=to_dict(model)
    path=tmp_path/('shared.'+fmt)
    write_geometry(path,model,options=GeometryWriteOptions(output_length_unit=unit))
    result=read_geometry(path,options=GeometryReadOptions(source_length_unit_override=unit if fmt=='brep' else None)); restored=result.geometry
    assert (len(restored.faces),len(restored.edges),len(restored.vertices))==(2,7,6)
    shared_edges=[e for e in restored.edges if len(restored.faces_using_edge(e))==2]
    assert len(shared_edges)==1
    assert restored.validate_topology()==() and to_dict(model)==before
    shared_edge=restored.edges[shared_edges[0]]
    assert sorted([restored.vertices[shared_edge.start].position.tolist(),restored.vertices[shared_edge.end].position.tolist()])==[[1.,0.,0.],[1.,1.,0.]]
    for face in restored.faces.values():
        assert face.surface.evaluate(.25,.75)==pytest.approx((.5,.75,0),abs=1e-12,rel=0)
    assert all(h.model_id==restored.model_id for handles in result.report.cad_to_geometry.values() for h in handles)


def test_declared_sheet_shared_support_brep(tmp_path):
    model,edge=shared_model(distinct=True)
    model.add_sheet(list(model.faces))
    path=tmp_path/'declared-sheet.brep'; write_geometry(path,model)
    restored=read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m')).geometry
    assert (len(restored.faces),len(restored.edges),len(restored.vertices))==(2,7,6)
    assert len([e for e in restored.edges if len(restored.faces_using_edge(e))==2])==1


@pytest.mark.parametrize('middle',[.5,.625])
def test_unequal_incident_pcurve_definition_refuses(tmp_path,middle):
    from OCP.BRep import BRep_Tool,BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopAbs import TopAbs_FORWARD
    from anyfileio_occt import _native
    from anyfileio_occt._geometry import bspline_curve
    from anygeometry.serialization import to_dict
    model,edge=shared_model(distinct=True); before=to_dict(model)
    path=tmp_path/'tampered.brep'; write_geometry(path,model)
    shape,_=_native.read_shape(path,'brep','m'); faces=_native.shape_map(shape,'face')
    first=TopoDS.Face_s(faces.FindKey(1)); second=TopoDS.Face_s(faces.FindKey(2))
    old_surface=BRep_Tool.Surface_s(second); copy=old_surface.Copy()
    first_edges=_native.shape_map(first,'edge'); second_edges=_native.shape_map(second,'edge')
    data=[]
    for i in range(1,second_edges.Extent()+1):
        native_edge=TopoDS.Edge_s(second_edges.FindKey(i).Oriented(TopAbs_FORWARD))
        data.append((native_edge,BRep_Tool.CurveOnSurface_s(native_edge,second,0.,0.),BRep_Tool.Range_s(native_edge,second),first_edges.FindIndex(native_edge)!=0))
    second.Free(True); builder=BRep_Builder(); builder.UpdateFace(second,copy,TopLoc_Location(),1e-7)
    for native_edge,pc,domain,shared in data:
        if shared: pc=bspline_curve([(.5,0),(middle,.5),(.5,1)],2,[0,0,0,1,1,1],dimension=2)
        builder.UpdateEdge(native_edge,pc,copy,TopLoc_Location(),1e-7)
        builder.Range(native_edge,copy,TopLoc_Location(),*domain)
    assert BRepTools.Write_s(shape,str(path))
    with pytest.raises(GeometryInterchangeError,match='geometry.trim.shared_pcurve_unsupported'):
        read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m'))
    assert to_dict(model)==before


@pytest.mark.parametrize('fmt',['brep'])
def test_shared_support_ranged_native_chart(tmp_path,fmt):
    model,shared=shared_model(distinct=True,reverse=True,ranged=True)
    path=tmp_path/('ranged.'+fmt); write_geometry(path,model)
    restored=read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m' if fmt=='brep' else None)).geometry
    assert (len(restored.faces),len(restored.edges),len(restored.vertices))==(2,7,6)
    assert restored.validate_topology()==()
    assert all(face.surface.u_range==(2.,6.) and face.surface.v_range==(-1.,3.) for face in restored.faces.values())


def test_shared_support_gather_cancellation(tmp_path,monkeypatch):
    from anyfileio_occt import geometry_import
    from anyfileio.cad import CadOperationCancelled
    from anygeometry.serialization import to_dict
    model,edge=shared_model(); before=to_dict(model); path=tmp_path/'cancel.brep'; write_geometry(path,model)
    payload=path.read_bytes(); state={'stop':False}; real=geometry_import._native_pcurve_definition
    def inspected(*args,**kwargs):
        result=real(*args,**kwargs); state['stop']=True; return result
    monkeypatch.setattr(geometry_import,'_native_pcurve_definition',inspected)
    with pytest.raises(CadOperationCancelled):
        read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m'),cancellation=lambda:state['stop'])
    assert path.read_bytes()==payload and to_dict(model)==before


@pytest.mark.parametrize('fmt',['brep'])
def test_native_writer_source_replacement_is_atomic(tmp_path,monkeypatch,fmt):
    from anyfileio_occt import _native
    from OCP.TopoDS import TopoDS
    model,edge=shared_model(); real=_native.write_shape; written=[]
    def dropped(shape,path,format,unit='m',cancellation=None):
        face=TopoDS.Face_s(_native.shape_map(shape,'face').FindKey(1))
        written.append(True)  # record the attempted substitution before the source guard
        return real(face,path,format,unit,cancellation)
    monkeypatch.setattr(_native,'write_shape',dropped)
    path=tmp_path/('preserve.'+fmt); path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.association.source_changed'): write_geometry(path,model)
    assert path.read_bytes()==b'old' and list(tmp_path.iterdir())==[path]
    assert written==[True]


@pytest.mark.parametrize('fmt',['brep'])
def test_independent_coincident_patches_are_not_carrier_welded(tmp_path,fmt):
    from anygeometry import GeometryModel
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    support=NurbsSurface(1,1,(0,0,1,1),(0,0,1,1),(((0,0,0),(0,1,0)),((2,0,0),(2,1,0))))
    uv=((0,0),(1,0),(1,1),(0,1)); model=GeometryModel()
    for repetition in range(2):
        vertices=model.add_points(support.evaluate(*p) for p in uv); edges=[]
        for i in range(4): edges.append(model.add_curve(vertices[i],vertices[(i+1)%4],CurveOnSurface(support,NurbsCurve(1,(0,0,1,1),(uv[i],uv[(i+1)%4])))))
        model.add_face(edges,surface=support)
    path=tmp_path/('coincident.'+fmt); write_geometry(path,model)
    restored=read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m' if fmt=='brep' else None)).geometry
    assert (len(restored.faces),len(restored.edges),len(restored.vertices))==(2,8,8)


def test_step_unowned_free_curves_require_proved_association(tmp_path):
    from anygeometry import GeometryModel
    from anygeometry.nurbs import NurbsCurve
    model=GeometryModel(); a,b,c=model.add_points(((0,0,0),(1,0,0),(.5,1,0)))
    model.add_arc(a,c,b); model.add_spline(a,[c],b)
    model.add_curve(a,b,NurbsCurve(2,(0,0,0,1,1,1),((0,0,0),(.5,.4,0),(1,0,0)),(1,.7,1)))
    path=tmp_path/'preserve.step'; path.write_bytes(b'old')
    # Editable STEP is refused before serialization until record lineage is proved.
    with pytest.raises(GeometryInterchangeError,match='geometry.association_unproved'):
        write_geometry(path,model)
    assert path.read_bytes()==b'old' and list(tmp_path.iterdir())==[path]


@pytest.mark.parametrize('fmt',['step','iges'])
def test_shared_surface_staged_format_refusal(tmp_path,fmt):
    from test_native_geometry import assert_staged_refusal
    model,_=shared_model(distinct=True,reverse=True,ranged=True)
    assert_staged_refusal(tmp_path/('shared.'+fmt),model)
