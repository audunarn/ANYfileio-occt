"""Literal representation-location guards, independent of TopoDS locations."""
from fractions import Fraction as Q
import pytest
pytest.importorskip('OCP')
from OCP.BRep import BRep_Tool,BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Curve,BRepAdaptor_Surface
from OCP.TopoDS import TopoDS
from OCP.TopLoc import TopLoc_Location,TopLoc_Datum3D
from OCP.gp import gp_Trsf,gp_Vec
from anyfileio_occt import _native
from test_plane_nurbs_trims import native_four_faces


def _trace(shape):
    faces=_native.shape_map(shape,'face'); edges=_native.shape_map(shape,'edge')
    for i in range(1,edges.Extent()+1):
        edge=TopoDS.Edge_s(edges.FindKey(i))
        if sum(_native.shape_map(faces.FindKey(j),'edge').Contains(edge) for j in range(1,faces.Extent()+1))==4:
            return edge
    raise AssertionError('four-face trace missing')


def _location(identity=False):
    trsf=gp_Trsf(); trsf.SetTranslation(gp_Vec(0. if identity else .1,0.,0.))
    # Force an actual datum even for coefficient identity: IsIdentity() tests
    # the location container, whereas the coefficient guard tests the transform.
    return TopLoc_Location(TopLoc_Datum3D(trsf))


def _located_curve(shape,identity=False,location=None):
    edge=_trace(shape); representation=TopLoc_Location()
    curve=BRep_Tool.Curve_s(edge,representation,0.,0.)
    assert representation.IsIdentity()
    location=_location(identity) if location is None else location; local=curve.Copy(); local.Transform(location.Transformation().Inverted())
    BRep_Builder().UpdateEdge(edge,local,location,1e-7)
    return edge,local,location


def _located_surface(shape,plane=False,identity=False,location=None):
    faces=_native.shape_map(shape,'face'); face=TopoDS.Face_s(faces.FindKey(3 if plane else 1))
    representation=TopLoc_Location(); surface=BRep_Tool.Surface_s(face,representation)
    assert representation.IsIdentity()
    edges=_native.shape_map(face,'edge'); saved=[]
    for i in range(1,edges.Extent()+1):
        edge=TopoDS.Edge_s(edges.FindKey(i))
        saved.append((edge,BRep_Tool.CurveOnSurface_s(edge,face,0.,0.),BRep_Tool.Range_s(edge,face)))
    location=_location(identity) if location is None else location; local=surface.Copy(); local.Transform(location.Transformation().Inverted())
    builder=BRep_Builder(); builder.UpdateFace(face,local,location,1e-7)
    for edge,pc,domain in saved:
        builder.UpdateEdge(edge,pc,local,location,1e-7); builder.Range(edge,local,location,*domain)
    return face,local,location


def _exact_transformed(point,location):
    values=tuple(Q(x) for x in (point.X(),point.Y(),point.Z())); trsf=location.Transformation()
    return tuple(sum(Q(trsf.Value(r,c))*values[c-1] for c in (1,2,3))+Q(trsf.Value(r,4)) for r in (1,2,3))


def test_curve_representation_location_is_independent_and_adaptor_rounds():
    shape=native_four_faces(); edge,local,location=_located_curve(shape)
    assert edge.Location().IsIdentity()
    actual=TopLoc_Location(); stored=BRep_Tool.Curve_s(edge,actual,0.,0.)
    assert not actual.IsIdentity()
    adapted=BRepAdaptor_Curve(edge).BSpline()
    discrepancies=[]
    for i in range(1,stored.NbPoles()+1):
        ideal=_exact_transformed(stored.Pole(i),actual); rounded=tuple(Q(x) for x in (adapted.Pole(i).X(),adapted.Pole(i).Y(),adapted.Pole(i).Z()))
        discrepancies.extend(abs(a-b) for a,b in zip(ideal,rounded))
    assert max(discrepancies)>0
    print('CURVE_MAX_LITERAL_ADAPTOR_DISCREPANCY',float(max(discrepancies)))


