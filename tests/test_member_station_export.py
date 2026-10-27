"""Member stations place whole current edges, independently of curve domains."""
import pytest
pytest.importorskip('OCP')
from anygeometry import GeometryModel, OrientedEdge
from anygeometry.nurbs import NurbsCurve
from anygeometry.serialization import to_dict
from anyfileio import read_cad
from anyfileio.cad import CadReadOptions
from anyfileio.geometry import write_geometry, read_geometry, GeometryWriteOptions, GeometryReadOptions


def chain(kind='plain'):
    m=GeometryModel();p=m.add_part(name='Source Member')
    a,b,c=[m.add_point(x,0,0) for x in (0,1,3)]
    first=m.add_line(a,b)
    if kind in ('basis','reverse_basis'):
        reverse=kind=='reverse_basis'
        curve=NurbsCurve(1,(2.,2.,6.,6.),((0.,0.,0.),(4.,0.,0.)),domain=(5.,3.) if reverse else (3.,5.))
        last=m.add_curve(c if reverse else b,b if reverse else c,curve)
        uses=[first,OrientedEdge(last,False) if reverse else last]
    else:last=m.add_line(b,c);uses=[first,last]
    member=m.add_member(uses,part_id=p)
    assert [(u.parent_range.start,u.parent_range.end) for u in (m.member_edge_uses[i] for i in m.members[member].edge_use_ids)]==pytest.approx([(0,1/3),(1/3,1)])
    if kind=='reverse':m.reverse_member(member)
    if kind=='split_edge':m.split_edge(last,.25)
    if kind=='split_member':m.split_member(member,.5)
    return m


def native_chains(doc):
    from anyfileio_occt import _native
    from anyfileio_occt.backend import document_shape
    from OCP.TopoDS import TopoDS
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopAbs import TopAbs_REVERSED
    wires=_native.shape_map(document_shape(doc),'wire');result=[]
    for i in range(1,wires.Extent()+1):
        walk=BRepTools_WireExplorer(TopoDS.Wire_s(wires.FindKey(i)));points=[]
        while walk.More():
            edge=walk.Current();curve=BRepAdaptor_Curve(edge)
            start,end=curve.FirstParameter(),curve.LastParameter()
            if edge.Orientation()==TopAbs_REVERSED:start,end=end,start
            x,y=curve.Value(start).X(),curve.Value(end).X()
            assert curve.Value((start+end)/2).X()==pytest.approx((x+y)/2,abs=1e-12)
            if points:assert points[-1]==pytest.approx(x,abs=1e-12)
            else:points.append(x)
            points.append(y);walk.Next()
        result.append(points)
    return sorted(result)


def assert_member_reference(doc,model,report,member_id):
    """Resolve THIS Member's ref, and check ordered oriented material uses."""
    from anyfileio_occt import _native
    from anyfileio_occt.backend import document_shape
    from OCP.TopoDS import TopoDS,TopoDS_Iterator
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.BRepTools import BRepTools_WireExplorer
    shape=document_shape(doc);wires=_native.shape_map(shape,'wire');edges=_native.shape_map(shape,'edge')
    reference,=report.geometry_to_cad[model.handle('member',member_id)]
    wire=TopoDS.Wire_s(wires.FindKey(reference.local_id));expected=[]
    for use_id in model.members[member_id].edge_use_ids:
        use=model.member_edge_uses[use_id]
        edge_ref,=report.geometry_to_cad[model.handle('edge',use.edge_id)]
        expected.append((edge_ref.local_id,int(use.orientation)==-1))
    iterator=TopoDS_Iterator(wire);actual=[]
    while iterator.More():
        edge=iterator.Value();actual.append((edges.FindIndex(edge),edge.Orientation()==TopAbs_REVERSED));iterator.Next()
    assert actual==expected
    # Connectivity traversal must not omit a repeated/branch use either.
    walk=BRepTools_WireExplorer(wire);walked=[]
    while walk.More():
        edge=walk.Current();walked.append((edges.FindIndex(edge),edge.Orientation()==TopAbs_REVERSED));walk.Next()
    assert walked==expected


@pytest.mark.parametrize('kind',['plain','reverse','split_edge','split_member','basis','reverse_basis'])
@pytest.mark.parametrize('units',[('m','cm'),('mm','mm')])
def test_whole_current_edges_and_native_history(tmp_path,kind,units):
    source,output=units;m=chain(kind);m.set_document_settings(units=source);before=to_dict(m)
    path=tmp_path/'member.brep';report=write_geometry(path,m,options=GeometryWriteOptions(output_length_unit=output))
    assert any('persistent member station ranges' in loss for loss in report.metadata_losses)
    expected={'reverse':[[3,1,0]],'split_edge':[[0,1,1.5,3]],'split_member':[[0,1,1.5],[1.5,3]]}.get(kind,[[0,1,3]])
    scale=1 if source=='m' else .001
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override=output)) as doc:
        actual=native_chains(doc)
        assert len(actual)==len(expected)
        for got,want in zip(actual,expected):assert got==pytest.approx([x*scale for x in want],abs=1e-12)
        universe={r.cad_ref for r in doc.manifest.shapes}
        if kind in ('basis','reverse_basis'):
            from anyfileio_occt import _native
            from anyfileio_occt.backend import document_shape
            from OCP.TopoDS import TopoDS
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            reference,=report.geometry_to_cad[m.handle('edge',2)]
            edge=_native.shape_map(document_shape(doc),'edge').FindKey(reference.local_id)
            curve=BRepAdaptor_Curve(TopoDS.Edge_s(edge))
            assert (curve.FirstParameter(),curve.LastParameter())==pytest.approx((3,5),abs=1e-12)
            assert sorted((curve.Value(3).X(),curve.Value(5).X()))==pytest.approx([scale,3*scale],abs=1e-12)
        for member in m.members:
            refs=report.geometry_to_cad[m.handle('member',member)]
            assert len(refs)==1 and refs[0].kind=='wire' and refs[0] in universe
            assert_member_reference(doc,m,report,member)
        assert all(set(refs)<=universe for refs in report.geometry_to_cad.values())
    imported=read_geometry(path,options=GeometryReadOptions(source_length_unit_override=output))
    restored=imported.geometry
    assert not restored.members and not restored.parts and len(restored.edges)==len(m.edges)
    assert len(restored.vertices)==len(m.vertices)
    assert any('grouping is not inferred' in loss for loss in imported.report.metadata_losses)
    assert all(not part.name or part.name!='Source Member' for part in restored.parts.values())
    native=tmp_path/'member.anygeometry.json';write_geometry(native,m)
    assert to_dict(read_geometry(native).geometry)==before
    assert to_dict(m)==before


