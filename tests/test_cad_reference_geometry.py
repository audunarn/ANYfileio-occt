"""Real product affiliation without inferred physical members or coordinate welds."""
from pathlib import Path
import pytest
pytest.importorskip('OCP')
from anyfileio import read_cad
from anyfileio.cad import CadReadOptions,CadOperationCancelled
from anyfileio.geometry import read_geometry,write_geometry,GeometryInterchangeError,GeometryReadOptions
from anygeometry import GeometryModel
from anygeometry.serialization import to_dict
from anyfileio_occt._reference_geometry import KEY,affiliations


def line():
    model=GeometryModel();a=model.add_point(0,0,0);b=model.add_point(2,0,0);model.add_line(a,b)
    return model


def inspected(path):
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False)) as doc:
        return doc.manifest


def assert_line_product(model,name=None):
    assert len(model.parts)==1 and not model.members and not model.sheets
    assert len(model.edges)==1 and len(model.vertices)==2
    part=next(iter(model.parts.values()))
    if name is not None:assert part.name==name
    refs=affiliations(model)[part.id]
    assert len(refs)==1 and refs[0].kind=='edge'
    edge=model.edges[refs[0].id]
    assert model.vertices[edge.start].position==pytest.approx((0,0,0),abs=1e-12)
    assert model.vertices[edge.end].position==pytest.approx((2,0,0),abs=1e-12)


def test_native_step_free_line_import_brep_geometry_and_native_persistence(tmp_path):
    first=tmp_path/'first.step';make_products(first);payload=first.read_bytes()
    model=read_geometry(first).geometry;before=to_dict(model)
    assert_line_product(model);name=next(iter(model.parts.values())).name
    native=tmp_path/'retained.anygeometry.json';write_geometry(native,model)
    restored=read_geometry(native).geometry
    assert restored.model_id==model.model_id and restored.groups==model.groups
    assert_line_product(restored,name)
    second=tmp_path/'second.brep';write_geometry(second,restored)
    actual=inspected_brep(second)
    assert actual.topology_counts['edge']==1 and actual.topology_counts['vertex']==2
    assert actual.world_bounds_m==pytest.approx((0,0,0,2,0,0),abs=1e-12)
    assert_line_product(staged_product_cycle(tmp_path,restored),name)
    assert to_dict(model)==before and to_dict(restored)==before and first.read_bytes()==payload


@pytest.mark.skipif(not Path('C:/ANYworkspaceWork/anyfileio-geometry-20261027/free-line-first.step').is_file(),reason='preserved installed input only available in development evidence')
def test_preserved_installed_free_line_input(tmp_path):
    path=Path('C:/ANYworkspaceWork/anyfileio-geometry-20261027/free-line-first.step');payload=path.read_bytes()
    model=read_geometry(path).geometry;assert_line_product(model)
    assert_line_product(staged_product_cycle(tmp_path,model))
    assert path.read_bytes()==payload


def make_products(path,*,point=False,mixed=False):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge,BRepBuilderAPI_MakeVertex,BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Pnt
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    from anyfileio_occt._xde import write_groups
    builder=BRep_Builder();shape=TopoDS_Compound();builder.MakeCompound(shape)
    builder.Add(shape,BRepBuilderAPI_MakeVertex(gp_Pnt(3,4,5)).Vertex() if point else BRepBuilderAPI_MakeEdge(gp_Pnt(0,0,0),gp_Pnt(2,0,0)).Edge())
    if mixed:
        polygon=BRepBuilderAPI_MakePolygon()
        for p in ((0,2,0),(1,2,0),(1,3,0),(0,3,0)):polygon.Add(gp_Pnt(*p))
        polygon.Close();builder.Add(shape,BRepBuilderAPI_MakeFace(polygon.Wire()).Face())
    write_groups([('Reference product',shape)],path)
    return shape


