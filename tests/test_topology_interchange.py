"""Independent native material/use graph regressions."""
from fractions import Fraction as Q
import pytest
pytest.importorskip('OCP')
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge,BRepBuilderAPI_MakeVertex,BRepBuilderAPI_MakeWire,BRepBuilderAPI_MakeFace
from OCP.TopoDS import TopoDS_Compound,TopoDS
from OCP.gp import gp_Pnt,gp_Trsf,gp_Vec
from OCP.TopLoc import TopLoc_Location
from anyfileio_occt._topology import Work,extract,witness

def compound(*items):
    b=BRep_Builder(); c=TopoDS_Compound(); b.MakeCompound(c)
    for item in items: b.Add(c,item)
    return c

def vertex(x,y=0,z=0): return BRepBuilderAPI_MakeVertex(gp_Pnt(x,y,z)).Vertex()
def edge(a,b): return BRepBuilderAPI_MakeEdge(a,b).Edge()
def prove(a,b,limit=1000000,**kwargs):
    work=Work(limit)
    l=extract(a,Q(1),work,**kwargs); r=extract(b,Q(1),work,**kwargs)
    return l,r,witness(l,r,work)

def test_independent_coincident_edges_and_repeated_uses():
    def fixture():
        a=edge(vertex(0),vertex(1)); b=edge(vertex(0),vertex(1))
        return compound(a,b,a)
    l,r,m=prove(fixture(),fixture())
    assert len(m)==len(l.colors)==len(r.colors)
    assert sum(k=='edge' for k,_,_ in l.entities.values())==2

def test_repeated_use_not_independent_identity():
    a=edge(vertex(0),vertex(1))
    with pytest.raises(Exception,match='counts changed'):
        prove(compound(a,a),compound(edge(vertex(0),vertex(1)),edge(vertex(0),vertex(1))))

def test_same_count_weld_split_refused():
    def fixture(shared):
        a,b,c=vertex(0),vertex(1),vertex(2)
        # Same entity counts but one graph is a chain plus isolated point,
        # the other two disconnected edges, with matching coordinate proposals.
        return compound(edge(a,b),edge(b if shared else vertex(1),c),vertex(1)) if shared else compound(edge(a,b),edge(vertex(1),c))
    with pytest.raises(Exception): prove(fixture(True),fixture(False))

def test_compound_membership_and_isolated_roles():
    a,b,c,d=vertex(0),vertex(1),vertex(2),vertex(3)
    left=compound(compound(a,b),compound(c,d))
    right=compound(compound(a,c),compound(b,d))
    with pytest.raises(Exception,match='witness'): prove(left,right)

def test_oriented_free_wire():
    a,b,c=vertex(0),vertex(1),vertex(2)
    wire=BRepBuilderAPI_MakeWire(edge(a,b),edge(b,c)).Wire()
    prove(wire,wire)
    with pytest.raises(Exception): prove(wire,wire.Reversed())

def test_location_exact_world_attribute():
    a=vertex(2,3,4); t=gp_Trsf(); t.SetTranslation(gp_Vec(10,20,30))
    l,r,m=prove(a.Located(TopLoc_Location(t)),vertex(12,23,34))
    assert list(l.points.values())==list(r.points.values())==[(Q(12),Q(23),Q(34))]

def test_budget_refuses_and_cancellation():
    a=edge(vertex(0),vertex(1))
    with pytest.raises(Exception,match='max_topology_work'): prove(a,a,10)

def polygon(points):
    vertices=[vertex(*p) for p in points]; builder=BRepBuilderAPI_MakeWire()
    for a,b in zip(vertices,vertices[1:]+vertices[:1]): builder.Add(edge(a,b))
    return builder.Wire()

def face_at(x=0):
    return BRepBuilderAPI_MakeFace(polygon([(x,0),(x+1,0),(x+1,1),(x,1)])).Face()

def test_reversed_material_face_and_changed_hole_refuse():
    face=face_at()
    prove(face,face)
    with pytest.raises(Exception): prove(face,face.Reversed())
    outer=polygon([(0,0),(4,0),(4,4),(0,4)])
    hole=polygon([(1,1),(1,2),(2,2),(2,1)])
    a=BRepBuilderAPI_MakeFace(outer); a.Add(hole)
    b=BRepBuilderAPI_MakeFace(outer); b.Add(TopoDS.Wire_s(hole.Reversed()))
    with pytest.raises(Exception): prove(a.Face(),b.Face())

