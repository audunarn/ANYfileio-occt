"""Reports address actual serialized canonical CAD records, not native ranks."""
import pytest
pytest.importorskip('OCP')
from anyfileio import read_cad
from anyfileio.cad import CadReadOptions
from anyfileio.geometry import write_geometry,read_geometry,GeometryWriteOptions,GeometryReadOptions
from anygeometry.serialization import to_dict
from test_native_geometry import square
from anyfileio.geometry import GeometryInterchangeError


def assert_actual(path,report,*,editable=True):
    override=report.output_unit if report.format=='brep' else None
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override=override)) as doc:
        manifest=doc.manifest
        universe={r.cad_ref for r in manifest.shapes+manifest.occurrences+manifest.prototypes}
        assert report.output_document_id==manifest.document_id
        assert report.output_sha256==manifest.source_sha256
        for values in report.geometry_to_cad.values():
            assert values and set(values)<=universe
            assert all(r.document_id==report.output_document_id for r in values)
    if editable:
        result=read_geometry(path,options=GeometryReadOptions(source_length_unit_override=override))
        for handle,values in report.geometry_to_cad.items():
            if handle.kind in ('vertex','edge','face'):
                assert set(values)<=result.report.cad_to_geometry.keys()
    return manifest


@pytest.mark.parametrize('fmt,unit',[('step','m'),('step','mm'),('iges','cm'),('brep','cm')])
def test_actual_material_references_and_rename(tmp_path,fmt,unit):
    model=square();model.add_point(5,6,7);before=to_dict(model)
    if fmt!='brep':
        with pytest.raises(GeometryInterchangeError,match='geometry.association_unproved'):
            write_geometry(tmp_path/('unproved.'+fmt),model,options=GeometryWriteOptions(output_length_unit=unit))
        assert to_dict(model)==before
        return
    path=tmp_path/('panel.'+fmt);report=write_geometry(path,model,options=GeometryWriteOptions(output_length_unit=unit))
    assert set(report.geometry_to_cad)=={model.handle(kind,i) for kind,entities in (('vertex',model.vertices),('edge',model.edges),('face',model.faces)) for i in entities}
    assert_actual(path,report)
    renamed=tmp_path/('renamed.'+fmt);renamed.write_bytes(path.read_bytes());assert_actual(renamed,report)
    assert to_dict(model)==before


@pytest.mark.parametrize('fmt',['step','brep'])
def test_actual_sheet_and_part_carriers(tmp_path,fmt):
    model=square();part=model.add_part(name='Panel');sheet=model.add_sheet([1],part_id=part)
    if fmt!='brep':
        with pytest.raises(GeometryInterchangeError,match='geometry.association_unproved'):write_geometry(tmp_path/'unproved.step',model)
        return
    path=tmp_path/('parts.'+fmt);report=write_geometry(path,model)
    assert_actual(path,report)
    assert all(r.kind=='shell' for r in report.geometry_to_cad[model.handle('sheet',sheet)])
    refs=report.geometry_to_cad[model.handle('part',part)]
    if fmt=='step':assert len(refs)==1 and refs[0].kind=='occurrence'
    else:
        assert all(r.kind=='shell' for r in refs)
        assert any(d.code=='geometry.cad.part_carrier_closure' for d in report.diagnostics)
        assert any('compound identity' in loss for loss in report.metadata_losses)


def test_identically_named_coincident_parts_use_product_witness(tmp_path):
    from anygeometry import GeometryModel
    model=GeometryModel()
    for offset in (0,0,5):
        panel=square()
        if offset:
            import numpy as np
            transform=np.eye(4);transform[0,3]=offset
            inserted=model.insert_model(panel,matrix=transform)
        else:inserted=model.insert_model(panel)
        part=model.add_part(name='Same');model.add_sheet([inserted.handle_map[panel.handle('face',1)].id],part_id=part)
    path=tmp_path/'coincident.step'
    with pytest.raises(GeometryInterchangeError,match='geometry.association_unproved'):
        write_geometry(path,model,options=GeometryWriteOptions(max_topology_work=5000000))


