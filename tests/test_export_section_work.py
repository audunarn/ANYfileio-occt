"""One shared cooperative/proof budget for real PlaneNurbs CAD export."""
from contextlib import contextmanager
import pytest
pytest.importorskip('OCP')
from anyfileio.geometry import GeometryWriteOptions,GeometryInterchangeError,write_geometry
from anyfileio.cad import CadOperationCancelled
from test_plane_nurbs_trims import section_model


@pytest.fixture(scope='module')
def model():return section_model()


def options(**updates):
    values=dict(fidelity='approximate',max_deviation_m=.01,max_segments=20000)
    values.update(updates);return GeometryWriteOptions(**values)


def test_proposal_budget_failure_preserves_destination_and_source(tmp_path,model):
    from anygeometry.serialization import to_dict
    before=to_dict(model);path=tmp_path/'budget.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
        write_geometry(path,model,options=options(max_segments=30))
    assert path.read_bytes()==b'old' and list(tmp_path.iterdir())==[path] and to_dict(model)==before


@pytest.mark.parametrize('mode',['cancel','geometry_error'])
def test_inside_owner_proposal_callback_identity(tmp_path,model,monkeypatch,mode):
    from anygeometry.errors import GeometryError
    from anygeometry.support_curves import PlaneNurbsCurve
    path=tmp_path/'cancel.brep';path.write_bytes(b'old');active={'query':False,'calls':0};original=PlaneNurbsCurve.chart
    stop=GeometryError('caller identity')
    def chart(self,*args):
        active['query']=True
        return original(self,*args)
    monkeypatch.setattr(PlaneNurbsCurve,'chart',chart)
    def cancellation():
        if active['query']:
            active['calls']+=1
            if mode=='geometry_error':raise stop
            return active['calls']>=5
        return False
    with pytest.raises(CadOperationCancelled if mode=='cancel' else GeometryError) as error:
        write_geometry(path,model,options=options(),cancellation=cancellation)
    if mode=='geometry_error':assert error.value is stop
    assert active['calls'] and path.read_bytes()==b'old' and list(tmp_path.iterdir())==[path]


def test_owner_proposal_refusal_is_typed(tmp_path,model,monkeypatch):
    from anygeometry.support_curves import PlaneNurbsCurve
    from anygeometry.plane_nurbs import PlaneNurbsNotCertified
    monkeypatch.setattr(PlaneNurbsCurve,'chart',lambda *args:(_ for _ in ()).throw(PlaneNurbsNotCertified('owner refusal')))
    path=tmp_path/'owner.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.bounds.owner_refused'):
        write_geometry(path,model,options=options())
    assert path.read_bytes()==b'old'


def test_missing_capability_is_lazy_and_exact_refusal_unchanged(tmp_path,model,monkeypatch):
    import anygeometry.curve_parameter_matching as matching
    from test_native_geometry import square
    monkeypatch.setattr(matching,'bounded_section_work',None)
    path=tmp_path/'missing.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.owner.section_work_missing'):
        write_geometry(path,model,options=options())
    assert path.read_bytes()==b'old'
    with pytest.raises(GeometryInterchangeError,match='geometry.exact.composition_unavailable'):
        write_geometry(path,model)
    write_geometry(tmp_path/'ordinary.brep',square())


def test_foreign_active_context_refuses_without_override(tmp_path,model):
    from anygeometry.curve_parameter_matching import bounded_section_work
    path=tmp_path/'nested.brep';path.write_bytes(b'old')
    with bounded_section_work(max_work=20000) as ledger:
        with pytest.raises(GeometryInterchangeError,match='geometry.owner.section_work_conflict'):
            write_geometry(path,model,options=options())
        assert ledger.work_used==0
    assert path.read_bytes()==b'old'


def test_certified_plane_section_refuses_atomically_without_bypassing_gate(tmp_path,model,monkeypatch):
    import anygeometry.serialization as serializer
    path=tmp_path/'certified.brep';path.write_bytes(b'old')
    monkeypatch.setattr(serializer,'to_dict',lambda *args,**kwargs:pytest.fail('unsafe nested certified audit entered'))
    with pytest.raises(GeometryInterchangeError,match='geometry.owner.cooperative_validation_missing'):
        write_geometry(path,model,options=options(validation_mode='certified'))
    assert path.read_bytes()==b'old' and list(tmp_path.iterdir())==[path]


