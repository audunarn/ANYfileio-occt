"""Actual BREP fidelity against independent pre-encoding physical definitions."""
import pytest
pytest.importorskip('OCP')
from anygeometry import GeometryModel
from anygeometry.nurbs import NurbsCurve
from anygeometry.serialization import to_dict
from anyfileio.geometry import write_geometry,GeometryWriteOptions,GeometryInterchangeError


def curved(offset=0.,integer_ends=False,unit='m',tolerance=None):
    model=GeometryModel(**({'tolerance':tolerance} if tolerance is not None else {}))
    model.set_document_settings(units=unit)
    controls=((offset+(0 if integer_ends else .123456789),0,0),(offset+1.234567891,.456789123,0),(offset+(3 if integer_ends else 3.345678912),0,0))
    a,b=model.add_points((controls[0],controls[-1]));model.add_curve(a,b,NurbsCurve(2,(0,0,0,1,1,1),controls))
    return model


@pytest.mark.parametrize('offset',[1e9,1e12])
@pytest.mark.parametrize('source',['m','mm'])
@pytest.mark.parametrize('output',['m','cm'])
def test_large_offset_vertex_drift_refuses_without_origin_allowance(tmp_path,offset,source,output):
    model=curved(offset,unit=source);before=to_dict(model);path=tmp_path/'precision.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.precision.exceeded'):
        write_geometry(path,model,options=GeometryWriteOptions(output_length_unit=output))
    assert path.read_bytes()==b'old' and to_dict(model)==before and list(tmp_path.iterdir())==[path]


def test_nondecimal_interior_pole_with_integer_end_vertices(tmp_path):
    model=curved(1e12,True);before=to_dict(model);path=tmp_path/'pole.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.precision.exceeded'):
        write_geometry(path,model,options=GeometryWriteOptions(output_length_unit='cm'))
    assert path.read_bytes()==b'old' and to_dict(model)==before


@pytest.mark.parametrize('unit',['m','mm','cm'])
def test_ordinary_nondecimal_curve_and_reversed_basis(tmp_path,unit):
    model=curved();before=to_dict(model);path=tmp_path/'curve.brep'
    report=write_geometry(path,model,options=GeometryWriteOptions(output_length_unit=unit))
    assert report.output_document_id and to_dict(model)==before


@pytest.mark.parametrize('mutation',['scale','pole'])
def test_selfconsistent_native_payload_cannot_define_own_fidelity(tmp_path,monkeypatch,mutation):
    from anyfileio_occt import _association,_native
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Pnt
    original=_association.scale
    def changed(shape,factor):
        result=original(shape,factor*2 if mutation=='scale' and factor==100 else factor)
        if mutation=='pole' and factor==100:
            edge=TopoDS.Edge_s(_native.shape_map(result.shape,'edge').FindKey(1));location=TopLoc_Location()
            curve=BRep_Tool.Curve_s(edge,location,0.,0.);p=curve.Pole(2);curve.SetPole(2,gp_Pnt(p.X(),p.Y()+1,p.Z()))
        return result
    monkeypatch.setattr(_association,'scale',changed)
    model=curved(integer_ends=True);before=to_dict(model);path=tmp_path/'encoder.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.precision.exceeded'):
        write_geometry(path,model,options=GeometryWriteOptions(output_length_unit='cm'))
    assert path.read_bytes()==b'old' and to_dict(model)==before


def test_owner_tolerance_is_used_without_new_relative_allowance(tmp_path):
    from anygeometry.tolerance import TolerancePolicy
    model=curved(tolerance=TolerancePolicy(length=1e-20,surface_residual=1e-20));before=to_dict(model)
    path=tmp_path/'strict.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.precision.exceeded'):
        write_geometry(path,model,options=GeometryWriteOptions(output_length_unit='cm'))
    assert path.read_bytes()==b'old' and to_dict(model)==before