def test_member_and_approximate_trim_actual_refs(tmp_path):
    from test_native_geometry import _noniso_trim_model
    model=square();part=model.add_part(name='Plate');model.add_sheet([1],part_id=part)
    a=model.add_point(3,0,0);b=model.add_point(4,0,0);edge=model.add_line(a,b);member=model.add_member([edge],part_id=part)
    path=tmp_path/'member.brep';report=write_geometry(path,model);assert_actual(path,report)
    assert report.geometry_to_cad[model.handle('member',member)][0].kind=='wire'
    model=_noniso_trim_model();path=tmp_path/'trim.brep'
    report=write_geometry(path,model,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.1))
    assert report.approximations;assert_actual(path,report,editable=False)


@pytest.mark.parametrize('mode',['missing','bytes','cancel','callback','revision'])
def test_actual_document_failures_are_atomic_and_close(tmp_path,monkeypatch,mode):
    import anyfileio
    from dataclasses import replace
    from anyfileio.cad import CadOperationCancelled
    actual=anyfileio.read_cad;documents=[];state={'active':False};model=square();before=to_dict(model)
    stop=GeometryInterchangeError('callback sentinel',code='geometry.topology.changed')
    class View:
        def __init__(self,doc):self.doc=doc
        def close(self):return self.doc.close()
        def __enter__(self):return self
        def __exit__(self,*args):return self.doc.__exit__(*args)
        def _backend_state_for(self,*args):return self.doc._backend_state_for(*args)
        @property
        def manifest(self):return replace(self.doc.manifest,shapes=tuple(r for r in self.doc.manifest.shapes if r.cad_ref.kind!='edge'))
    def read(path,**kwargs):
        doc=actual(path,**kwargs);documents.append(doc);state['active']=True
        if mode=='bytes':path.write_bytes(b'changed')
        if mode=='revision':model.add_point(20,20,20)
        return View(doc) if mode=='missing' else doc
    monkeypatch.setattr(anyfileio,'read_cad',read)
    def cancelled():
        if state['active'] and mode=='callback':raise stop
        return state['active'] and mode=='cancel'
    path=tmp_path/'preserve.brep';path.write_bytes(b'old')
    with pytest.raises(CadOperationCancelled if mode=='cancel' else GeometryInterchangeError) as error:
        write_geometry(path,model,cancellation=cancelled)
    if mode=='callback':assert error.value is stop
    assert documents and all(doc.closed for doc in documents)
    assert path.read_bytes()==b'old'
    if mode!='revision':assert to_dict(model)==before


def test_one_topology_ledger_and_late_budget_refusal(tmp_path,monkeypatch):
    from anyfileio_occt import _topology,_output_references
    actual=_topology.Work;works=[];entered=[];original=_output_references.reconcile
    class Tracked(actual):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);works.append(self)
    def reconcile(*args,**kwargs):
        work=args[9];entered.append((work,work.used));return original(*args,**kwargs)
    monkeypatch.setattr(_topology,'Work',Tracked);monkeypatch.setattr(_output_references,'reconcile',reconcile)
    report=write_geometry(tmp_path/'first.brep',square())
    assert len(works)==1 and entered[0][0] is works[0] and 0<entered[0][1]<works[0].used
    # Choose an allowance from the measured first-stage work of the SAME input;
    # do not alter defaults or any scientific limit to make an export pass.
    allowance=entered[0][1]+1;works.clear();entered.clear();path=tmp_path/'budget.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.topology.budget'):
        write_geometry(path,square(),options=GeometryWriteOptions(max_topology_work=allowance))
    assert len(works)==1 and entered and path.read_bytes()==b'old'


