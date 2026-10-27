"""Exact shared polynomial ruled import; no sampled equality admission."""
import numpy as np
import pytest

pytest.importorskip('OCP')
from anyfileio.geometry import read_geometry,write_geometry,GeometryReadOptions,GeometryWriteOptions,GeometryInterchangeError


ROWS=tuple(tuple((x,y,z) for x,z in ((0,0),(1,0),(1,1))) for y in (0,1,2))


def owner_pair(reverse=False,source_unit='m'):
    from anygeometry import GeometryModel,reverse_face
    from anygeometry.entities import OrientedEdge
    from anygeometry.surfaces import RuledSurface
    model=GeometryModel(); ids=[model.add_points(row) for row in ROWS]
    profiles=[[model.add_line(row[i],row[i+1]) for i in range(2)] for row in ids]
    left=[model.add_line(ids[j][0],ids[j+1][0]) for j in range(2)]
    right=[model.add_line(ids[j][2],ids[j+1][2]) for j in range(2)]
    for j in range(2):
        loop=([OrientedEdge(e,True) for e in profiles[j]]+[OrientedEdge(right[j],True)]+
              [OrientedEdge(e,False) for e in reversed(profiles[j+1])]+[OrientedEdge(left[j],False)])
        model.add_face_from_loop(loop,surface=RuledSurface(ROWS[j],ROWS[j+1]))
    if reverse: reverse_face(model,next(iter(model.faces)))
    model.set_document_settings(units=source_unit)
    return model


def native_pair(nonuniform=False,weighted=False,tamper=False,ranged=False,retrace=False):
    """Native-authored fixture independent of owner export/materialization."""
    from OCP.gp import gp_Pnt,gp_Pnt2d
    from OCP.Geom import Geom_BSplineSurface
    from OCP.Geom2d import Geom2d_BSplineCurve
    from OCP.TColgp import TColgp_Array2OfPnt,TColgp_Array1OfPnt2d
    from OCP.TColStd import TColStd_Array1OfReal,TColStd_Array1OfInteger,TColStd_Array2OfReal
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex,BRepBuilderAPI_MakeEdge,BRepBuilderAPI_MakeWire,BRepBuilderAPI_MakeFace
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Shell,TopoDS
    from OCP.TopLoc import TopLoc_Location
    def array(values,cls):
        result=cls(1,len(values))
        for i,value in enumerate(values,1): result.SetValue(i,value)
        return result
    vertices=[[BRepBuilderAPI_MakeVertex(gp_Pnt(*p)).Vertex() for p in row] for row in ROWS]
    profiles=[[BRepBuilderAPI_MakeEdge(row[i],row[i+1]).Edge() for i in range(2)] for row in vertices]
    left=[BRepBuilderAPI_MakeEdge(vertices[j][0],vertices[j+1][0]).Edge() for j in range(2)]
    right=[BRepBuilderAPI_MakeEdge(vertices[j][2],vertices[j+1][2]).Edge() for j in range(2)]
    us=(2.,4.,6.) if ranged else (0.,.25 if nonuniform else .5,1.)
    vs=(-1.,3.) if ranged else (0.,1.)
    builder=BRep_Builder(); shell=TopoDS_Shell(); builder.MakeShell(shell)
    for j in range(2):
        poles=TColgp_Array2OfPnt(1,3,1,2)
        for i in range(3):
            for k in range(2): poles.SetValue(i+1,k+1,gp_Pnt(*ROWS[j+k][i]))
        args=(array(us,TColStd_Array1OfReal),array(vs,TColStd_Array1OfReal),
              array((2,1,2),TColStd_Array1OfInteger),array((2,2),TColStd_Array1OfInteger),1,1,False,False)
        if weighted:
            weights=TColStd_Array2OfReal(1,3,1,2)
            for i in range(3):
                for k in range(2): weights.SetValue(i+1,k+1,(1.,.5,1.)[i])
            surface=Geom_BSplineSurface(poles,weights,*args)
        else: surface=Geom_BSplineSurface(poles,*args)
        specs=[(profiles[j][i],((us[i],vs[0]),(us[i+1],vs[0]))) for i in range(2)]
        specs += [(profiles[j+1][i],((us[i],vs[1]),(us[i+1],vs[1]))) for i in range(2)]
        specs += [(left[j],((us[0],vs[0]),(us[0],vs[1]))),(right[j],((us[-1],vs[0]),(us[-1],vs[1])))]
        for index,(edge,uv) in enumerate(specs):
            points=list(uv)
            if tamper and j==0 and index==2:
                # Endpoints and the midpoint remain the original border. The
                # hidden quarter-domain excursion must still be rejected.
                points=[uv[0],(.125,.75),(.25,1.),uv[1]]
            if retrace and j==0 and index==2:
                points=[uv[0],(.375,1.),(.25,1.),uv[1]]
            controls=array([gp_Pnt2d(*p) for p in points],TColgp_Array1OfPnt2d)
            knots=((0.,.25,.5,1.) if tamper and j==0 and index==2 else
                   (0.,.25,.75,1.) if len(points)==4 else (0.,1.))
            multiplicities=(2,)+(1,)*(len(points)-2)+(2,)
            pc=Geom2d_BSplineCurve(controls,array(knots,TColStd_Array1OfReal),array(multiplicities,TColStd_Array1OfInteger),1,False)
            builder.UpdateEdge(edge,pc,surface,TopLoc_Location(),1e-7)
            builder.Range(edge,surface,TopLoc_Location(),0.,1.)
        wire=BRepBuilderAPI_MakeWire()
        for edge in profiles[j]+[right[j]]: wire.Add(edge)
        for edge in list(reversed(profiles[j+1]))+[left[j]]: wire.Add(TopoDS.Edge_s(edge.Reversed()))
        maker=BRepBuilderAPI_MakeFace(surface,wire.Wire(),True)
        assert maker.IsDone()
        builder.Add(shell,maker.Face())
    return shell