def test_other_family_certified_validation_still_runs(tmp_path,monkeypatch):
    import anygeometry.serialization as serializer
    from test_native_geometry import square
    original=serializer.to_dict;calls=[]
    def validate(*args,**kwargs):
        calls.append(kwargs.get('certified'));return original(*args,**kwargs)
    monkeypatch.setattr(serializer,'to_dict',validate)
    write_geometry(tmp_path/'square.brep',square(),options=GeometryWriteOptions(validation_mode='certified'))
    assert True in calls

@pytest.fixture
def observed(monkeypatch):
    import anygeometry.curve_parameter_matching as matching
    from anygeometry.support_curves import PlaneNurbsCurve
    from anyfileio_occt import _trim_bounds,_geometry,geometry_export
    records=dict(active=False,enforce=False,ledgers=[],works=[],proof_work=None,proof_started=False,proof_bounds=0,free=[],queries={})
    context=matching.bounded_section_work;records['real_context']=context
    @contextmanager
    def scope(**kwargs):
        with context(**kwargs) as ledger:
            records['ledgers'].append(ledger);records['active']=True
            try:yield ledger
            finally:records['active']=False
    monkeypatch.setattr(matching,'bounded_section_work',scope)
    original_work=_trim_bounds._Work
    class Tracked(original_work):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);records['works'].append(self)
    monkeypatch.setattr(_trim_bounds,'_Work',Tracked)
    for name in ('chart','breakpoints','bounds','evaluate'):
        original=getattr(PlaneNurbsCurve,name)
        def checked(self,*args,_name=name,_original=original,**kwargs):
            if records['enforce']:
                assert records['active'],_name+' escaped owner scope'
                records['queries'][_name]=records['queries'].get(_name,0)+1
                if _name=='bounds' and records['proof_started']:records['proof_bounds']+=1
            return _original(self,*args,**kwargs)
        monkeypatch.setattr(PlaneNurbsCurve,name,checked)
    verify=_trim_bounds.verify_fitted_trims
    def verified(*args,**kwargs):
        records['proof_started']=True;records['proof_work']=kwargs['work'];records['proof_start']=kwargs['work'].used
        return verify(*args,**kwargs)
    monkeypatch.setattr(_trim_bounds,'verify_fitted_trims',verified)
    polyline=_geometry.bounded_polyline
    def free(*args,**kwargs):
        work=kwargs['work'];start=work.used
        result=polyline(*args,**kwargs);records['free'].append((work,start,work.used));return result
    monkeypatch.setattr(_geometry,'bounded_polyline',free)
    return records


@pytest.mark.parametrize('deviation,allowance',[(.01,20000),(.002,100000)])
def test_real_proposal_and_serialized_proof_share_one_finite_ledger(tmp_path,model,observed,deviation,allowance):
    from anygeometry.serialization import to_dict
    before=to_dict(model);observed['enforce']=True
    report=write_geometry(tmp_path/'shared.brep',model,options=options(max_deviation_m=deviation,max_segments=allowance))
    observed['enforce']=False
    assert len(observed['works'])==len(observed['ledgers'])==1
    work=observed['works'][0]
    assert observed['proof_work'] is work and 0<observed['proof_start']<work.used<=allowance
    assert observed['proof_bounds'] and observed['queries']['chart'] and observed['queries']['breakpoints']
    assert 0<observed['ledgers'][0].work_used<work.used
    assert all(record.bound_m<=deviation for record in report.approximations)
    assert not observed['active'] and to_dict(model)==before


def test_old_20k_exhaustion_is_late_and_atomic(tmp_path,model,observed,monkeypatch):
    from anyfileio_occt import _native
    original=_native.write_shape;written=[]
    def write(*args,**kwargs):
        result=original(*args,**kwargs);written.append(True);return result
    monkeypatch.setattr(_native,'write_shape',write)
    path=tmp_path/'late.brep';path.write_bytes(b'old');observed['enforce']=True
    with pytest.raises(GeometryInterchangeError,match='geometry.approximation.budget'):
        write_geometry(path,model,options=options(max_deviation_m=.002))
    assert written and observed['proof_started'] and path.read_bytes()==b'old'
    assert not observed['active'] and len(observed['works'])==1
    with observed['real_context'](max_work=1) as ledger:assert ledger.work_used==0