@pytest.mark.parametrize('kind',['point','edge','mixed'])
def test_named_reference_and_carrier_import_and_native_persistence(tmp_path,kind):
    first=tmp_path/'product.step';make_products(first,point=kind=='point',mixed=kind=='mixed')
    model=read_geometry(first).geometry;before=to_dict(model)
    part=next(iter(model.parts.values()));refs=affiliations(model)[part.id]
    assert part.name=='Reference product' and not model.members
    assert len(refs)==1 and refs[0].kind==('vertex' if kind=='point' else 'edge')
    assert len(model.sheets)==(1 if kind=='mixed' else 0)
    final=staged_product_cycle(tmp_path,model)
    assert next(iter(final.parts.values())).name=='Reference product'
    assert not final.members and len(final.sheets)==len(model.sheets)
    assert len(final.edges)==len(model.edges) and len(final.vertices)==len(model.vertices)
    assert inspected(first).world_bounds_m==pytest.approx((3,4,5,3,4,5) if kind=='point' else (0,0,0,2,3 if kind=='mixed' else 0,0),abs=1e-12)
    if kind=='point':assert next(iter(final.vertices.values())).position==pytest.approx((3,4,5),abs=1e-12)
    else:
        edge=final.edges[affiliations(final)[next(iter(final.parts))][0].id]
        assert final.vertices[edge.start].position==pytest.approx((0,0,0),abs=1e-12)
        assert final.vertices[edge.end].position==pytest.approx((2,0,0),abs=1e-12)
    assert to_dict(model)==before


def test_later_unowned_line_not_attached_to_imported_product(tmp_path):
    first=tmp_path/'first.step';make_products(first);model=read_geometry(first).geometry
    a=model.add_point(10,0,0);b=model.add_point(12,0,0);added=model.add_line(a,b)
    assert all(r.id!=added for refs in affiliations(model).values() for r in refs)
    final=staged_product_cycle(tmp_path,model)
    # Native persistence keeps the original product affiliation; it does not
    # invent the separate product that historical STEP export used to create.
    assert len(final.parts)==1 and len(final.edges)==2 and not final.members
    assert all(r.id!=added for refs in affiliations(final).values() for r in refs)
    assert final.vertices[final.edges[added].start].position==pytest.approx((10,0,0),abs=1e-12)
    assert final.vertices[final.edges[added].end].position==pytest.approx((12,0,0),abs=1e-12)


def test_repeated_coincident_product_import_and_native_persistence(tmp_path):
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDataStd import TDataStd_Name
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf,gp_Vec,gp_Pnt
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from anyfileio_occt._xde import write_document
    doc=TDocStd_Document(TCollection_ExtendedString('BinXCAF'));XCAFDoc_DocumentTool.SetLengthUnit_s(doc,1.)
    tool=XCAFDoc_DocumentTool.ShapeTool_s(doc.Main());root=tool.NewShape()
    TDataStd_Name.Set_s(root,TCollection_ExtendedString('Assembly'))
    definition=tool.AddShape(BRepBuilderAPI_MakeEdge(gp_Pnt(0,0,0),gp_Pnt(2,0,0)).Edge(),False)
    TDataStd_Name.Set_s(definition,TCollection_ExtendedString('Reference line'))
    for x in (0.,0.,5.):
        transform=gp_Trsf();transform.SetTranslation(gp_Vec(x,0,0));tool.AddComponent(root,definition,TopLoc_Location(transform))
    tool.UpdateAssemblies();first=tmp_path/'instances.step';write_document(doc,first)
    model=read_geometry(first).geometry;before=to_dict(model)
    assert len(model.parts)==3 and len(model.edges)==3 and len(model.vertices)==6 and not model.members
    groups=affiliations(model);assert len({refs[0] for refs in groups.values()})==3
    final=staged_product_cycle(tmp_path,model)
    groups=affiliations(final)
    assert len(final.parts)==3 and len(final.edges)==3 and len(final.vertices)==6 and not final.members
    assert sorted(final.vertices[final.edges[refs[0].id].start].position[0] for refs in groups.values())==[0,0,5]
    assert all(final.vertices[final.edges[refs[0].id].end].position[0]-final.vertices[final.edges[refs[0].id].start].position[0]==pytest.approx(2,abs=1e-12) for refs in groups.values())
    assert to_dict(model)==before