def test_closed_source_split_and_bounded_free_curve_refs(tmp_path):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Circ,gp_Ax2,gp_Pnt,gp_Dir
    from anyfileio_occt import _native
    from anygeometry import GeometryModel
    from anygeometry.support_curves import PlaneNurbsCurve
    from test_plane_nurbs_trims import section_model
    import numpy as np
    path=tmp_path/'circle.brep'
    _native.write_shape(BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(0,0,0),gp_Dir(0,0,1)),1)).Edge(),path,'brep','m')
    model=read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m')).geometry
    assert len(model.edges)==4
    output=tmp_path/'split.brep';report=write_geometry(output,model);assert_actual(output,report)
    curve=next(e.curve for e in section_model().edges.values() if isinstance(e.curve,PlaneNurbsCurve)).subcurve(.1,.2)
    model=GeometryModel();a,b=model.add_points(curve.evaluate(np.array([0.,1.])));edge=model.add_curve(a,b,curve)
    output=tmp_path/'free.brep';report=write_geometry(output,model,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.02,max_segments=20000))
    assert len(report.geometry_to_cad[model.handle('edge',edge)])>1
    assert_actual(output,report)


def test_missing_core_capability_refuses_atomically(tmp_path,monkeypatch):
    from anyfileio.geometry import GeometryWriteReport
    fields=dict(GeometryWriteReport.__dataclass_fields__);fields.pop('output_document_id')
    monkeypatch.setattr(GeometryWriteReport,'__dataclass_fields__',fields)
    path=tmp_path/'old.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.core.capability_missing'):
        write_geometry(path,square())
    assert path.read_bytes()==b'old'


@pytest.mark.parametrize('mode',['cancelling_chain','ambiguous'])
def test_wrapper_fallback_refuses_nonliteral_or_ambiguous_candidates(tmp_path,monkeypatch,mode):
    import anyfileio
    from dataclasses import replace
    from OCP.TopLoc import TopLoc_Location,TopLoc_Datum3D
    from OCP.gp import gp_Trsf
    from anyfileio_occt import _native
    from test_literal_locations import _rounded_identity_chain
    actual=anyfileio.read_cad;documents=[]
    def read(path,**kwargs):
        doc=actual(path,**kwargs);documents.append(doc);state=doc._backend_state_for('occt')
        # Manufacture only canonical table wrappers, not actual file geometry.
        # The graph proof continues to consume the unchanged actual doc shape.
        from anyfileio_occt.backend import document_shape
        shape=document_shape(doc)
        location=_rounded_identity_chain()[0] if mode=='cancelling_chain' else TopLoc_Location(TopLoc_Datum3D(gp_Trsf()))
        wrapped=shape.Moved(location)
        tables={kind:{i:r.cad_ref for i,r in enumerate([r for r in doc.manifest.shapes if r.cad_ref.kind==kind],1)} for kind in ('vertex','edge','face','wire','shell','solid')}
        state.instances=((1,wrapped,tables),)
        if mode=='ambiguous':
            from anyfileio.cad import CadEntityRef
            edge_ref=tables['edge'][1];alternate=CadEntityRef(doc.manifest.document_id,'edge',100)
            record=next(r for r in doc.manifest.shapes if r.cad_ref==edge_ref)
            doc._manifest=replace(doc.manifest,shapes=doc.manifest.shapes+(replace(record,cad_ref=alternate),))
            other={k:dict(v) for k,v in tables.items()};other['edge'][1]=alternate
            state.instances+=((1,wrapped,other),)
        return doc
    monkeypatch.setattr(anyfileio,'read_cad',read)
    path=tmp_path/'old.brep';path.write_bytes(b'old')
    code='geometry.association.state_invalid'
    with pytest.raises(GeometryInterchangeError,match=code):write_geometry(path,square())
    assert path.read_bytes()==b'old' and documents and all(d.closed for d in documents)


