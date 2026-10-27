"""File-record lineage discriminates topology automorphisms without samples."""
import pytest
pytest.importorskip('OCP')
from anygeometry import GeometryModel
from anygeometry.serialization import to_dict
from anyfileio import read_cad
from anyfileio.cad import CadReadOptions
from anyfileio.geometry import write_geometry,read_geometry,GeometryWriteOptions,GeometryReadOptions,GeometryInterchangeError


def curves(line=False):
    model=GeometryModel();a=model.add_point(-1,0,0);b=model.add_point(1,0,0)
    u=model.add_point(0,1,0);d=model.add_point(0,-1,0)
    first=model.add_line(a,b) if line else model.add_arc(a,u,b)
    second=model.add_arc(a,d,b)
    return model,first,second


@pytest.mark.parametrize('line',[False,True])
@pytest.mark.parametrize('unit',['m','mm','cm'])
@pytest.mark.parametrize('source_unit',['m','mm'])
def test_reordered_compound_preserves_curve_record_identity(tmp_path,monkeypatch,line,unit,source_unit):
    from anyfileio_occt import _native
    from OCP.TopoDS import TopoDS_Compound,TopoDS_Iterator,TopoDS
    from OCP.BRep import BRep_Builder
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line,GeomAbs_Circle
    from anyfileio_occt.backend import document_shape
    original=_native.write_shape
    def reorder(shape,path,fmt,unit='m',cancellation=None):
        iterator=TopoDS_Iterator(shape,False,True);children=[]
        while iterator.More():children.append(iterator.Value());iterator.Next()
        changed=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(changed)
        for child in reversed(children):builder.Add(changed,child)
        return original(changed,path,fmt,unit,cancellation)
    monkeypatch.setattr(_native,'write_shape',reorder)
    model,upper,lower=curves(line);model.set_document_settings(units=source_unit);before=to_dict(model);path=tmp_path/'reordered.brep'
    report=write_geometry(path,model,options=GeometryWriteOptions(output_length_unit=unit))
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override=unit)) as doc:
        assert report.output_document_id==doc.manifest.document_id
        edges=_native.shape_map(document_shape(doc),'edge')
        for identifier,sign in ((upper,0 if line else 1),(lower,-1)):
            reference,=report.geometry_to_cad[model.handle('edge',identifier)]
            curve=BRepAdaptor_Curve(TopoDS.Edge_s(edges.FindKey(reference.local_id)))
            assert curve.GetType()==(GeomAbs_Line if sign==0 else GeomAbs_Circle)
            midpoint=curve.Value((curve.FirstParameter()+curve.LastParameter())/2)
            assert midpoint.Y()==pytest.approx(sign*(1 if source_unit=='m' else .001),abs=1e-12)
    assert to_dict(model)==before


def test_source_geometry_mutation_cannot_validate_itself(tmp_path,monkeypatch):
    from anyfileio_occt import _native
    from OCP.BRep import BRep_Builder,BRep_Tool
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf,gp_Vec
    original=_native.write_shape
    def changed(shape,path,fmt,unit='m',cancellation=None):
        edge=TopoDS.Edge_s(_native.shape_map(shape,'edge').FindKey(1));location=TopLoc_Location()
        curve=BRep_Tool.Curve_s(edge,location,0.,0.).Copy();t=gp_Trsf();t.SetTranslation(gp_Vec(0,2,0));curve.Transform(t)
        BRep_Builder().UpdateEdge(edge,curve,location,1e-7)
        return original(shape,path,fmt,unit,cancellation)
    monkeypatch.setattr(_native,'write_shape',changed)
    model,_,_=curves();before=to_dict(model);path=tmp_path/'old.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.association.source_changed'):write_geometry(path,model)
    assert path.read_bytes()==b'old' and to_dict(model)==before


@pytest.mark.parametrize('fmt',['step','iges'])
def test_unproved_formats_refuse_editable_export_only(tmp_path,fmt):
    model,_,_=curves();path=tmp_path/('old.'+fmt);path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.association_unproved'):write_geometry(path,model)
    assert path.read_bytes()==b'old'