def shell(*faces):
    from OCP.TopoDS import TopoDS_Shell
    builder=BRep_Builder(); result=TopoDS_Shell(); builder.MakeShell(result)
    for f in faces: builder.Add(result,f)
    return result

def test_declared_shell_reassignment_and_transport_carrier():
    from anyfileio_occt._topology import compare
    a,b,c,d=[face_at(x) for x in (0,2,4,6)]
    with pytest.raises(Exception): prove(compound(shell(a,b),shell(c,d)),compound(shell(a,c),shell(b,d)))
    compare(compound(a,b),compound(shell(a,b)),Q(1),Q(1),Work(1000000),transport=True)
    with pytest.raises(Exception):
        compare(compound(shell(a,b),c),compound(shell(a,c),shell(b)),Q(1),Q(1),Work(1000000),transport=True)

def test_coincident_face_automorphisms():
    left=compound(face_at(),face_at()); right=compound(face_at(),face_at())
    prove(left,right)

def test_cancel_extraction():
    class Cancel:
        def __call__(self): raise RuntimeError('cancel topology')
    with pytest.raises(RuntimeError,match='cancel topology'):
        extract(face_at(),Q(1),Work(10000,Cancel()))

def test_product_oriented_repeated_use_membership():
    from anyfileio_occt._topology import compare
    a,b=edge(vertex(0),vertex(1)),edge(vertex(2),vertex(3))
    source=compound(a,a,b); target=compound(a,a,b)
    groups=(('A',compound(a,a)),('B',compound(b)))
    compare(source,target,Q(1),Q(1),Work(1000000),transport=True,source_groups=groups,target_groups=groups)
    with pytest.raises(Exception):
        compare(source,target,Q(1),Q(1),Work(1000000),transport=True,source_groups=groups,
                target_groups=(('A',compound(a)),('B',compound(a,b))))

def test_exact_file_graph_tamper_atomic_and_budget(tmp_path,monkeypatch):
    from test_native_geometry import square
    from anyfileio.geometry import write_geometry,GeometryWriteOptions,GeometryInterchangeError
    from anyfileio_occt import _native
    from anygeometry.serialization import to_dict
    model=square();before=to_dict(model);attempted=[]
    path=tmp_path/'exact.brep'; path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.topology.budget'):
        write_geometry(path,model,options=GeometryWriteOptions(max_topology_work=10))
    assert path.read_bytes()==b'old'
    original=_native.write_shape
    def changed(shape,path,fmt,unit='m',cancellation=None):
        faces=_native.shape_map(shape,'face')
        output=compound(faces.FindKey(1).Reversed())
        attempted.append(True)
        original(output,path,fmt,unit,cancellation)
    monkeypatch.setattr(_native,'write_shape',changed)
    with pytest.raises(GeometryInterchangeError,match='geometry.association.source_changed'):
        write_geometry(path,model)
    assert path.read_bytes()==b'old'

    assert attempted==[True] and to_dict(model)==before and list(tmp_path.iterdir())==[path]

def test_closed_edge_direction_typed_refusal():
    from OCP.gp import gp_Circ,gp_Ax2,gp_Dir
    circle=BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(),gp_Dir(0,0,1)),1)).Edge()
    with pytest.raises(Exception,match='geometry.topology.direction_unsupported'): prove(circle,circle)

def test_nested_rotated_placement_and_exact_units():
    from OCP.gp import gp_Ax1,gp_Dir
    from anyfileio_occt._topology import compare
    import math
    rotation=gp_Trsf(); rotation.SetRotation(gp_Ax1(gp_Pnt(),gp_Dir(0,0,1)),math.pi/2)
    translation=gp_Trsf(); translation.SetTranslation(gp_Vec(4,5,6))
    original=edge(vertex(0),vertex(2))
    nested=compound(compound(original).Located(TopLoc_Location(rotation))).Located(TopLoc_Location(translation))
    # Same container graph through independent native copying/readback isn't
    # needed to establish affine evaluation: inspect exact stored coefficients.
    g=extract(nested,Q(1,1000),Work(1000000))
    points=list(g.points.values()); assert len(points)==2
    assert (Q(4,1000),Q(5,1000),Q(6,1000)) in points
    prove(nested,nested)

def test_candidate_budget_bounds_coincident_search():
    left=compound(*[edge(vertex(0),vertex(1)) for _ in range(12)])
    right=compound(*[edge(vertex(0),vertex(1)) for _ in range(12)])
    with pytest.raises(Exception,match='geometry.topology.budget'): prove(left,right,2000)