@pytest.mark.parametrize('edit',['missing_group','changed_group','split','member','foreign_model','copied_part'])
def test_invalid_affiliation_is_atomic(tmp_path,edit):
    first=tmp_path/'first.step';make_products(first);model=read_geometry(first).geometry
    part=next(iter(model.parts.values()));group=part.metadata[KEY]['group']
    if edit=='missing_group':model.remove_group(group)
    elif edit=='changed_group':
        v=model.add_point(9,9,9);model.add_to_group(group,[model.entity_ref('vertex',v)])
    elif edit=='split':model.split_edge(1)
    elif edit=='member':model.add_member([1],part_id=part.id)
    elif edit=='copied_part':model.add_part(name='Copied',metadata=part.metadata)
    else:
        copied=line();copied.add_part(name='Copied',metadata=part.metadata);model=copied
    before=to_dict(model);path=tmp_path/'preserve.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.reference_geometry.invalid'):
        write_geometry(path,model)
    assert path.read_bytes()==b'old' and to_dict(model)==before


@pytest.mark.parametrize('failure',['cancel','late'])
def test_reference_product_failure_preserves_source_and_destination(tmp_path,monkeypatch,failure):
    first=tmp_path/'first.step';make_products(first);model=read_geometry(first).geometry;before=to_dict(model)
    from anyfileio_occt import _native
    actual=_native.write_shape;state={'written':False};stop=RuntimeError('after native write')
    def write(*args,**kwargs):
        result=actual(*args,**kwargs);state['written']=True
        if failure=='late':raise stop
        return result
    monkeypatch.setattr(_native,'write_shape',write)
    path=tmp_path/'preserve.brep';path.write_bytes(b'old')
    with pytest.raises(CadOperationCancelled if failure=='cancel' else RuntimeError) as error:
        write_geometry(path,model,cancellation=lambda:state['written'])
    if failure=='late':assert error.value is stop
    assert state['written'] and path.read_bytes()==b'old' and to_dict(model)==before


@pytest.mark.parametrize('field,value',[('version',True),('version',2),('part_id',True),('source_occurrence_id',True),('source_document_id','invalid'),('members',(('edge',True),))])
def test_malformed_provenance_is_typed_and_atomic(tmp_path,field,value):
    from anyfileio_occt._reference_geometry import capture
    model=line();reference=model.entity_ref('edge',1)
    metadata=capture(model,[reference],part_id=1,document_id='cad-import-v1:'+'0'*64,occurrence_id=1,prototype_id=1)
    metadata[KEY][field]=value;model.add_part(metadata=metadata)
    before=to_dict(model);path=tmp_path/'preserve.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.reference_geometry.invalid'):
        write_geometry(path,model)
    assert path.read_bytes()==b'old' and to_dict(model)==before


def test_import_part_allocator_invariant_is_checked(tmp_path,monkeypatch):
    first=tmp_path/'first.step';make_products(first);before=first.read_bytes()
    actual=GeometryModel.add_part
    def unexpected(*args,**kwargs):return actual(*args,**kwargs)+1
    monkeypatch.setattr(GeometryModel,'add_part',unexpected)
    with pytest.raises(GeometryInterchangeError,match='geometry.reference_geometry.invalid'):
        read_geometry(first)
    assert first.read_bytes()==before