def test_same_boundary_different_surface_interiors_use_record_provenance(tmp_path,monkeypatch):
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    from anyfileio_occt import _native
    from OCP.TopoDS import TopoDS,TopoDS_Compound,TopoDS_Iterator
    from OCP.BRep import BRep_Builder
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from anyfileio_occt.backend import document_shape
    model=GeometryModel();expected={}
    uv=((0,0),(1,0),(1,1),(0,1))
    for height in (.25,.5):
        net=tuple(tuple((i/2,j/2,height if i==j==1 else 0.) for j in range(3)) for i in range(3))
        surface=NurbsSurface(2,2,(0,0,0,1,1,1),(0,0,0,1,1,1),net)
        vertices=model.add_points(surface.evaluate(*p) for p in uv);edges=[]
        for i in range(4):edges.append(model.add_curve(vertices[i],vertices[(i+1)%4],CurveOnSurface(surface,NurbsCurve(1,(0,0,1,1),(uv[i],uv[(i+1)%4])))))
        face=model.add_face(edges,surface=surface);expected[face]=net
    original=_native.write_shape
    def reorder(shape,path,fmt,unit='m',cancellation=None):
        iterator=TopoDS_Iterator(shape,False,True);children=[]
        while iterator.More():children.append(iterator.Value());iterator.Next()
        changed=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(changed)
        for child in reversed(children):builder.Add(changed,child)
        return original(changed,path,fmt,unit,cancellation)
    monkeypatch.setattr(_native,'write_shape',reorder)
    path=tmp_path/'interiors.brep';report=write_geometry(path,model)
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as doc:
        faces=_native.shape_map(document_shape(doc),'face')
        for identifier,net in expected.items():
            reference,=report.geometry_to_cad[model.handle('face',identifier)]
            actual=BRepAdaptor_Surface(TopoDS.Face_s(faces.FindKey(reference.local_id))).BSpline()
            for i in range(3):
                for j in range(3):
                    point=actual.Pole(i+1,j+1)
                    assert (point.X(),point.Y(),point.Z())==net[i][j]


@pytest.mark.parametrize('kind',['free','fitted'])
def test_certificate_and_report_consume_same_actual_entities(tmp_path,monkeypatch,kind):
    from anyfileio_occt import _association,_geometry,_trim_bounds
    actual=_association.actual_association;observed=[];expected_refs={}
    from anyfileio_occt import _output_references
    reconcile=_output_references.reconcile
    def reference_check(*args,**kwargs):
        association=kwargs['association']
        from anyfileio_occt import _native
        source_map=_native.shape_map(args[1],'edge');raw_map=_native.shape_map(association.topology[0],'edge')
        for handle,shapes in args[6].items():
            values=[]
            for shape in shapes:
                if handle.kind=='edge':
                    source_index=source_map.FindIndex(shape);raw_index,_=association.topology[2][source_index]
                    assert raw_map.FindKey(raw_index).IsSame(association.raw(shape))
                values.append(association.reference(association.canonical(shape)))
            expected_refs[handle]=tuple(values)
        return reconcile(*args,**kwargs)
    monkeypatch.setattr(_output_references,'reconcile',reference_check)
    def build(*args,**kwargs):
        result=actual(*args,**kwargs);observed.append(result);return result
    monkeypatch.setattr(_association,'actual_association',build)
    if kind=='fitted':
        from test_native_geometry import _noniso_trim_model
        model=_noniso_trim_model();function=_trim_bounds.verify_fitted_trims
        def checked(*args,**kwargs):
            assert kwargs['association'] is observed[0] and kwargs['topology'] is observed[0].topology
            return function(*args,**kwargs)
        monkeypatch.setattr(_trim_bounds,'verify_fitted_trims',checked)
        deviation=.1
    else:
        from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
        import numpy as np
        support=NurbsSurface(1,1,(0,0,1,1),(0,0,1,1),(((0,0,0),(0,1,.2)),((1,0,0),(1,1,0))))
        curve=CurveOnSurface(support,NurbsCurve(1,(0,0,1,1),((0,0),(1,1))))
        model=GeometryModel();a,b=model.add_points(curve.evaluate(np.array([0.,1.])));model.add_curve(a,b,curve)
        function=_geometry.verify_serialized_polylines
        def checked(*args,**kwargs):
            assert kwargs['association'] is observed[0];return function(*args,**kwargs)
        monkeypatch.setattr(_geometry,'verify_serialized_polylines',checked);deviation=.1
    path=tmp_path/'bounded.brep';report=write_geometry(path,model,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=deviation,max_topology_work=5000000))
    assert report.approximations and all(r.bound_m<=deviation for r in report.approximations)
    assert len(observed)==1 and observed[0].document.closed
    # Each report ref is exactly the canonical descendant of its pinned raw
    # record; no independent canonical search can substitute another curve.
    for handle,values in expected_refs.items():assert report.geometry_to_cad[handle]==values