def test_precision_callback_identity_and_cleanup(tmp_path,monkeypatch):
    from anyfileio_occt import _precision
    original=_precision.Source.check;active=[];stop=RuntimeError('precision callback')
    def check(self,*args,**kwargs):active.append(True);return original(self,*args,**kwargs)
    monkeypatch.setattr(_precision.Source,'check',check)
    def cancel():
        if active:raise stop
        return False
    model=curved();before=to_dict(model);path=tmp_path/'callback.brep';path.write_bytes(b'old')
    with pytest.raises(RuntimeError) as error:write_geometry(path,model,cancellation=cancel)
    assert error.value is stop and path.read_bytes()==b'old' and to_dict(model)==before
    assert list(tmp_path.iterdir())==[path]


def test_full_surface_interior_mutation_cannot_hide_behind_boundary(tmp_path,monkeypatch):
    from anygeometry.nurbs import NurbsSurface,CurveOnSurface
    from anyfileio_occt import _association,_native
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Pnt
    surface=NurbsSurface(2,2,(0,0,0,1,1,1),(0,0,0,1,1,1),tuple(tuple((i,j,.5 if i==j==1 else 0) for j in range(3)) for i in range(3)))
    model=GeometryModel();uv=((0,0),(1,0),(1,1),(0,1));vertices=model.add_points(surface.evaluate(*p) for p in uv);edges=[]
    for i in range(4):edges.append(model.add_curve(vertices[i],vertices[(i+1)%4],CurveOnSurface(surface,NurbsCurve(1,(0,0,1,1),(uv[i],uv[(i+1)%4])))))
    model.add_face(edges,surface=surface);original=_association.scale
    def changed(shape,factor):
        result=original(shape,factor)
        if factor==100:
            face=TopoDS.Face_s(_native.shape_map(result.shape,'face').FindKey(1));location=TopLoc_Location();s=BRep_Tool.Surface_s(face,location);p=s.Pole(2,2)
            s.SetPole(2,2,gp_Pnt(p.X(),p.Y(),p.Z()+1))
        return result
    monkeypatch.setattr(_association,'scale',changed)
    before=to_dict(model);path=tmp_path/'surface.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.precision.exceeded'):write_geometry(path,model,options=GeometryWriteOptions(output_length_unit='cm'))
    assert path.read_bytes()==b'old' and to_dict(model)==before


def test_isolated_zero_and_coincident_points_are_all_verified(tmp_path):
    model=GeometryModel();model.add_points(((0,0,0),(0,0,0),(1,0,0)))
    before=to_dict(model);report=write_geometry(tmp_path/'points.brep',model)
    assert len(report.geometry_to_cad)==3
    assert len({r for refs in report.geometry_to_cad.values() for r in refs})==3
    assert to_dict(model)==before


def test_certified_chart_hull_not_native_uvbounds_drives_surface_proof(tmp_path,monkeypatch):
    from test_surface_interchange import grid_model
    from anyfileio_occt import _precision
    from OCP.BRepTools import BRepTools
    model=grid_model('coons');seen=[];original=_precision.surface_bound;active=[]
    original_uv=BRepTools.UVBounds_s
    def uv(*args):
        if active:raise AssertionError('native UVBounds is not a precision enclosure')
        return original_uv(*args)
    monkeypatch.setattr(BRepTools,'UVBounds_s',uv)
    for name in ('__init__','check'):
        method=getattr(_precision.Source,name)
        def wrapped(self,*args,_method=method,**kwargs):
            active.append(True)
            try:return _method(self,*args,**kwargs)
            finally:active.pop()
        monkeypatch.setattr(_precision.Source,name,wrapped)
    def bounded(a,b,rs,rt,bounds,work):
        seen.append(bounds)
        # This explicit public Coons grid has natural normalized chart[0,1]^2.
        # All full boundary-PC hulls together must enclose exactly that box.
        assert bounds==(0,1,0,1)
        return original(a,b,rs,rt,bounds,work)
    monkeypatch.setattr(_precision,'surface_bound',bounded)
    before=to_dict(model);report=write_geometry(tmp_path/'ellipse.brep',model)
    assert seen and report.output_document_id and to_dict(model)==before