def assert_pair(model,scale=1.,reverse_first=False):
    from anygeometry.surfaces import RuledSurface
    assert (len(model.faces),len(model.edges),len(model.vertices))==(2,10,9)
    assert len([i for i in model.edges if len(model.faces_using_edge(i))==2])==2
    assert all(isinstance(f.surface,RuledSurface) for f in model.faces.values())
    assert model.validate_topology()==()
    for face in model.faces.values():
        first,second=face.surface.first_boundary,face.surface.second_boundary
        y=min(first[:,1].min(),second[:,1].min())
        sign=-1. if reverse_first and y<.5*scale else 1.
        for u,v in ((.25,.25),(.75,.75)):
            # Public face reversal may reverse the directrix; assert the exact
            # folded strip's point-set equations rather than assume its chart.
            x,p_y,z=face.surface.evaluate(u,v)
            assert p_y==pytest.approx(y+v*scale,abs=1e-12,rel=0)
            assert min(abs(z),abs(x-scale))<=1e-12
            # Analytical derivatives of the PUBLIC piecewise-linear ruled
            # coefficients, away from the knot. No finite differences or
            # implementation surface-normal helper supplies this result.
            count=len(first)-1; i=int(u*count); local=u*count-i
            du=count*((1-v)*(first[i+1]-first[i])+v*(second[i+1]-second[i]))
            dv=(1-local)*(second[i]-first[i])+local*(second[i+1]-first[i+1])
            actual=np.cross(du,dv); actual/=np.linalg.norm(actual)
            # Identify the PHYSICAL patch, not an assumed unchanged imported
            # UV chart. The horizontal patch is +Z, vertical patch is -X.
            expected=np.array((0.,0.,1.)) if x<.75*scale else np.array((-1.,0.,0.))
            assert actual==pytest.approx(sign*expected,abs=1e-12,rel=0)
        points=np.array([model.vertices[model.oriented_start_vertex(use)].position for use in face.loop])
        expected=np.array(((0,y/scale,0),(1,y/scale,0),(1,y/scale,1),
                           (1,y/scale+1,1),(1,y/scale+1,0),(0,y/scale+1,0)))*scale
        if sign<0: expected=expected[::-1]
        assert len(points)==len(expected)
        # Only a cyclic start-point change is allowed, not a loop reversal.
        assert min(np.max(np.abs(np.roll(points,i,axis=0)-expected)) for i in range(len(points)))<=1e-12
        area_vector=sum((np.cross(a,b) for a,b in zip(points,np.roll(points,-1,axis=0))),np.zeros(3))
        expected_direction=sign*np.array((-1.,0.,1.))/np.sqrt(2.)
        assert area_vector/np.linalg.norm(area_vector)==pytest.approx(expected_direction,abs=1e-12,rel=0)