@pytest.mark.parametrize('mode',['runtime','domain','cancel'])
def test_export_restores_only_recorded_callback_inside_public_read(tmp_path,monkeypatch,mode):
    import anyfileio
    from anyfileio.cad import CadOperationCancelled
    original=anyfileio.read_cad;state={'read':False}
    stop=RuntimeError('canonical read sentinel') if mode=='runtime' else GeometryInterchangeError('canonical read domain sentinel',code='test.domain')
    def reading(*args,**kwargs):state['read']=True;return original(*args,**kwargs)
    monkeypatch.setattr(anyfileio,'read_cad',reading)
    def cancelled():
        if state['read'] and mode!='cancel':raise stop
        return state['read']
    model,_,_=curves();before=to_dict(model);path=tmp_path/'old.brep';path.write_bytes(b'old')
    with pytest.raises(CadOperationCancelled if mode=='cancel' else type(stop)) as error:
        write_geometry(path,model,cancellation=cancelled)
    if mode!='cancel':assert error.value is stop
    assert state['read'] and path.read_bytes()==b'old' and to_dict(model)==before


@pytest.mark.parametrize('mode',['missing','collision','swap','payload'])
def test_wrong_or_missing_record_and_payload_are_atomic(tmp_path,monkeypatch,mode):
    from anyfileio_occt import _native,_association
    original=_native.write_shape
    def changed(shape,path,fmt,unit='m',cancellation=None):
        result=original(shape,path,fmt,unit,cancellation);capsule=_association.current_writer().capsule
        indices=[i for i in range(1,capsule.snapshot.pool.map.Extent()+1) if int(capsule.snapshot.pool.shape(i).ShapeType())==6]
        if mode=='missing':capsule.records.pop(indices[0])
        elif mode=='collision':capsule.records[indices[1]]=capsule.records[indices[0]]
        elif mode=='swap':capsule.records[indices[0]],capsule.records[indices[1]]=capsule.records[indices[1]],capsule.records[indices[0]]
        else:path.write_bytes(path.read_bytes()+b'\n')
        return result
    monkeypatch.setattr(_native,'write_shape',changed)
    model,_,_=curves();before=to_dict(model);path=tmp_path/'old.brep';path.write_bytes(b'old')
    code={'missing':'record_invalid','collision':'record_invalid','swap':'record_invalid','payload':'payload_changed'}[mode]
    with pytest.raises(GeometryInterchangeError,match='geometry.association.'+code):write_geometry(path,model)
    assert path.read_bytes()==b'old' and to_dict(model)==before


@pytest.mark.parametrize('phase',['raw','canonical'])
def test_live_geometry_tamper_cannot_hide_behind_original_file_hash(tmp_path,monkeypatch,phase):
    import anyfileio
    from anyfileio_occt import _native
    from OCP.BRep import BRep_Builder,BRep_Tool
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf,gp_Vec
    original=anyfileio.read_cad;documents=[]
    def reading(*args,**kwargs):
        doc=original(*args,**kwargs);documents.append(doc);state=doc._backend_state_for('occt')
        root=state.raw_brep if phase=='raw' else state.shape
        edge=TopoDS.Edge_s(_native.shape_map(root,'edge').FindKey(1));location=TopLoc_Location()
        curve=BRep_Tool.Curve_s(edge,location,0.,0.).Copy();transform=gp_Trsf();transform.SetTranslation(gp_Vec(0,3,0));curve.Transform(transform)
        BRep_Builder().UpdateEdge(edge,curve,location,1e-7)
        return doc
    monkeypatch.setattr(anyfileio,'read_cad',reading)
    model,_,_=curves();before=to_dict(model);path=tmp_path/'old.brep';path.write_bytes(b'old')
    code='literal_changed' if phase=='raw' else 'history_invalid'
    with pytest.raises(GeometryInterchangeError,match='geometry.association.'+code):
        write_geometry(path,model,options=GeometryWriteOptions(output_length_unit='cm'))
    assert documents and all(d.closed for d in documents)
    assert path.read_bytes()==b'old' and to_dict(model)==before