def test_one_shared_work_ledger_is_consumed_by_precision(tmp_path,monkeypatch):
    from anyfileio_occt import _precision
    original=_precision.Source.check;ledgers=[]
    def check(self,*args,**kwargs):
        ledgers.append(self.work);self.work.charge(self.work.limit)
        return original(self,*args,**kwargs)
    monkeypatch.setattr(_precision.Source,'check',check)
    model=curved();before=to_dict(model);path=tmp_path/'budget.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.topology.budget'):write_geometry(path,model)
    assert len(ledgers)==1 and ledgers[0].used>ledgers[0].limit
    assert path.read_bytes()==b'old' and to_dict(model)==before


def test_millimetre_bare_line_and_point_to_inches_physical_oracle(tmp_path):
    from fractions import Fraction as Q
    from anyfileio import read_cad
    from anyfileio.cad import CadReadOptions
    from anyfileio_occt.backend import document_raw_brep
    from anyfileio_occt import _native
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    model=GeometryModel();model.set_document_settings(units='mm');a,b=model.add_points(((0,0,0),(2,0,0)));model.add_line(a,b);model.add_point(4,0,0)
    before=to_dict(model);path=tmp_path/'inch.brep';write_geometry(path,model,options=GeometryWriteOptions(output_length_unit='in'))
    with read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override='in')) as doc:
        raw,_=document_raw_brep(doc);vertices=_native.shape_map(raw,'vertex')
        actual=sorted(float(Q(BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertices.FindKey(i))).X())*Q(127,5000)) for i in range(1,vertices.Extent()+1))
        assert actual==pytest.approx([0,.002,.004],abs=1e-12,rel=0)
    assert to_dict(model)==before


def precision_curve(degree,knots,poles,weights):
    from collections import Counter
    from fractions import Fraction as Q
    return {'kind':'BSplineCurve','dim':len(poles[0]),'degree':degree,
            'knots':tuple((Q(k),m) for k,m in Counter(knots).items()),
            'poles':tuple(tuple(Q(x) for x in p) for p in poles),'weights':tuple(Q(w) for w in weights)}


@pytest.mark.parametrize('version_kind',['unknown_module','wrong_module','wrong_distribution','unknown_distribution'])
def test_outside_affine_runtime_guard_and_unchanged_inside_proof(monkeypatch,version_kind):
    from fractions import Fraction as Q
    from types import SimpleNamespace
    from anyfileio_occt import _precision,_binding
    from anyfileio_occt._topology import Work
    actual=_binding._load_binding();module_version={'unknown_module':None,'wrong_module':'7.9.4'}.get(version_kind,'7.9.3.1')
    version={'wrong_distribution':'7.9.3.1.2','unknown_distribution':None}.get(version_kind,'7.9.3.1.1')
    fake=SimpleNamespace(distribution_name=actual.distribution_name,distribution_version=version,module=SimpleNamespace(__version__=module_version))
    monkeypatch.setattr(_binding,'_load_binding',lambda:fake)
    c=precision_curve(1,(0,0,1,1),((0,0),(2,1)),(1,1));one=(Q(1),Q(1));inside=(Q(0),Q(1));outside=(Q(-1,4),Q(5,4))
    assert _precision.curve_bound(c,c,one,one,inside,inside,Work(10000))==0
    assert _precision.chart_hull(c,inside,one,Work(10000))==((0,2),(0,1))
    with pytest.raises(GeometryInterchangeError,match='geometry.precision.unproved'):_precision.curve_bound(c,c,one,one,inside,outside,Work(10000))
    with pytest.raises(GeometryInterchangeError,match='geometry.precision.unproved'):_precision.chart_hull(c,outside,one,Work(10000))