def test_two_free_sections_use_same_ledger_without_reset(tmp_path,model,observed,monkeypatch):
    from anygeometry import GeometryModel
    from anygeometry.support_curves import PlaneNurbsCurve
    import numpy as np
    # Keep this ledger-sharing fixture small enough for the independent graph
    # search budget; the whole section remains covered by the face tests.
    curve=next(edge.curve for edge in model.edges.values() if isinstance(edge.curve,PlaneNurbsCurve)).subcurve(.1,.2)
    move=np.eye(4);move[0,3]=2.;free=GeometryModel()
    for source in (curve,curve.transformed(move)):
        a,b=free.add_points(source.evaluate(np.array([0.,1.])));free.add_curve(a,b,source)
    from anyfileio_occt import _geometry
    verify=_geometry.verify_serialized_polylines;proof=[]
    def verified(*args,**kwargs):
        work=kwargs['work'];start=work.used
        result=verify(*args,**kwargs);proof.append((work,start,work.used));return result
    monkeypatch.setattr(_geometry,'verify_serialized_polylines',verified)
    observed['enforce']=True
    report=write_geometry(tmp_path/'free.brep',free,options=options(max_deviation_m=.1))
    assert len(report.approximations)==2 and all(r.bound_m<=.1 for r in report.approximations)
    assert len(observed['works'])==len(observed['ledgers'])==1 and len(observed['free'])==2
    first,second=observed['free']
    assert first[0] is second[0] is observed['works'][0] and 0<first[2]<=second[1]<second[2]<=20000
    assert len(proof)==1 and proof[0][0] is first[0] and second[2]<=proof[0][1]<proof[0][2]<=20000
    assert observed['queries']['evaluate'] and observed['queries']['bounds'] and not observed['active']


def test_native_writer_failure_restores_context_and_keeps_destination(tmp_path,model,observed,monkeypatch):
    from anyfileio_occt import _native
    stop=RuntimeError('writer identity');path=tmp_path/'writer.brep';path.write_bytes(b'old')
    def fail(*args,**kwargs):raise stop
    monkeypatch.setattr(_native,'write_shape',fail)
    with pytest.raises(RuntimeError) as error:write_geometry(path,model,options=options())
    assert error.value is stop and path.read_bytes()==b'old' and not observed['active']
    with observed['real_context'](max_work=1) as ledger:assert ledger.work_used==0


@pytest.mark.parametrize('section',[True,False])
def test_callback_exception_is_not_relabelled_by_topology_handler(tmp_path,model,monkeypatch,section):
    from anyfileio_occt import _association,_native
    if not section:
        from test_native_geometry import _noniso_trim_model
        model=_noniso_trim_model()
    original=_association.actual_association;state={'topology':False};stop=GeometryInterchangeError('callback identity',code='geometry.topology.changed')
    def verify(*args,**kwargs):state['topology']=True;return original(*args,**kwargs)
    monkeypatch.setattr(_association,'actual_association',verify)
    def cancelled():
        if state['topology']:raise stop
        return False
    path=tmp_path/'callback.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError) as error:write_geometry(path,model,options=options(),cancellation=cancelled)
    assert error.value is stop and path.read_bytes()==b'old'


def test_cancellation_during_actual_owner_bound_restores_scope(tmp_path,model,observed,monkeypatch):
    from anygeometry.support_curves import PlaneNurbsCurve
    original=PlaneNurbsCurve.bounds;state={'bounds':False}
    def bounds(*args,**kwargs):state['bounds']=True;return original(*args,**kwargs)
    monkeypatch.setattr(PlaneNurbsCurve,'bounds',bounds)
    path=tmp_path/'proof.brep';path.write_bytes(b'old')
    with pytest.raises(CadOperationCancelled):
        write_geometry(path,model,options=options(),cancellation=lambda:state['bounds'])
    assert observed['proof_started'] and path.read_bytes()==b'old' and not observed['active']
    with observed['real_context'](max_work=1) as ledger:assert ledger.work_used==0