@pytest.mark.parametrize('unit',['cm','mm','in'])
@pytest.mark.parametrize('operation',['success','failure','cancel'])
def test_iges_raw_model_units_and_guard(tmp_path,monkeypatch,unit,operation):
    import OCP.IGESControl as iges
    from OCP.Interface import Interface_Static
    from OCP.BRep import BRep_Tool
    from anyfileio_occt import _native
    from anyfileio_occt._units import _CANONICAL_SCALES
    from anyfileio.cad import CadOperationError,CadOperationCancelled
    path=tmp_path/('known-'+unit+'.iges')
    writer=iges.IGESControl_Writer; writer_seen=[]
    class Writer:
        def __init__(self,*args): self.actual=writer(*args)
        def __getattr__(self,key): return getattr(self.actual,key)
        def AddShape(self,shape):
            section=self.actual.Model().GlobalSection()
            assert section.CascadeUnit()==1000 and section.UnitValue()==_CANONICAL_SCALES[unit]
            writer_seen.append(section.CascadeUnit())
            return self.actual.AddShape(shape)
    monkeypatch.setattr(iges,'IGESControl_Writer',Writer)
    _native.write_shape(edge(vertex(0),vertex(2)),path,'iges',unit)
    assert writer_seen==[1000.]
    previous=Interface_Static.CVal_s('xstep.cascade.unit')
    real=iges.IGESControl_Reader; state={'stop':False}; seen=[]
    # Inspect literal parsed IGES entity coordinates BEFORE any transfer. This
    # independently checks the writer rather than trusting compensating readers.
    parsed=real(); parsed.ReadFile(str(path)); model=parsed.IGESModel()
    header=model.GlobalSection()
    assert header.UnitFlag()=={'cm':10,'mm':2,'in':1}[unit]
    assert header.UnitName().ToCString()=={'cm':'CM','mm':'MM','in':'INCH'}[unit]
    line=model.Value(1); assert line.TypeNumber()==110
    physical_factor={'cm':Q(1,100),'mm':Q(1,1000),'in':Q(127,5000)}[unit]
    assert float(Q(line.EndPoint().X())*physical_factor)==pytest.approx(2,abs=1e-12,rel=0)
    class Reader:
        def __init__(self): self.actual=real()
        def __getattr__(self,key): return getattr(self.actual,key)
        def TransferRoots(self):
            value=self.actual.IGESModel().GlobalSection().CascadeUnit(); seen.append(value)
            assert value==1000*_CANONICAL_SCALES[unit]
            if operation=='failure': return 0
            count=self.actual.TransferRoots()
            if operation=='cancel': state['stop']=True
            return count
    monkeypatch.setattr(iges,'IGESControl_Reader',Reader)
    if operation!='success':
        with pytest.raises(CadOperationCancelled if operation=='cancel' else CadOperationError):
            _native.read_shape(path,'iges',cancellation=lambda:state['stop'],raw_coordinates=True)
    else:
        raw,decision=_native.read_shape(path,'iges',raw_coordinates=True)
        points=_native.shape_map(raw,'vertex')
        physical=sorted(float(Q(BRep_Tool.Pnt_s(TopoDS.Vertex_s(points.FindKey(i))).X())*Q(str(_CANONICAL_SCALES[unit]))) for i in range(1,points.Extent()+1))
        assert physical==pytest.approx([0,2],abs=1e-12,rel=0)
        monkeypatch.setattr(iges,'IGESControl_Reader',real)
        normalized,_=_native.read_shape(path,'iges')
        points=_native.shape_map(normalized,'vertex')
        assert sorted(BRep_Tool.Pnt_s(TopoDS.Vertex_s(points.FindKey(i))).X() for i in range(1,points.Extent()+1))==pytest.approx([0,2],abs=1e-12,rel=0)
    assert seen==[1000*_CANONICAL_SCALES[unit]]
    assert Interface_Static.CVal_s('xstep.cascade.unit')==previous


@pytest.mark.parametrize('replacement,override,code',[('2HXX','cm','cad.units.override_unsupported'),('2HMM',None,'cad.units.inconsistent')])
def test_iges_unproven_header_decode_refuses(tmp_path,replacement,override,code):
    from anyfileio_occt import _native
    from anyfileio.cad import CadOperationError
    path=tmp_path/'header.iges'; _native.write_shape(edge(vertex(0),vertex(2)),path,'iges','cm')
    contents=path.read_bytes(); assert contents.count(b'2HCM')==1
    path.write_bytes(contents.replace(b'2HCM',replacement.encode('ascii'),1))
    with pytest.raises(CadOperationError,match=code):
        _native.read_shape(path,'iges',override,raw_coordinates=True)