@pytest.mark.parametrize('ranged',[False,True])
def test_native_authored_polynomial_pair(tmp_path,ranged):
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS
    from anygeometry.nurbs import NurbsSurface
    from anyfileio_occt import _native
    from anyfileio_occt.geometry_import import surface_from_native
    shape=native_pair(ranged=ranged); faces=_native.shape_map(shape,'face')
    explicit=[surface_from_native(TopoDS.Face_s(faces.FindKey(i))) for i in range(1,faces.Extent()+1)]
    # The generic helper used by post-file NURBS certificates MUST stay generic.
    assert all(isinstance(s,NurbsSurface) for s in explicit)
    path=tmp_path/'native.brep'; assert BRepTools.Write_s(shape,str(path))
    before=path.read_bytes()
    model=read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m')).geometry
    assert_pair(model)
    for face,support in zip(model.faces.values(),explicit):
        assert face.surface.first_boundary.tolist()==[list(row[0]) for row in support.controls]
        assert face.surface.second_boundary.tolist()==[list(row[1]) for row in support.controls]
    assert path.read_bytes()==before


@pytest.mark.parametrize('fmt,unit',[('brep','mm')])
@pytest.mark.parametrize('reverse',[False,True])
def test_owner_pair_files(tmp_path,fmt,unit,reverse):
    from anygeometry.serialization import to_dict
    source=owner_pair(reverse); before=to_dict(source); path=tmp_path/('pair.'+fmt)
    assert_pair(source,reverse_first=reverse)
    write_geometry(path,source,options=GeometryWriteOptions(output_length_unit=unit))
    result=read_geometry(path,options=GeometryReadOptions(source_length_unit_override=unit if fmt=='brep' else None))
    assert_pair(result.geometry,reverse_first=reverse)
    assert to_dict(source)==before


@pytest.mark.parametrize('change,reason',[('nonuniform','uniform normalized'),('weighted','nonconstant rational'),
    ('tamper','natural chart border'),('retrace','exactly once')])
def test_unproved_definitions_refuse(tmp_path,change,reason):
    from OCP.BRepTools import BRepTools
    path=tmp_path/'unproved.brep'; assert BRepTools.Write_s(native_pair(**{change:True}),str(path))
    before=path.read_bytes()
    with pytest.raises(GeometryInterchangeError,match=reason):
        read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m'))
    assert path.read_bytes()==before


def test_source_millimetres_are_preserved_as_metres(tmp_path):
    source=owner_pair(source_unit='mm'); path=tmp_path/'physical.brep'
    write_geometry(path,source,options=GeometryWriteOptions(output_length_unit='m'))
    result=read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m'))
    assert_pair(result.geometry,.001)