def test_duplicate_identical_geometry_retains_distinct_actual_records(tmp_path):
    from anyfileio_occt import _native
    from anyfileio_occt.backend import document_shape
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    model=GeometryModel();edges=[]
    for _ in range(2):
        a=model.add_point(-1,0,0);b=model.add_point(1,0,0);v=model.add_point(0,1,0);edges.append(model.add_arc(a,v,b))
    path=tmp_path/'duplicates.brep';report=write_geometry(path,model)
    refs=[report.geometry_to_cad[model.handle('edge',i)][0] for i in edges];assert len(set(refs))==2
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as doc:
        native_edges=_native.shape_map(document_shape(doc),'edge')
        for ref in refs:
            curve=BRepAdaptor_Curve(TopoDS.Edge_s(native_edges.FindKey(ref.local_id)));p=curve.Value((curve.FirstParameter()+curve.LastParameter())/2)
            assert p.Y()==pytest.approx(1,abs=1e-12)


def test_native_file_is_readable_by_ordinary_breptools(tmp_path):
    from OCP.BRepTools import BRepTools
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Shape,TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from anyfileio_occt import _native
    model,_,_=curves();path=tmp_path/'ordinary.brep';write_geometry(path,model,options=GeometryWriteOptions(output_length_unit='cm'))
    shape=TopoDS_Shape();assert BRepTools.Read_s(shape,str(path),BRep_Builder()) and not shape.IsNull()
    edges=_native.shape_map(shape,'edge');assert edges.Extent()==2
    values=[]
    for i in range(1,3):
        curve=BRepAdaptor_Curve(TopoDS.Edge_s(edges.FindKey(i)));assert curve.Circle().Radius()==100
        values.append(curve.Value((curve.FirstParameter()+curve.LastParameter())/2).Y()*.01)
    assert sorted(values)==pytest.approx([-1,1],abs=1e-12)


def review_patch_model(height=.25):
    from anygeometry.nurbs import NurbsSurface,NurbsCurve,CurveOnSurface
    model=GeometryModel();net=tuple(tuple((i/2,j/2,height if i==j==1 else 0.) for j in range(3)) for i in range(3))
    surface=NurbsSurface(2,2,(0,0,0,1,1,1),(0,0,0,1,1,1),net);uv=((0,0),(1,0),(1,1),(0,1))
    vertices=model.add_points(surface.evaluate(*p) for p in uv);edges=[]
    for i in range(4):edges.append(model.add_curve(vertices[i],vertices[(i+1)%4],CurveOnSurface(surface,NurbsCurve(1,(0,0,1,1),(uv[i],uv[(i+1)%4])))))
    model.add_face(edges,surface=surface);return model


