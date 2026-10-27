"""Foreign OCCT BREP formats, not ANYgeometry editable-export fixtures."""
import hashlib
import numpy as np
import pytest
pytest.importorskip('OCP')
from OCP.BRep import BRep_Builder,BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
from OCP.BRepTools import BRepTools
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopTools import TopTools_FormatVersion
from OCP.TopoDS import TopoDS,TopoDS_Shape
from OCP.TopLoc import TopLoc_Location
from OCP.gp import gp_Pnt
from anyfileio import read_cad
from anyfileio.cad import CadReadOptions
from anyfileio.geometry import GeometryReadOptions
from anyfileio_occt import _native
from anyfileio_occt.backend import document_shape,document_brep_association
from anyfileio_occt.geometry_import import import_geometry


def foreign_face(triangulated):
    def wire(points):
        polygon=BRepBuilderAPI_MakePolygon()
        for x,y in points:polygon.Add(gp_Pnt(x,y,0))
        polygon.Close();return polygon.Wire()
    maker=BRepBuilderAPI_MakeFace(wire(((0,0),(4,0),(4,3),(0,3))),True)
    maker.Add(wire(((1,1),(1,2),(2,2),(2,1))))
    assert maker.IsDone()
    face=maker.Face()
    if triangulated:
        mesh=BRepMesh_IncrementalMesh(face,.1);mesh.Perform();assert mesh.IsDone()
    return face


def assert_native_face(shape,triangulated):
    assert _native.counts(shape)['face']==1
    assert _native.shape_map(shape,'wire').Extent()==2
    assert _native.shape_map(shape,'edge').Extent()==8
    assert _native.shape_map(shape,'vertex').Extent()==8
    face=TopoDS.Face_s(_native.shape_map(shape,'face').FindKey(1))
    props=GProp_GProps();BRepGProp.SurfaceProperties_s(face,props)
    assert props.Mass()==pytest.approx(11.,abs=1e-12,rel=0)
    edges=_native.shape_map(face,'edge')
    for i in range(1,edges.Extent()+1):
        edge=TopoDS.Edge_s(edges.FindKey(i));pc=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.)
        assert pc is not None
        a,b=BRep_Tool.Range_s(edge,face)
        assert np.isfinite([a,b]).all() and a<b
        value=pc.Value((a+b)/2)
        assert np.isfinite([value.X(),value.Y()]).all()
        lifted=BRep_Tool.Surface_s(face).Value(value.X(),value.Y())
        spatial=BRepAdaptor_Curve(edge).Value((a+b)/2)
        assert (lifted.X(),lifted.Y(),lifted.Z())==pytest.approx(
            (spatial.X(),spatial.Y(),spatial.Z()),abs=1e-12,rel=0)
    triangulation=BRep_Tool.Triangulation_s(face,TopLoc_Location())
    if triangulated:assert triangulation is not None and triangulation.NbTriangles()>0


def assert_foreign_import(path,triangulated,record_property):
    payload=path.read_bytes();digest=hashlib.sha256(payload).hexdigest()
    # An independent ordinary native read verifies the exact same input bytes.
    ordinary=TopoDS_Shape();assert BRepTools.Read_s(ordinary,str(path),BRep_Builder())
    assert_native_face(ordinary,triangulated)
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as doc:
        assert doc.manifest.source_sha256==digest and not doc.source_available
        assert doc.manifest.world_bounds_m==pytest.approx((0,0,0,4,3,0),abs=1e-7,rel=0)
        for kind,count in (('face',1),('wire',2),('edge',8),('vertex',8)):
            assert doc.manifest.topology_counts[kind]==count
        assert_native_face(document_shape(doc),triangulated)
        records,normalization=document_brep_association(doc)
        eligible=payload.startswith(b'\nCASCADE Topology V3,')
        assert (records is not None)==eligible
        record_property('retained_native_records',records is not None)
        if records is not None:assert records.sha256==digest
        assert normalization is not None
        result=import_geometry(doc,options=GeometryReadOptions())
        model=result.geometry
        assert len(model.faces)==1 and len(model.edges)==len(model.vertices)==8
        face=next(iter(model.faces.values()))
        assert len(face.loop)==4 and len(face.holes)==1 and len(face.holes[0])==4
        assert model.validate_topology()==()
        points={tuple(v.position) for v in model.vertices.values()}
        assert points=={(0.,0.,0.),(4.,0.,0.),(4.,3.,0.),(0.,3.,0.),(1.,1.,0.),(1.,2.,0.),(2.,2.,0.),(2.,1.,0.)}
        def polygon_area(loop):
            p=[model.vertices[model.edges[e.edge].start if e.forward else model.edges[e.edge].end].position for e in loop]
            return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(p,p[1:]+p[:1]))/2
        outer=polygon_area(face.loop);hole=polygon_area(face.holes[0])
        assert abs(outer)==12 and abs(hole)==1 and outer*hole<0
        assert abs(outer+hole)==11
        assert result.report.source_sha256==digest
    assert doc.closed and path.read_bytes()==payload
    assert list(path.parent.iterdir())==[path]


@pytest.mark.parametrize('version',[1,2,3])
@pytest.mark.parametrize('newline',['lf','crlf'])
@pytest.mark.parametrize('triangulated',[False,True])
def test_ordinary_foreign_brep_versions_and_lines(tmp_path,version,newline,triangulated,record_property):
    path=tmp_path/'foreign.brep'
    enum=getattr(TopTools_FormatVersion,'TopTools_FormatVersion_VERSION_'+str(version))
    assert BRepTools.Write_s(foreign_face(triangulated),str(path),triangulated,True,enum)
    payload=path.read_bytes().replace(b'\r\n',b'\n')
    assert ('CASCADE Topology V'+str(version)+',').encode() in payload
    if newline=='crlf':payload=payload.replace(b'\n',b'\r\n')
    path.write_bytes(payload)
    assert_foreign_import(path,triangulated,record_property)


def test_ordinary_foreign_default_writer(tmp_path,record_property):
    path=tmp_path/'foreign.brep'
    assert BRepTools.Write_s(foreign_face(True),str(path))
    assert_foreign_import(path,True,record_property)