@pytest.mark.parametrize('kind',['hole','shared'])
def test_material_reference_endpoints_with_holes_or_shared_edge(tmp_path,kind):
    from anygeometry import GeometryModel
    from anyfileio_occt import _native
    if kind=='hole':
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
        from OCP.gp import gp_Pnt
        def wire(points):
            polygon=BRepBuilderAPI_MakePolygon()
            for x,y in points:polygon.Add(gp_Pnt(x,y,0))
            polygon.Close();return polygon.Wire()
        face=BRepBuilderAPI_MakeFace(wire([(0,0),(4,0),(4,4),(0,4)]),True)
        face.Add(wire([(1,1),(1,2),(2,2),(2,1)]))
        path=tmp_path/'input.brep';_native.write_shape(face.Face(),path,'brep','m')
        model=read_geometry(path,options=GeometryReadOptions(source_length_unit_override='m')).geometry
        assert len(model.faces[1].holes)==1
    else:
        model=GeometryModel();a,b,c,d,e,f=model.add_points([(0,0,0),(1,0,0),(1,1,0),(0,1,0),(2,0,0),(2,1,0)])
        ab=model.add_line(a,b);bc=model.add_line(b,c);cd=model.add_line(c,d);da=model.add_line(d,a)
        be=model.add_line(b,e);ef=model.add_line(e,f);fc=model.add_line(f,c)
        model.add_face([ab,bc,cd,da]);model.add_face([be,ef,fc,bc])
    output=tmp_path/'mapped.brep';report=write_geometry(output,model);assert_actual(output,report)
    imported=read_geometry(output,options=GeometryReadOptions(source_length_unit_override='m'))
    for edge in model.edges.values():
        ref,=report.geometry_to_cad[model.handle('edge',edge.id)]
        handle,=imported.report.cad_to_geometry[ref];actual=imported.geometry.edges[handle.id]
        expected=sorted(tuple(model.vertices[i].position) for i in (edge.start,edge.end))
        points=sorted(tuple(imported.geometry.vertices[i].position) for i in (actual.start,actual.end))
        import numpy as np
        assert np.asarray(points)==pytest.approx(np.asarray(expected),abs=1e-12)
        assert len(imported.geometry.faces_using_edge(actual.id))==len(model.faces_using_edge(edge.id))


@pytest.mark.parametrize('mode',['callback','cancel'])
def test_callback_during_actual_document_witness_keeps_identity(tmp_path,monkeypatch,mode):
    import anyfileio
    from anyfileio.cad import CadOperationCancelled
    from anyfileio_occt import _topology
    state={'canonical':False,'witness':False};documents=[]
    read=anyfileio.read_cad;witness=_topology.witness
    def reading(*args,**kwargs):
        doc=read(*args,**kwargs);documents.append(doc);state['canonical']=True;return doc
    def proving(*args,**kwargs):
        if state['canonical']:state['witness']=True
        return witness(*args,**kwargs)
    monkeypatch.setattr(anyfileio,'read_cad',reading);monkeypatch.setattr(_topology,'witness',proving)
    stop=GeometryInterchangeError('inside witness callback',code='geometry.topology.changed')
    def cancelled():
        if state['witness'] and mode=='callback':raise stop
        return state['witness'] and mode=='cancel'
    model=square();before=to_dict(model);path=tmp_path/'preserve.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError if mode=='callback' else CadOperationCancelled) as error:
        write_geometry(path,model,cancellation=cancelled)
    if mode=='callback':assert error.value is stop
    assert state['witness'] and documents and all(doc.closed for doc in documents)
    assert path.read_bytes()==b'old' and to_dict(model)==before


def test_coordinate_equal_replacement_vertex_cannot_disappear_from_report(tmp_path,monkeypatch):
    from anygeometry import GeometryModel
    from anyfileio_occt import geometry_export as exporter
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Pnt
    model=GeometryModel();a=model.add_point(0,0,0);b=model.add_point(1,0,0);model.add_line(a,b)
    before=to_dict(model);path=tmp_path/'preserve.brep';path.write_bytes(b'old')
    def substituted(*args,**kwargs):
        return [BRepBuilderAPI_MakeEdge(gp_Pnt(0,0,0),gp_Pnt(1,0,0)).Edge()],None
    monkeypatch.setattr(exporter,'curve_edge',substituted)
    with pytest.raises(GeometryInterchangeError,match='geometry.output.references_missing'):
        write_geometry(path,model)
    assert path.read_bytes()==b'old' and to_dict(model)==before