def test_member_cancel_and_late_failure_preserve_destination(tmp_path,monkeypatch):
    from anyfileio.cad import CadOperationCancelled
    from anyfileio_occt import _output_references
    m=chain('split_edge');before=to_dict(m);path=tmp_path/'atomic.brep';path.write_bytes(b'old')
    with pytest.raises(CadOperationCancelled):write_geometry(path,m,cancellation=lambda:True)
    assert path.read_bytes()==b'old' and to_dict(m)==before
    sentinel=RuntimeError('late member report failure')
    def fail(*args,**kwargs):raise sentinel
    monkeypatch.setattr(_output_references,'reconcile',fail)
    with pytest.raises(RuntimeError) as error:write_geometry(path,m)
    assert error.value is sentinel and path.read_bytes()==b'old' and to_dict(m)==before
    assert list(tmp_path.iterdir())==[path]


def test_shared_and_coincident_members_keep_distinct_uses(tmp_path):
    m=chain();part=next(iter(m.parts));edges=list(m.edges)
    m.add_member(edges,part_id=part)
    a,b=m.add_points(((0,0,0),(1,0,0)));m.add_member([m.add_line(a,b)],part_id=part)
    before=to_dict(m);path=tmp_path/'uses.brep';report=write_geometry(path,m)
    refs=[report.geometry_to_cad[m.handle('member',i)][0] for i in m.members]
    assert len(set(refs))==3
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as doc:
        for member in m.members:assert_member_reference(doc,m,report,member)
        assert native_chains(doc)==[[0,1],[0,1,3],[0,1,3]]
        assert doc.manifest.topology_counts['edge']==3 and doc.manifest.topology_counts['vertex']==5
    assert to_dict(m)==before


@pytest.mark.parametrize('kind',['closed','backtrack','repeated'])
def test_public_closed_and_repeated_member_uses(tmp_path,kind):
    from anyfileio.geometry import GeometryInterchangeError
    m=GeometryModel();part=m.add_part();a,b,c=m.add_points(((0,0,0),(1,0,0),(1,1,0)))
    e=m.add_line(a,b)
    if kind=='closed':uses=[e,m.add_line(b,c),m.add_line(c,a)]
    else:uses=[OrientedEdge(e,True),OrientedEdge(e,False)]+([OrientedEdge(e,True)] if kind=='repeated' else [])
    if kind!='closed':
        # The public owner refuses duplicate edge uses before CAD; consumed
        # allocator IDs remain reserved after its transaction rollback.
        from anygeometry.errors import GeometryError
        before=to_dict(m)
        with pytest.raises(GeometryError,match='uses edge .* more than once'):m.add_member(uses,part_id=part)
        after=to_dict(m)
        assert {k:v for k,v in after.items() if k not in ('id_state','checksum')}=={k:v for k,v in before.items() if k not in ('id_state','checksum')}
        return
    mid=m.add_member(uses,part_id=part);before=to_dict(m);path=tmp_path/'uses.brep';path.write_bytes(b'old')
    try:report=write_geometry(path,m)
    except GeometryInterchangeError as error:
        assert error.code.startswith('geometry.') and path.read_bytes()==b'old'
    else:
        with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as doc:
            assert_member_reference(doc,m,report,mid)
    assert to_dict(m)==before


def test_symmetric_member_refs_after_compound_reorder(tmp_path,monkeypatch):
    from anyfileio_occt import _native
    from OCP.TopoDS import TopoDS_Compound,TopoDS_Iterator
    from OCP.BRep import BRep_Builder
    m=GeometryModel()
    for x in (-3,1):
        part=m.add_part(name='same');a,b,c=m.add_points(((x,0,0),(x+1,0,0),(x+2,0,0)))
        m.add_member([m.add_line(a,b),m.add_line(b,c)],part_id=part)
    original=_native.write_shape
    def reorder(shape,path,fmt,unit='m',cancellation=None):
        it=TopoDS_Iterator(shape);children=[]
        while it.More():children.append(it.Value());it.Next()
        builder=BRep_Builder();changed=TopoDS_Compound();builder.MakeCompound(changed)
        for child in reversed(children):builder.Add(changed,child)
        return original(changed,path,fmt,unit,cancellation)
    monkeypatch.setattr(_native,'write_shape',reorder)
    before=to_dict(m);path=tmp_path/'symmetric.brep';report=write_geometry(path,m)
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as doc:
        for member in m.members:assert_member_reference(doc,m,report,member)
    assert to_dict(m)==before