@pytest.mark.parametrize('kind',['curve','surface','pc'])
@pytest.mark.parametrize('size',['1e-9','ulp'])
def test_fine_native_definition_mutations_are_not_hidden_by_stream_precision(tmp_path,monkeypatch,kind,size):
    import io,math,json
    from anyfileio_occt import _native
    from OCP.BRep import BRep_Tool,BRep_Builder
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    from OCP.GeomTools import GeomTools
    from OCP.gp import gp_Pnt,gp_Pnt2d
    model=curves()[0] if kind=='curve' else review_patch_model();before=to_dict(model);original=_native.write_shape;observed={}
    def changed(shape,path,fmt,unit='m',cancellation=None):
        builder=BRep_Builder();location=TopLoc_Location();original_bytes=None
        if kind=='curve':
            edge=TopoDS.Edge_s(_native.shape_map(shape,'edge').FindKey(1));value=BRep_Tool.Curve_s(edge,location,0.,0.);copy=value.Copy();baseline=copy.Radius()
            altered=baseline+1e-9 if size=='1e-9' else math.nextafter(baseline,math.inf);copy.SetRadius(altered)
            update=lambda:builder.UpdateEdge(edge,copy,location,1e-7)
        else:
            face=TopoDS.Face_s(_native.shape_map(shape,'face').FindKey(1))
            if kind=='surface':
                value=BRep_Tool.Surface_s(face,location);stream=io.BytesIO();GeomTools.Write_s(value,stream);original_bytes=stream.getvalue();copy=value;p=copy.Pole(2,2);baseline=p.Z()
                altered=baseline+1e-9 if size=='1e-9' else math.nextafter(baseline,math.inf);copy.SetPole(2,2,gp_Pnt(p.X(),p.Y(),altered))
                update=lambda:None
            else:
                edge=TopoDS.Edge_s(_native.shape_map(face,'edge').FindKey(1));value=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.);copy=value.Copy();i=copy.NbPoles();p=copy.Pole(i)
                use_x=bool(p.X());baseline=p.X() if use_x else p.Y();assert baseline!=0
                altered=baseline+1e-9 if size=='1e-9' else math.nextafter(baseline,math.inf);copy.SetPole(i,gp_Pnt2d(altered if use_x else p.X(),p.Y() if use_x else altered))
                update=lambda:builder.UpdateEdge(edge,copy,face,1e-7)
        left=io.BytesIO();right=io.BytesIO()
        if original_bytes is None:GeomTools.Write_s(value,left)
        else:left.write(original_bytes)
        GeomTools.Write_s(copy,right)
        observed.update(kind=kind,size=size,baseline=baseline,altered=altered,stream_changed=left.getvalue()!=right.getvalue(),before_tail=repr(left.getvalue()[-150:]),after_tail=repr(right.getvalue()[-150:]))
        update();return original(shape,path,fmt,unit,cancellation)
    monkeypatch.setattr(_native,'write_shape',changed);path=tmp_path/'old.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.association.source_changed'):write_geometry(path,model)
    assert observed and observed['altered']!=observed['baseline']
    print('GEOMTOOLS_PRECISION '+json.dumps(observed),flush=True)
    assert path.read_bytes()==b'old' and to_dict(model)==before


@pytest.mark.parametrize('kind',['vertex','face'])
def test_native_tolerance_change_is_part_of_frozen_state(tmp_path,monkeypatch,kind):
    import math
    from anyfileio_occt import _native
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool,BRep_Builder
    model=review_patch_model();original=_native.write_shape
    def changed(shape,*args,**kwargs):
        value=_native.shape_map(shape,kind).FindKey(1);builder=BRep_Builder()
        if kind=='vertex':
            value=TopoDS.Vertex_s(value);builder.UpdateVertex(value,math.nextafter(BRep_Tool.Tolerance_s(value),math.inf))
        else:
            value=TopoDS.Face_s(value);builder.UpdateFace(value,math.nextafter(BRep_Tool.Tolerance_s(value),math.inf))
        return original(shape,*args,**kwargs)
    monkeypatch.setattr(_native,'write_shape',changed);path=tmp_path/'old.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.association.source_changed'):write_geometry(path,model)
    assert path.read_bytes()==b'old'