def mixed_wire_shape():
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace,BRepBuilderAPI_MakeEdge,BRepBuilderAPI_MakeWire
    from OCP.gp import gp_Pnt
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound,TopoDS
    from OCP.TopExp import TopExp
    from anyfileio_occt import _native as native
    polygon=BRepBuilderAPI_MakePolygon()
    for p in ((0,0,0),(1,0,0),(1,1,0),(0,1,0)):polygon.Add(gp_Pnt(*p))
    polygon.Close();face=BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    edges=native.shape_map(face,'edge');edge=TopoDS.Edge_s(edges.FindKey(1))
    extra=BRepBuilderAPI_MakeEdge(TopExp.LastVertex_s(edge,True),BRepBuilderAPI_MakePolygon(gp_Pnt(2,0,0),gp_Pnt(3,0,0)).FirstVertex()).Edge()
    wire=BRepBuilderAPI_MakeWire(edge,extra).Wire()
    builder=BRep_Builder();shape=TopoDS_Compound();builder.MakeCompound(shape);builder.Add(shape,face);builder.Add(shape,wire)
    return shape


def test_actual_step_mixed_wire_never_silently_orphans_material(tmp_path):
    from anyfileio_occt._xde import write_groups
    path=tmp_path/'mixed-wire.step';write_groups([('Mixed wire',mixed_wire_shape())],path);payload=path.read_bytes()
    # STEP may normalize this native carrier. If it survives, the new typed
    # refusal is required; otherwise every actual-file edge must be affiliated.
    try:model=read_geometry(path).geometry
    except GeometryInterchangeError as error:
        assert error.code=='geometry.reference_geometry.mixed_wire_unsupported'
    else:
        carried={oe.edge for face in model.faces.values() for loop in (face.loop,)+face.holes for oe in loop}
        carried.update(model.member_edge_uses[u].edge_id for member in model.members.values() for u in member.edge_use_ids)
        carried.update(r.id for refs in affiliations(model).values() for r in refs if r.kind=='edge')
        assert carried==set(model.edges)
    assert path.read_bytes()==payload


def test_native_scene_mixed_wire_refuses_before_owner_conversion(tmp_path,monkeypatch):
    from anyfileio_occt import _native as native
    from anyfileio_occt import geometry_import as importer
    from anyfileio.geometry import GeometryReadOptions
    path=tmp_path/'native.brep';native.write_shape(mixed_wire_shape(),path,'brep','m');payload=path.read_bytes()
    raw,_=native.read_shape(path,'brep','m',raw_coordinates=True)
    # Reuse a real live scene/session, inject the preserved native BREP leaf at
    # the provider boundary. No claim that STEP's writer retains this carrier.
    first=tmp_path/'scene.step';make_products(first)
    with read_cad(first,options=CadReadOptions(mode='live',retain_source=False)) as doc:
        state=doc._backend_state_for('occt');oid,_,refs=state.instances[0]
        state.instances=((oid,raw,refs),)
        def unexpected(*args,**kwargs):raise AssertionError('Owner conversion must not run')
        monkeypatch.setattr(importer,'_import_shape',unexpected)
        with pytest.raises(GeometryInterchangeError,match='geometry.reference_geometry.mixed_wire_unsupported'):
            importer.import_geometry(doc,options=GeometryReadOptions())
        assert not doc.closed
    assert path.read_bytes()==payload


def test_multiple_mixed_product_import_and_native_persistence(tmp_path):
    from OCP.gp import gp_Trsf,gp_Vec
    from OCP.TopLoc import TopLoc_Location
    from anyfileio_occt._xde import write_groups
    shape=make_products(tmp_path/'fixture.step',mixed=True)
    move=gp_Trsf();move.SetTranslation(gp_Vec(10,0,0))
    first=tmp_path/'parts.step';write_groups([('Alpha',shape),('Beta',shape.Moved(TopLoc_Location(move)))],first)
    model=read_geometry(first).geometry;before=to_dict(model)
    final=staged_product_cycle(tmp_path,model)
    assert len(final.parts)==2 and len(final.sheets)==2 and not final.members
    groups=affiliations(final)
    assert set(p.name for p in final.parts.values())=={'Alpha','Beta'}
    for part in final.parts.values():
        offset=0 if part.name=='Alpha' else 10
        assert len(part.sheet_ids)==len(groups[part.id])==1
        edge=final.edges[groups[part.id][0].id]
        assert final.vertices[edge.start].position==pytest.approx((offset,0,0),abs=1e-12)
        assert final.vertices[edge.end].position==pytest.approx((offset+2,0,0),abs=1e-12)
        sheet=final.sheets[part.sheet_ids[0]]
        face_ids=[final.face_uses[u].face_id for u in sheet.face_use_ids]
        face_edges={use.edge for i in face_ids for use in final.faces[i].loop}
        points=[final.vertices[v].position for i in face_edges for v in (final.edges[i].start,final.edges[i].end)]
        assert min(p[0] for p in points)==pytest.approx(offset,abs=1e-12)
        assert max(p[0] for p in points)==pytest.approx(offset+1,abs=1e-12)
        assert min(p[1] for p in points)==pytest.approx(2,abs=1e-12)
        assert max(p[1] for p in points)==pytest.approx(3,abs=1e-12)
    assert to_dict(model)==before