def test_native_asset_is_not_mutated(tmp_path):
    from OCP.BRepTools import BRepTools
    from anyfileio.cad_operations import read_cad
    from anyfileio.cad import CadReadOptions
    from anyfileio_occt.backend import document_shape
    from anyfileio_occt.geometry_import import import_geometry
    source=tmp_path/'source.brep'; assert BRepTools.Write_s(native_pair(),str(source))
    with read_cad(source,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as document:
        before=tmp_path/'before.brep'; after=tmp_path/'after.brep'
        assert BRepTools.Write_s(document_shape(document),str(before))
        assert_pair(import_geometry(document,options=GeometryReadOptions()).geometry)
        assert BRepTools.Write_s(document_shape(document),str(after))
        assert before.read_bytes()==after.read_bytes()


def test_proof_cancellation_does_not_change_source(tmp_path,monkeypatch):
    from OCP.BRepTools import BRepTools
    from anyfileio.cad import CadOperationCancelled
    from anyfileio_occt import geometry_import
    path=tmp_path/'cancel.brep'; assert BRepTools.Write_s(native_pair(),str(path)); before=path.read_bytes()
    state={'stop':False}; real=geometry_import._prove_ruled_border
    def proved(*args,**kwargs):
        real(*args,**kwargs); state['stop']=True
    monkeypatch.setattr(geometry_import,'_prove_ruled_border',proved)
    with pytest.raises(CadOperationCancelled):
        read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m'),cancellation=lambda:state['stop'])
    assert path.read_bytes()==before


def test_subtolerance_native_line_displacement_is_not_exact(tmp_path):
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.Geom import Geom_Line
    from OCP.gp import gp_Lin,gp_Pnt,gp_Dir
    from OCP.TopoDS import TopoDS
    from anyfileio_occt import _native
    shape=native_pair(); edge=TopoDS.Edge_s(_native.shape_map(shape,'edge').FindKey(1)); builder=BRep_Builder()
    builder.UpdateEdge(edge,Geom_Line(gp_Lin(gp_Pnt(0,0,2.**-40),gp_Dir(1,0,0))),1e-7)
    builder.Range(edge,0.,1.)
    path=tmp_path/'moved.brep'; assert BRepTools.Write_s(shape,str(path))
    with pytest.raises(GeometryInterchangeError,match='native line range and topology endpoints differ'):
        read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m'))


@pytest.mark.parametrize('bent',[False,True])
def test_surface_knot_union_and_monotone_parameter_transport(bent):
    from anygeometry.nurbs import NurbsSurface
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.TopoDS import TopoDS_Face
    from OCP.TopLoc import TopLoc_Location
    from anyfileio_occt._geometry import point,bspline_curve,surface_to_native
    from anyfileio_occt.geometry_import import _prove_ruled_border
    profile=((0,0,0),(0,0,1),(1,0,0)) if bent else ((0,0,0),(1,0,0),(2,0,0))
    support=NurbsSurface(1,1,(0,0,.5,1,1),(0,0,1,1),
        tuple((p,(p[0],1,p[2])) for p in profile))
    surface=surface_to_native(support); builder=BRep_Builder(); face=TopoDS_Face()
    builder.MakeFace(face,surface,TopLoc_Location(),1e-7)
    edge=BRepBuilderAPI_MakeEdge(point(profile[0]),point(profile[-1])).Edge()
    controls=((0,0),(1,0)) if bent else ((0,0),(.25,0),(1,0))
    pc=bspline_curve(controls,1,(0,0,1,1) if bent else (0,0,.5,1,1),dimension=2)
    builder.UpdateEdge(edge,pc,surface,TopLoc_Location(),1e-7)
    builder.Range(edge,surface,TopLoc_Location(),0.,1.)
    if bent:
        # Native PC has no interior knot: its surface-knot crossing alone
        # exposes the off-line lifted point despite matching endpoints.
        with pytest.raises(GeometryInterchangeError,match='pcurve lift differs'):
            _prove_ruled_border(edge,face,support,None)
    else:
        # Different finite native 3D/PC domains and nonconstant PC speed are
        # admitted by an exact, monotone piecewise reparameterization.
        _prove_ruled_border(edge,face,support,None)


@pytest.mark.parametrize('fmt',['step','iges'])
@pytest.mark.parametrize('reverse',[False,True])
def test_ruled_pair_staged_format_refusal(tmp_path,fmt,reverse):
    from test_native_geometry import assert_staged_refusal
    source=owner_pair(reverse);assert_pair(source,reverse_first=reverse)
    assert_staged_refusal(tmp_path/('pair.'+fmt),source)