def test_ordinary_foreign_brep_guard_checkpoints_and_typed_bad_root(tmp_path,monkeypatch):
    from contextlib import contextmanager
    from anyfileio_occt import _native,_association
    from anyfileio.cad import CadOperationError,CadOperationCancelled
    from OCP.BRepTools import BRepTools
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Pnt
    # A separate ordinary OCCT writer, not the association serializer.
    foreign=tmp_path/'foreign.brep';assert BRepTools.Write_s(BRepBuilderAPI_MakeEdge(gp_Pnt(2,3,4),gp_Pnt(5,3,4)).Edge(),str(foreign))
    source=foreign.read_bytes();guard=_native._message_guard;state={'depth':0,'calls':0}
    @contextmanager
    def tracked():
        with guard():
            state['depth']+=1
            try:yield
            finally:state['depth']-=1
    monkeypatch.setattr(_native,'_message_guard',tracked)
    actual=_association.Decoded
    class Checked(actual):
        def __init__(self,*args,**kwargs):assert state['depth']>0;state['calls']+=1;super().__init__(*args,**kwargs)
    monkeypatch.setattr(_association,'Decoded',Checked)
    with read_cad(foreign,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m')) as doc:
        assert doc.manifest.world_bounds_m==pytest.approx((2,3,4,5,3,4),abs=1e-12)
    assert state['depth']==0 and state['calls'] and foreign.read_bytes()==source
    # Native-form table read and root read have cancellation between them.
    own=tmp_path/'own.brep';write_geometry(own,curves()[0]);data=own.read_bytes()
    from OCP import BRepTools as module
    native_table=module.BRepTools_ShapeSet;phase={'read':False}
    class Table:
        def __init__(self,*args):self.table=native_table(*args)
        def __getattr__(self,name):return getattr(self.table,name)
        def Read(self,*args):
            assert state['depth']>0
            result=self.table.Read(*args)
            if len(args)==1:phase['read']=True
            return result
    monkeypatch.setattr(module,'BRepTools_ShapeSet',Table)
    with pytest.raises(CadOperationCancelled):
        read_cad(own,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m'),cancellation=lambda:phase['read'])
    assert state['depth']==0 and phase['read'] and own.read_bytes()==data
    bad=tmp_path/'bad.brep';split=data.rstrip().rfind(b'\n');bad.write_bytes(data[:split+1]+b'+9999999 0 ')
    with pytest.raises(CadOperationError) as error:
        read_cad(bad,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='m'))
    assert error.value.code=='cad.read.failed' and state['depth']==0


def test_brep_part_closures_follow_reordered_distinct_interiors(tmp_path,monkeypatch):
    from anyfileio_occt import _native
    from anyfileio_occt.backend import document_shape
    from OCP.TopoDS import TopoDS,TopoDS_Compound,TopoDS_Iterator
    from OCP.BRep import BRep_Builder
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    model=GeometryModel();expected={}
    for height in (.25,.5):
        patch=review_patch_model(height);inserted=model.insert_model(patch)
        face=inserted.handle_map[patch.handle('face',1)].id;part=model.add_part(name='Same');model.add_sheet([face],part_id=part)
        expected[part]=(face,height)
    original=_native.write_shape
    def reorder(shape,*args,**kwargs):
        it=TopoDS_Iterator(shape,False,True);children=[]
        while it.More():children.append(it.Value());it.Next()
        root=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(root)
        for child in reversed(children):builder.Add(root,child)
        return original(root,*args,**kwargs)
    monkeypatch.setattr(_native,'write_shape',reorder)
    before=to_dict(model);path=tmp_path/'parts.brep';report=write_geometry(path,model,options=GeometryWriteOptions(output_length_unit='cm',max_topology_work=5000000))
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='cm')) as doc:
        shape=document_shape(doc);shells=_native.shape_map(shape,'shell');faces=_native.shape_map(shape,'face');seen=set()
        for part,(face,height) in expected.items():
            shell_ref,=report.geometry_to_cad[model.handle('part',part)];assert shell_ref.kind=='shell';seen.add(shell_ref)
            shell=shells.FindKey(shell_ref.local_id);inside=_native.shape_map(shell,'face');assert inside.Extent()==1
            face_ref,=report.geometry_to_cad[model.handle('face',face)];assert faces.FindIndex(inside.FindKey(1))==face_ref.local_id
            support=BRepAdaptor_Surface(TopoDS.Face_s(inside.FindKey(1))).BSpline()
            assert support.Pole(2,2).Z()==pytest.approx(height,abs=1e-12)
        assert len(seen)==2
    assert to_dict(model)==before
    assert all(any(model.handle('part',part) in d.entities for d in report.diagnostics if d.code=='geometry.cad.part_carrier_closure') for part in expected)