def test_shared_face_corner_reference_preserves_identity_or_refuses_atomically(tmp_path):
    from test_native_geometry import square
    from anyfileio_occt._reference_geometry import capture
    model=square();end=model.add_point(-1,0,0);edge=model.add_line(1,end)
    metadata=capture(model,[model.entity_ref('edge',edge)],part_id=1,
        document_id='cad-import-v1:'+'0'*64,occurrence_id=1,prototype_id=1)
    part=model.add_part(name='Shared corner',metadata=metadata);model.add_sheet([1],part_id=part)
    before=to_dict(model);path=tmp_path/'preserve.brep';path.write_bytes(b'old')
    try:report=write_geometry(path,model)
    except GeometryInterchangeError as error:
        assert error.code=='geometry.topology.changed'
        assert path.read_bytes()==b'old'
        print('shared-corner: typed topology limit',flush=True)
    else:
        imported=read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m'));final=imported.geometry
        assert len(final.vertices)==5
        # BREP preserves material incidence; it does not recover STEP product affiliations.
        face_edges={use.edge for face in final.faces.values() for loop in (face.loop,)+face.holes for use in loop}
        references=[edge for edge in final.edges.values() if edge.id not in face_edges]
        assert len(references)==1
        reference=references[0]
        face_vertices={v for i in face_edges for v in (final.edges[i].start,final.edges[i].end)}
        refs=report.geometry_to_cad[model.handle('edge',edge)]
        assert refs and all(any(h.kind=='edge' and h.id==reference.id for h in imported.report.cad_to_geometry[ref]) for ref in refs)
        assert reference.start in face_vertices
        assert final.vertices[reference.start].position==pytest.approx((0,0,0),abs=1e-12)
        print('shared-corner: actual topology preserved',flush=True)
    assert to_dict(model)==before
    assert to_dict(staged_product_cycle(tmp_path,model))==before


def free_wire_fixture(kind):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex,BRepBuilderAPI_MakeEdge
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Wire
    from OCP.gp import gp_Pnt
    points=[BRepBuilderAPI_MakeVertex(gp_Pnt(*p)).Vertex() for p in ((0,0,0),(1,0,0),(2,0,0),(0,1,0))]
    pairs={'chain':[(0,1),(1,2)],'disconnected':[(0,1),(2,3)],'branched':[(0,1),(1,2),(1,3)],'repeated':[(0,1),(0,1)]}[kind]
    builder=BRep_Builder();wire=TopoDS_Wire();builder.MakeWire(wire);first=None
    for pair in pairs:
        edge=first if kind=='repeated' and first is not None else BRepBuilderAPI_MakeEdge(points[pair[0]],points[pair[1]]).Edge()
        builder.Add(wire,edge);first=edge
    return wire


def native_scene(document):
    """Use a real BREP's flat manifest/session as one explicit native leaf."""
    from anyfileio_occt.backend import document_shape
    from anyfileio_occt import _native as native
    from anyfileio.cad import CadEntityRef
    shape=document_shape(document)
    refs={kind:{i:CadEntityRef(document.manifest.document_id,kind,i) for i in range(1,native.shape_map(shape,kind).Extent()+1)} for kind in ('vertex','edge','wire','face','shell','solid')}
    document._backend_state_for('occt').instances=((1,shape,refs),)