def test_surface_representation_location_is_independent_and_adaptor_rounds():
    shape=native_four_faces(); face,local,location=_located_surface(shape)
    assert face.Location().IsIdentity()
    actual=TopLoc_Location(); stored=BRep_Tool.Surface_s(face,actual)
    assert not actual.IsIdentity()
    adapted=BRepAdaptor_Surface(face,False).BSpline(); discrepancies=[]
    for i in range(1,stored.NbUPoles()+1):
        for j in range(1,stored.NbVPoles()+1):
            ideal=_exact_transformed(stored.Pole(i,j),actual); point=adapted.Pole(i,j); rounded=tuple(Q(x) for x in (point.X(),point.Y(),point.Z()))
            discrepancies.extend(abs(a-b) for a,b in zip(ideal,rounded))
    assert max(discrepancies)>0
    print('SURFACE_MAX_LITERAL_ADAPTOR_DISCREPANCY',float(max(discrepancies)))

@pytest.mark.parametrize('kind',['curve','nurbs','plane','nurbs_chain'])
def test_literal_certificate_guards_precede_adaptor_conversion(monkeypatch,kind):
    from anyfileio_occt import _trim_bounds,geometry_import
    from anyfileio.geometry import GeometryInterchangeError
    shape=native_four_faces()
    if kind=='curve':
        edge,_,_=_located_curve(shape)
        import OCP.BRepAdaptor as adaptors
        monkeypatch.setattr(adaptors,'BRepAdaptor_Curve',lambda *args:pytest.fail('rounded curve adaptor called before location refusal'))
        with pytest.raises(GeometryInterchangeError,match='Curve representation location'):
            _trim_bounds._native_curve(edge)
    else:
        location=_rounded_identity_chain()[0] if kind=='nurbs_chain' else None
        face,_,_=_located_surface(shape,plane=kind=='plane',location=location);edge=_trace(shape)
        monkeypatch.setattr(geometry_import,'surface_from_native',lambda *args:pytest.fail('rounded surface conversion called before location refusal'))
        with pytest.raises(GeometryInterchangeError,match='Surface representation location'):
            _trim_bounds._native_trim(edge,face)


@pytest.mark.parametrize('kind',['curve','nurbs','plane'])
def test_raw_import_representation_location_refuses_without_mutating_source(tmp_path,monkeypatch,kind):
    from OCP.BRepTools import BRepTools
    from anyfileio.geometry import GeometryReadOptions,GeometryInterchangeError
    from anyfileio_occt import _trim_bounds
    from anyfileio_occt.geometry_import import import_geometry
    from anyfileio_occt.backend import document_raw_brep,document_shape
    from test_native_geometry import read
    shape=native_four_faces()
    if kind=='curve':_located_curve(shape)
    else:_located_surface(shape,plane=kind=='plane')
    path=tmp_path/'located.brep';assert BRepTools.Write_s(shape,str(path));original=path.read_bytes();checkpoints=[]
    monkeypatch.setattr(_trim_bounds,'_certify',lambda *args:pytest.fail('literal proof reached rounded representation'))
    with read(path,'m') as document:
        state=document._backend_state_for('occt');raw,_=document_raw_brep(document)
        before=tmp_path/'before.brep';after=tmp_path/'after.brep';assert BRepTools.Write_s(raw,str(before))
        with pytest.raises(GeometryInterchangeError,match='geometry.bounds.location_unsupported'):
            import_geometry(document,options=GeometryReadOptions(fidelity='approximate',max_deviation_m=.01,max_segments=20000),
                cancellation=lambda:checkpoints.append(1) or False)
        assert BRepTools.Write_s(raw,str(after)) and before.read_bytes()==after.read_bytes()
        assert document_shape(document) is not None and not state.session.closed
    assert state.session.closed and not state.session._resources
    assert checkpoints and path.read_bytes()==original