def test_public_native_history_contract_located_repeated_and_reversed_uses():
    # This exercises the public OCCT identity-history contract, not an
    # independently invented geometric correspondence algorithm.
    from anyfileio_occt._association import scale,validate_uses
    from anyfileio_occt._topology import compare,Work
    from fractions import Fraction as Q
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.TopoDS import TopoDS_Compound
    from OCP.BRep import BRep_Builder
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Pnt,gp_Trsf,gp_Vec
    edge=BRepBuilderAPI_MakeEdge(gp_Pnt(0,0,0),gp_Pnt(1,0,0)).Edge();transform=gp_Trsf();transform.SetTranslation(gp_Vec(2,0,0))
    located=edge.Moved(TopLoc_Location(transform));root=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(root)
    for child in (edge,edge,edge.Reversed(),located):builder.Add(root,child)
    transformed=scale(root,1000.);work=Work(1000000)
    validate_uses(root,transformed.shape,transformed.entity,work)
    matches=compare(root,transformed.shape,Q(1),Q(1,1000),work,entity_map=transformed.entity)
    assert len(matches)==2 and len({target for target,reverse in matches.values()})==2
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS
    from anyfileio_occt import _native
    vertices=_native.shape_map(transformed.shape,'vertex')
    assert sorted(BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertices.FindKey(i))).X()/1000 for i in range(1,vertices.Extent()+1))==[0,1,2,3]


@pytest.mark.parametrize('counterpart',['3d','pc'])
def test_actual_fitted_certificate_rejects_wrong_pinned_counterpart_after_association(tmp_path,monkeypatch,counterpart):
    from test_native_geometry import _noniso_trim_model
    from anyfileio_occt import _trim_bounds,_native
    from OCP.BRep import BRep_Tool,BRep_Builder
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf,gp_Vec,gp_Vec2d
    actual=_trim_bounds.verify_fitted_trims;called=[]
    def corrupted(*args,**kwargs):
        association=kwargs['association'];raw=association.topology[0];assert kwargs['topology'] is association.topology
        face=TopoDS.Face_s(_native.shape_map(raw,'face').FindKey(1));edge=TopoDS.Edge_s(_native.shape_map(face,'edge').FindKey(1));builder=BRep_Builder()
        if counterpart=='3d':
            location=TopLoc_Location();curve=BRep_Tool.Curve_s(edge,location,0.,0.).Copy();transform=gp_Trsf();transform.SetTranslation(gp_Vec(0,3,0));curve.Transform(transform);builder.UpdateEdge(edge,curve,location,1e-7)
        else:
            curve=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.).Copy();curve.Translate(gp_Vec2d(0,.125));builder.UpdateEdge(edge,curve,face,1e-7)
        called.append(association)
        return actual(*args,**kwargs)
    monkeypatch.setattr(_trim_bounds,'verify_fitted_trims',corrupted)
    model=_noniso_trim_model();before=to_dict(model);path=tmp_path/'old.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
        write_geometry(path,model,options=GeometryWriteOptions(fidelity='approximate',max_deviation_m=.1))
    assert len(called)==1 and called[0].document.closed
    assert path.read_bytes()==b'old' and to_dict(model)==before


@pytest.mark.parametrize('suppress',[False,True])
@pytest.mark.parametrize('preset_context',[False,True])
def test_callback_cause_and_suppression_survive_internal_read_restore(tmp_path,monkeypatch,suppress,preset_context):
    import anyfileio
    original=anyfileio.read_cad;state={'inside':False};cause=ValueError('user cause');stop=RuntimeError('user callback')
    context=ValueError('existing context') if preset_context else None
    stop.__cause__=cause;stop.__suppress_context__=suppress;stop.__context__=context
    def reading(*args,**kwargs):state['inside']=True;return original(*args,**kwargs)
    monkeypatch.setattr(anyfileio,'read_cad',reading)
    def cancelled():
        if state['inside']:raise stop
        return False
    model=curves()[0];before=to_dict(model);path=tmp_path/'old.brep';path.write_bytes(b'old')
    with pytest.raises(RuntimeError) as error:write_geometry(path,model,cancellation=cancelled)
    assert error.value is stop and stop.__cause__ is cause and stop.__suppress_context__ is suppress
    assert stop.__context__ is context
    assert path.read_bytes()==b'old' and to_dict(model)==before