@pytest.mark.parametrize('kind',['branched','disconnected','repeated'])
def test_incomplete_free_wire_refuses_before_owner_conversion(tmp_path,monkeypatch,kind):
    from anyfileio_occt import _native as native,geometry_import as importer
    from anyfileio.geometry import GeometryReadOptions
    path=tmp_path/'native.brep';native.write_shape(free_wire_fixture(kind),path,'brep','m');payload=path.read_bytes()
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as doc:
        native_scene(doc)
        def unexpected(*args,**kwargs):raise AssertionError('Owner conversion must not run')
        monkeypatch.setattr(importer,'_import_shape',unexpected)
        with pytest.raises(GeometryInterchangeError,match='geometry.reference_geometry.wire_unsupported'):
            importer.import_geometry(doc,options=GeometryReadOptions())
        assert not doc.closed
    assert path.read_bytes()==payload


def test_complete_native_free_wire_keeps_ordered_member_and_material(tmp_path):
    from anyfileio_occt import _native as native,geometry_import as importer
    from anyfileio.geometry import GeometryReadOptions
    path=tmp_path/'native.brep';native.write_shape(free_wire_fixture('chain'),path,'brep','m');payload=path.read_bytes()
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as doc:
        native_scene(doc);model=importer.import_geometry(doc,options=GeometryReadOptions()).geometry
    assert len(model.parts)==len(model.members)==1 and not affiliations(model)
    member=next(iter(model.members.values()));assert len(member.edge_use_ids)==2
    uses=[model.member_edge_uses[i] for i in member.edge_use_ids]
    assert {u.edge_id for u in uses}==set(model.edges)
    def endpoints(use):
        edge=model.edges[use.edge_id];pair=(edge.start,edge.end)
        return pair if int(use.orientation)==1 else pair[::-1]
    first,last=[endpoints(u) for u in uses]
    assert first[1]==last[0]
    assert model.vertices[first[0]].position==pytest.approx((0,0,0),abs=1e-12)
    assert model.vertices[last[1]].position==pytest.approx((2,0,0),abs=1e-12)
    before=to_dict(model);output=tmp_path/'member.brep';output.write_bytes(b'old')
    report=write_geometry(output,model)
    from test_member_station_export import native_chains
    with read_cad(output,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as doc:
        assert native_chains(doc)==[[0,1,2]]
        refs=report.geometry_to_cad[model.handle('member',member.id)]
        assert len(refs)==1 and refs[0] in {r.cad_ref for r in doc.manifest.shapes}
        native_scene(doc);cycled=importer.import_geometry(doc,options=GeometryReadOptions()).geometry
    assert len(cycled.members)==1 and len(cycled.parts)==1
    cycled_member=next(iter(cycled.members.values()))
    ordered=[]
    for use_id in cycled_member.edge_use_ids:
        use=cycled.member_edge_uses[use_id];edge=cycled.edges[use.edge_id]
        a,b=(edge.start,edge.end) if int(use.orientation)==1 else (edge.end,edge.start)
        if ordered:assert ordered[-1]==a
        else:ordered.append(a)
        ordered.append(b)
    assert [cycled.vertices[i].position[0] for i in ordered]==[0,1,2]
    counts=inspected_brep(output).topology_counts
    assert counts['wire']==1 and counts['edge']==2 and counts['vertex']==3
    assert to_dict(model)==before and path.read_bytes()==payload


def inspected_brep(path):
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as doc:return doc.manifest


def staged_product_cycle(tmp_path,model):
    """Native payload identity survives; STEP CAD re-export remains unavailable."""
    from test_native_geometry import assert_staged_refusal
    assert_staged_refusal(tmp_path/'unproved.step',model)
    path=tmp_path/'products.anygeometry.json';before=to_dict(model)
    write_geometry(path,model);restored=read_geometry(path).geometry
    assert to_dict(restored)==before
    return restored