@pytest.mark.parametrize('equal',[False,True])
def test_global_affine_continuation_requires_equal_positive_weights(equal):
    from fractions import Fraction as Q
    from anyfileio_occt import _precision
    from anyfileio_occt._topology import Work
    c=precision_curve(1,(0,0,1,1),((0,0),(2,1)),(1,1 if equal else 2));one=(Q(1),Q(1));inside=(Q(0),Q(1));outside=(Q(-1,4),Q(5,4))
    if equal:
        assert _precision.curve_bound(c,c,one,one,inside,outside,Work(10000))==Q(3,4)
        assert _precision.chart_hull(c,outside,one,Work(10000))==((Q(-1,2),Q(5,2)),(Q(-1,4),Q(5,4)))
    else:
        with pytest.raises(GeometryInterchangeError,match='geometry.precision.unproved'):_precision.curve_bound(c,c,one,one,inside,outside,Work(10000))
        with pytest.raises(GeometryInterchangeError,match='geometry.precision.unproved'):_precision.chart_hull(c,outside,one,Work(10000))


def test_public_outside_pcurve_unknown_evaluator_refuses_atomically(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from test_surface_interchange import grid_model
    from anyfileio_occt import _binding
    actual=_binding._load_binding();fake=SimpleNamespace(distribution_name=actual.distribution_name,distribution_version=actual.distribution_version,module=SimpleNamespace())
    monkeypatch.setattr(_binding,'_load_binding',lambda:fake)
    model=grid_model('coons');before=to_dict(model);path=tmp_path/'runtime.brep';path.write_bytes(b'old')
    with pytest.raises(GeometryInterchangeError,match='geometry.precision.unproved'):write_geometry(path,model,options=GeometryWriteOptions(output_length_unit='mm'))
    assert path.read_bytes()==b'old' and to_dict(model)==before and list(tmp_path.iterdir())==[path]


def test_rational_nonuniform_curve_speed_against_independent_dense_derivatives():
    # Reference samples test the conservative formula; they never accept files.
    import numpy as np
    from fractions import Fraction as Q
    from anyfileio_occt._precision import speed
    from anyfileio_occt._topology import Work
    knots=(0,0,0,.2,.7,1,1,1);poles=((50,1,0),(51,-2,.2),(52,2,-.4),(53,-1,.5),(54,1,0));weights=(.125,2,.5,3,1)
    curve=precision_curve(2,knots,poles,weights);bound=speed(curve,(Q(1),)*3,Work(10000))
    translated=dict(curve,poles=tuple(tuple(x+10**12 for x in p) for p in curve['poles']))
    assert speed(translated,(Q(1),)*3,Work(10000))==bound
    reference=NurbsCurve(2,knots,poles,weights).derivative(np.linspace(0,1,501))
    assert float(bound)>=float(np.max(np.sum(np.abs(reference),axis=-1)))>0


def test_rational_tensor_speed_against_independent_dense_derivatives():
    import numpy as np
    from fractions import Fraction as Q
    from anygeometry.nurbs import NurbsSurface
    from anyfileio_occt._precision import surface_bound
    from anyfileio_occt._topology import Work
    from collections import Counter
    ku=(0,0,0,.3,1,1,1);kv=(0,0,0,1,1,1)
    poles=tuple(tuple((20+i,j,((-1)**(i+j))*.25) for j in range(3)) for i in range(4))
    weights=((.5,2,1),(3,.25,1),(1,2,.75),(2,.5,1))
    surface=NurbsSurface(2,2,ku,kv,poles,weights)
    data={'kind':'BSplineSurface','degrees':(2,2),'knots':tuple(tuple((Q(k),m) for k,m in Counter(ks).items()) for ks in (ku,kv)),
          'poles':tuple(tuple(tuple(Q(x) for x in p) for p in row) for row in poles),'weights':tuple(tuple(Q(w) for w in row) for row in weights)}
    error,_,bound=surface_bound(data,data,Q(1),Q(1),(Q(0),Q(1),Q(0),Q(1)),Work(100000))
    shifted=dict(data,poles=tuple(tuple(tuple(x+10**12 for x in p) for p in row) for row in data['poles']))
    assert surface_bound(shifted,shifted,Q(1),Q(1),(Q(0),Q(1),Q(0),Q(1)),Work(100000))[2]==bound
    uv=np.array([(u,v) for u in np.linspace(0,1,23) for v in np.linspace(0,1,27)])
    du,dv=surface.derivatives_many(uv)
    assert error==0 and float(bound)>=max(float(np.max(np.sum(np.abs(d),axis=-1))) for d in (du,dv))>0


@pytest.mark.parametrize('change',['weight','knot','degree'])
def test_changed_full_curve_basis_refuses(change):
    from fractions import Fraction as Q
    from anyfileio_occt._precision import curve_bound
    from anyfileio_occt._topology import Work
    c=precision_curve(2,(0,0,0,1,1,1),((0,0,0),(1,1,0),(2,0,0)),(1,2,1));other=dict(c)
    if change=='weight':other['weights']=(Q(1),Q(3),Q(1))
    elif change=='knot':other['knots']=((Q(0),3),(Q(1,2),1),(Q(1),2))
    else:other['degree']=1
    with pytest.raises(GeometryInterchangeError,match='geometry.precision.unproved'):curve_bound(c,other,(Q(1),)*3,(Q(1),)*3,(Q(0),Q(1)),(Q(0),Q(1)),Work(10000))


@pytest.mark.parametrize('kind,change',[('Circle','radius'),('Circle','frame'),('Ellipse','frame'),('ConicalSurface','angle'),('CylindricalSurface','radius'),('SurfaceOfLinearExtrusion','u_kind')])
def test_analytic_parameter_changes_have_bound_or_typed_refusal(kind,change):
    from fractions import Fraction as Q
    from anyfileio_occt._precision import curve_bound,surface_bound,chart_factors
    from anyfileio_occt._topology import Work
    origin=(Q(0),)*3;x=(Q(1),Q(0),Q(0));y=(Q(0),Q(1),Q(0));z=(Q(0),Q(0),Q(1));one=(Q(1),)*3;domain=(Q(0),Q(1));work=Work(100000)
    if kind in ('Circle','Ellipse'):
        a={'kind':kind,'dim':3,'origin':origin,'x':x,'y':y,'radii':(Q(2),Q(2))};b=dict(a)
        if change=='radius':b['radii']=(Q(3),Q(3));assert curve_bound(a,b,one,one,domain,domain,work)>=2
        else:
            b['x']=y
            with pytest.raises(GeometryInterchangeError,match='geometry.precision.unproved'):curve_bound(a,b,one,one,domain,domain,work)
    elif kind=='SurfaceOfLinearExtrusion':
        line={'kind':'Line','dim':3,'origin':origin,'direction':x};circle={'kind':'Circle','dim':3,'origin':origin,'x':x,'y':y,'radii':(Q(2),Q(2))};a={'kind':kind,'basis':line,'direction':z};b=dict(a,basis=circle)
        assert chart_factors(a,Q(1,1000),Q(1,100))==(10,10)
        assert chart_factors(b,Q(1,1000),Q(1,100))==(1,10)
        with pytest.raises(GeometryInterchangeError,match='geometry.precision.unproved'):surface_bound(a,b,Q(1),Q(1),(Q(0),Q(1),Q(0),Q(1)),work)
    else:
        a={'kind':kind,'frame':(origin,x,y,z),'radius':Q(2),'angle':Q(1,4)};b=dict(a)
        if change=='angle':
            b['angle']=Q(1,2)
            with pytest.raises(GeometryInterchangeError,match='geometry.precision.unproved'):surface_bound(a,b,Q(1),Q(1),(Q(0),Q(1),Q(0),Q(1)),work)
        else:
            b['radius']=Q(3);error,_,_=surface_bound(a,b,Q(1),Q(1),(Q(0),Q(1),Q(0),Q(1)),work);assert error>=2