@pytest.mark.parametrize('kind',['curve','nurbs','plane'])
def test_coefficient_identity_representation_datum_is_admitted(kind):
    from anyfileio_occt import _trim_bounds
    shape=native_four_faces()
    if kind=='curve':
        edge,_,location=_located_curve(shape,identity=True)
        result=_trim_bounds._native_curve(edge)
    else:
        face,_,location=_located_surface(shape,plane=kind=='plane',identity=True)
        result=_trim_bounds._native_trim(_trace(shape),face)
    assert not location.IsIdentity()
    assert _trim_bounds._identity_location_coefficients(location)
    lo,hi=result.bounds(0.,1.);assert len(lo)==len(hi)==3


def test_cancellation_with_literal_location_preserves_input_and_session(tmp_path):
    from OCP.BRepTools import BRepTools
    from anyfileio.geometry import GeometryReadOptions
    from anyfileio.cad import CadOperationCancelled
    from anyfileio_occt.geometry_import import import_geometry
    from test_native_geometry import read
    shape=native_four_faces();_located_curve(shape);path=tmp_path/'cancel.brep';assert BRepTools.Write_s(shape,str(path));original=path.read_bytes();calls=[]
    with read(path,'m') as document:
        state=document._backend_state_for('occt')
        with pytest.raises(CadOperationCancelled):
            import_geometry(document,options=GeometryReadOptions(fidelity='approximate',max_deviation_m=.01,max_segments=20000),
                cancellation=lambda:calls.append(1) or len(calls)>=3)
    assert len(calls)==3 and state.session.closed and not state.session._resources and path.read_bytes()==original


def _rounded_identity_chain():
    for values in ((.1,.2,-(.1+.2)),(-(.1+.2),.1,.2)):
        location=TopLoc_Location()
        for value in values:
            transform=gp_Trsf();transform.SetTranslation(gp_Vec(value,0.,0.))
            location=location.Multiplied(TopLoc_Location(TopLoc_Datum3D(transform)))
        transform=location.Transformation()
        if all(transform.Value(r,c)==float(r==c) for r in (1,2,3) for c in (1,2,3,4)):
            assert sum(map(Q,values))!=0
            return location,values
    raise AssertionError('No cached-identity/literal-nonidentity chain found')


def test_cached_location_composition_can_hide_literal_residue():
    location,values=_rounded_identity_chain()
    assert location.Transformation().Value(1,4)==0.
    assert sum(map(Q,values))!=0
    print('CACHED_IDENTITY_LITERAL_TRANSLATION',sum(map(Q,values)))


@pytest.mark.parametrize('kind',['curve','nurbs','plane'])
def test_each_literal_datum_is_guarded_even_if_cached_composite_is_identity(tmp_path,kind):
    from OCP.BRepTools import BRepTools
    from anyfileio.geometry import GeometryReadOptions,GeometryInterchangeError
    from anyfileio_occt import _trim_bounds
    from anyfileio_occt.geometry_import import import_geometry
    from test_native_geometry import read
    location,values=_rounded_identity_chain();shape=native_four_faces()
    if kind=='curve':_located_curve(shape,location=location)
    else:_located_surface(shape,plane=kind=='plane',location=location)
    assert not _trim_bounds._identity_location_coefficients(location)
    path=tmp_path/'chain.brep';assert BRepTools.Write_s(shape,str(path));before=path.read_bytes()
    with read(path,'m') as document:
        state=document._backend_state_for('occt')
        # Rereading may recompose the chain in another floating order. The
        # NURBS pair can then trigger the preexisting exact ruled-location
        # guard before raw certification. Both are explicit location refusals;
        # the direct guard-order test separately requires our raw guard.
        code='(geometry.bounds.location_unsupported|located support needs exact coefficient transport)' if kind=='nurbs' else 'geometry.bounds.location_unsupported'
        with pytest.raises(GeometryInterchangeError,match=code):
            import_geometry(document,options=GeometryReadOptions(fidelity='approximate',max_deviation_m=.01,max_segments=20000))
    assert state.session.closed and not state.session._resources and path.read_bytes()==before
