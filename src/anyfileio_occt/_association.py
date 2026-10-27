"""BREP native file-record provenance, with no geometric correspondence search."""
from contextlib import contextmanager
from contextvars import ContextVar
from collections import Counter
from dataclasses import dataclass
import hashlib
import io
import math
import struct
from ._geometry import refuse
from . import _native as native

_WRITER=ContextVar('anyfileio_brep_writer',default=None)


class Pool:
    def __init__(self,root,work):
        from OCP.TopTools import TopTools_IndexedMapOfShape
        from OCP.TopAbs import TopAbs_FORWARD
        from ._topology import _children
        self.map=TopTools_IndexedMapOfShape(); self.work=work;self.uses={}
        def add(shape):
            work.charge();value=shape.Oriented(TopAbs_FORWARD);index=self.map.FindIndex(value)
            if index:return index
            work.charge();index=self.map.Add(value);uses=Counter();self.uses[index]=uses
            for child in _children(value,work):uses[(add(child),int(child.Orientation()))]+=1
            return index
        self.root=add(root)
    def index(self,shape):self.work.charge();return self.map.FindIndex(shape)
    def shape(self,index):self.work.charge();return self.map.FindKey(index)


def _location(location,work):
    values=[]
    while not location.IsIdentity():
        work.charge(13);t=location.FirstDatum().Transformation()
        values.append((location.FirstPower(),tuple(t.Value(r,c) for r in range(1,4) for c in range(1,5))))
        location=location.NextLocation()
    return tuple(values)


def _definition(value,work,depth=0):
    """Public defining data, independent of GeomTools decimal formatting.

    Finite native double fields retain their binary64 representation. This is
    representation immutability, not a universal geometric-equivalence test.
    """
    work.charge()
    if depth>64:refuse('Native definition nesting is unsupported','geometry.association_unproved')
    name=value.DynamicType().Name();kind=name.split('_',1)[-1];two=name.startswith('Geom2d_')
    def real(x):
        work.charge();x=float(x)
        if not math.isfinite(x):refuse('Nonfinite native defining parameter','geometry.association_unproved')
        return struct.pack('>d',x)
    def vector(point):
        return tuple(real(getattr(point,c)()) for c in (('X','Y') if two else ('X','Y','Z')))
    def frame(position):
        values=(vector(position.Location()),vector(position.XDirection()),vector(position.YDirection()))
        return values if two else values+(vector(position.Direction()),)
    if kind=='Line':
        line=value.Lin2d() if two else value.Lin()
        return name,vector(line.Location()),vector(line.Direction())
    if kind in ('Circle','Ellipse'):
        data=(name,vector(value.Location()),vector(value.XAxis().Direction()),vector(value.YAxis().Direction()))
        if not two:data+=(vector(value.Axis().Direction()),)
        return data+((real(value.Radius()),) if kind=='Circle' else (real(value.MajorRadius()),real(value.MinorRadius())))
    if kind=='TrimmedCurve':
        return name,real(value.FirstParameter()),real(value.LastParameter()),_definition(value.BasisCurve(),work,depth+1)
    if kind in ('BezierCurve','BSplineCurve'):
        count=value.NbPoles();work.charge(count*4+1)
        data=(name,value.Degree(),bool(value.IsPeriodic()),tuple((vector(value.Pole(i)),real(value.Weight(i))) for i in range(1,count+1)))
        if kind=='BSplineCurve':
            count=value.NbKnots();work.charge(count*2+1)
            data+=(tuple((real(value.Knot(i)),value.Multiplicity(i)) for i in range(1,count+1)),)
        return data
    if kind in ('Plane','CylindricalSurface','ConicalSurface'):
        data=(name,frame(value.Position()))
        if kind=='CylindricalSurface':data+=(real(value.Radius()),)
        if kind=='ConicalSurface':data+=(real(value.RefRadius()),real(value.SemiAngle()))
        return data
    if kind=='SurfaceOfLinearExtrusion':
        return name,vector(value.Direction()),_definition(value.BasisCurve(),work,depth+1)
    if kind=='RectangularTrimmedSurface':
        return name,tuple(real(x) for x in value.Bounds()),_definition(value.BasisSurface(),work,depth+1)
    if kind in ('BezierSurface','BSplineSurface'):
        nu,nv=value.NbUPoles(),value.NbVPoles();work.charge(nu*nv*4+1)
        data=(name,value.UDegree(),value.VDegree(),bool(value.IsUPeriodic()),bool(value.IsVPeriodic()),
              tuple(tuple((vector(value.Pole(i,j)),real(value.Weight(i,j))) for j in range(1,nv+1)) for i in range(1,nu+1)))
        if kind=='BSplineSurface':
            ku,kv=value.NbUKnots(),value.NbVKnots();work.charge((ku+kv)*2+1)
            data+=(tuple((real(value.UKnot(i)),value.UMultiplicity(i)) for i in range(1,ku+1)),
                   tuple((real(value.VKnot(i)),value.VMultiplicity(i)) for i in range(1,kv+1)))
        return data
    refuse(f'Native defining-data snapshot is unsupported for {name}','geometry.association_unproved')


def signature(shape,pool):
    """Immutable native definition BEFORE preparation; not sampled geometry."""
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools
    from OCP.GeomTools import GeomTools
    work=pool.work;work.charge();kind=int(shape.ShapeType())
    base=(kind,_location(shape.Location(),work))
    def geometry(value):
        if value is None:refuse('Native geometric definition is missing','geometry.association_unproved')
        definition=_definition(value,work)
        stream=io.BytesIO();GeomTools.Write_s(value,stream);data=stream.getvalue();work.charge(len(data)//32+1)
        return definition,data
    if kind==7:
        point=BRep_Tool.Pnt_s(TopoDS.Vertex_s(shape.Located(TopLoc_Location())))
        return base+(point.X(),point.Y(),point.Z(),BRep_Tool.Tolerance_s(TopoDS.Vertex_s(shape)))
    if kind==6:
        edge=TopoDS.Edge_s(shape);location=TopLoc_Location();curve=BRep_Tool.Curve_s(edge,location,0.,0.)
        return base+(_location(location,work),geometry(curve),BRep_Tool.Range_s(edge),BRep_Tool.Tolerance_s(edge))
    if kind==4:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE
        face=TopoDS.Face_s(shape);location=TopLoc_Location();surface=BRep_Tool.Surface_s(face,location)
        uses=TopExp_Explorer(face,TopAbs_EDGE);seen=set()
        while uses.More():
            work.charge();identifier=pool.index(uses.Current())
            if identifier in seen:refuse('Repeated face-edge uses need both seam pcurves; association is unproved','geometry.association_unproved')
            seen.add(identifier);uses.Next()
        work.charge(pool.map.Extent());edges=native.shape_map(face,'edge');pcs=[]
        for i in range(1,edges.Extent()+1):
            work.charge();edge=TopoDS.Edge_s(edges.FindKey(i));pc=BRep_Tool.CurveOnSurface_s(edge,face,0.,0.)
            pcs.append((pool.index(edge),geometry(pc),BRep_Tool.Range_s(edge,face)))
        return base+(_location(location,work),geometry(surface),BRepTools.UVBounds_s(face),BRep_Tool.Tolerance_s(face),tuple(sorted(pcs)))
    return base


@dataclass
class Scale:
    shape:object
    operation:object=None
    def entity(self,value):return self.operation.ModifiedShape(value) if self.operation is not None else value


def scale(shape,factor):
    if factor==1.:return Scale(shape)
    from OCP.gp import gp_Trsf,gp_Pnt
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    transform=gp_Trsf();transform.SetScale(gp_Pnt(0,0,0),factor)
    operation=BRepBuilderAPI_Transform(shape,transform,True)
    return Scale(operation.Shape(),operation)


def validate_uses(source,target,entity,work):
    """Pinned entity identity and explicit oriented direct-use multiplicity."""
    right=Pool(target,work);left=Pool(source,work);seen=set()
    for i in range(1,left.map.Extent()+1):
        work.charge();mapped=entity(left.shape(i));j=right.index(mapped)
        if not j or j in seen:refuse('Native entity history is missing or many-to-one','geometry.association.history_invalid')
        seen.add(j);expected=Counter()
        for (child,orientation),count in left.uses[i].items():
            work.charge();ci=right.index(entity(left.shape(child)))
            if not ci:refuse('Native child history is missing','geometry.association.history_invalid')
            expected[(ci,orientation)]+=count
        if expected!=right.uses[j]:refuse('Native history changed oriented uses','geometry.association.history_invalid')
    if len(seen)!=right.map.Extent():refuse('Native history omitted material','geometry.association.history_invalid')


class Snapshot:
    def __init__(self,source,factor,work):
        self.source=source;self.factor=factor;self.work=work;self.si=scale(source,factor);self.pool=Pool(self.si.shape,work)
        self.data={i:signature(self.pool.shape(i),self.pool) for i in range(1,self.pool.map.Extent()+1)}
        validate_uses(source,self.si.shape,self.si.entity,work);self.capsule=None
    def check(self,incoming):
        pool=Pool(incoming,self.work);expected_root=self.pool.root
        for i in range(1,self.pool.map.Extent()+1):
            value=self.pool.shape(i);j=pool.index(value)
            if not j:
                if i==expected_root and int(value.ShapeType())==0 and int(incoming.ShapeType())==0:j=pool.root
                else:refuse('Writer replaced a source native entity','geometry.association.source_changed')
            if self.data[i]!=signature(pool.shape(j),self.pool):
                refuse('Writer changed a frozen source geometric definition','geometry.association.source_changed')
            expected=Counter()
            for (child,orientation),count in self.pool.uses[i].items():expected[(pool.index(self.pool.shape(child)),orientation)]+=count
            if expected!=pool.uses[j]:refuse('Writer changed source oriented uses','geometry.association.source_changed')
        if pool.map.Extent()!=self.pool.map.Extent():refuse('Writer added native material','geometry.association.source_changed')


@contextmanager
def writing(snapshot):
    if _WRITER.get() is not None:refuse('Another BREP association writer is active','geometry.association_unproved')
    token=_WRITER.set(snapshot)
    try:yield snapshot
    finally:_WRITER.reset(token)


def current_writer():return _WRITER.get()


class Decoded:
    def __init__(self,data,cancellation=None):
        from OCP.BRepTools import BRepTools_ShapeSet
        from OCP.TopoDS import TopoDS_Shape
        # Frame extraction only. Geometry remains opaque native ShapeSet data.
        if not data.startswith(b'\nCASCADE Topology V3,'):
            refuse('BREP has no retained native record framing','geometry.association_unproved')
        native.checkpoint(cancellation)
        split=data.rstrip().rfind(b'\n');root_record=data[split+1:]
        self.table=BRepTools_ShapeSet();self.shape=TopoDS_Shape()
        try:self.table.Read(io.BytesIO(data[:split+1]))
        except Exception as error:native.fail(f'BREP table read failed: {error}','cad.read.failed')
        native.checkpoint(cancellation)
        try:self.table.Read(self.shape,io.BytesIO(root_record))
        except Exception as error:native.fail(f'BREP root read failed: {error}','cad.read.failed')
        native.checkpoint(cancellation)
        if self.shape.IsNull():refuse('Native BREP root record is missing','geometry.association_unproved')
        self.sha256=hashlib.sha256(data).hexdigest()
    def entity(self,record):
        from OCP.TopoDS import TopoDS_Shape
        shape=TopoDS_Shape()
        try:self.table.Read(shape,io.BytesIO(record))
        except Exception as error:refuse(f'Invalid native entity record: {error}','geometry.association.record_invalid')
        if shape.IsNull():refuse('Native BREP entity record is missing','geometry.association_unproved')
        return shape
    def record(self,shape):
        stream=io.BytesIO();self.table.Write(shape,stream);return stream.getvalue()


def literal_state(records,work,normalization=None):
    """Whole stored geometry/PCs, keyed by opaque native FILE records."""
    from OCP.TopTools import TopTools_IndexedMapOfShape
    raw=Pool(records.shape,work);targets=TopTools_IndexedMapOfShape();keys={};values=[]
    for i in range(1,raw.map.Extent()+1):
        work.charge();source=raw.shape(i);target=normalization.entity(source) if normalization is not None else source
        index=targets.Add(target)
        if index in keys:refuse('Normalization merged file records','geometry.association.history_invalid')
        keys[index]=records.record(source);values.append((target,keys[index]))
    class View:
        map=targets
        def index(self,shape):
            work.charge();index=targets.FindIndex(shape)
            if index not in keys:refuse('Geometry definition references an unknown record','geometry.association.record_invalid')
            return keys[index]
    view=View();view.work=work
    result={}
    for shape,key in values:
        work.charge();result[key]=signature(shape,view)
    return result


class Capsule:
    def __init__(self,incoming,unit,snapshot):
        from OCP.BRepTools import BRepTools_ShapeSet
        from ._units import _CANONICAL_SCALES
        self.snapshot=snapshot;self.incoming=incoming;work=snapshot.work;snapshot.check(incoming)
        self.raw=scale(incoming,1./_CANONICAL_SCALES[unit]);validate_uses(incoming,self.raw.shape,self.raw.entity,work)
        if getattr(snapshot,'precision',None) is not None:snapshot.precision.freeze_raw_pcs(self)
        self.table=BRepTools_ShapeSet();self.table.Add(self.raw.shape)
        tables=io.BytesIO();self.table.Write(tables);root=io.BytesIO();self.table.Write(self.raw.shape,root)
        self.payload=tables.getvalue()+root.getvalue();work.charge(len(self.payload)//32+1)
        self.sha256=hashlib.sha256(self.payload).hexdigest();self.expected=Decoded(self.payload)
        self.expected_raw=literal_state(self.expected,work)
        self.expected_normalization=scale(self.expected.shape,_CANONICAL_SCALES[unit])
        self.expected_canonical=literal_state(self.expected,work,self.expected_normalization)
        self.records={}
        for i in range(1,snapshot.pool.map.Extent()+1):
            work.charge();value=snapshot.pool.shape(i)
            if i==snapshot.pool.root:value=incoming
            raw=self.raw.entity(value);record=io.BytesIO();self.table.Write(raw,record);self.records[i]=record.getvalue()
        self.record_seal=tuple(sorted(self.records.items()))
        snapshot.capsule=self
    def raw_entity(self,source,decoded):
        si=self.snapshot.si.entity(source);index=self.snapshot.pool.index(si)
        if not index:refuse('Source has no serialized record provenance','geometry.association_unproved')
        record=self.records.get(index)
        if record is None:refuse('Serialized source record is missing','geometry.association.record_invalid')
        if index>len(self.record_seal) or self.record_seal[index-1]!=(index,record):
            refuse('Frozen source record provenance was changed','geometry.association.record_invalid')
        return decoded.entity(record)


def actual_association(source,path,unit,capsule,work,cancellation):
    from anyfileio import read_cad
    from anyfileio.cad import CadReadOptions
    from .backend import document_brep_association,document_shape,document_raw_brep
    from ._topology import compare
    from ._units import _CANONICAL_SCALES
    from fractions import Fraction as Q
    document=None
    try:
        capsule.snapshot.check(capsule.incoming)
        document=read_cad(path,options=CadReadOptions(mode='live',retain_source=False,source_length_unit_override=unit),cancellation=cancellation)
        state=document._backend_state_for('occt')
        if getattr(state,'instances',None) is not None:
            refuse('BREP association cannot consume unrelated occurrence tables','geometry.association.state_invalid')
        records,normalization=document_brep_association(document)
        if records is None or document.manifest.source_sha256!=capsule.sha256 or records.sha256!=capsule.sha256:
            refuse('Written BREP differs from frozen native payload','geometry.association.payload_changed')
        raw,decision=document_raw_brep(document);canonical=document_shape(document)
        if literal_state(records,work)!=capsule.expected_raw:
            refuse('Actual literal geometry differs from frozen decoded payload','geometry.association.literal_changed')
        if literal_state(records,work,normalization)!=capsule.expected_canonical:
            refuse('Canonical normalization differs from frozen decoded expectation','geometry.association.history_invalid')
        mapper=lambda value:capsule.raw_entity(value,records)
        precision=getattr(capsule.snapshot,'precision',None)
        if precision is None:refuse('Source physical precision proof is missing','geometry.precision.unproved')
        precision.check(mapper,Q(str(_CANONICAL_SCALES[unit])),raw=True)
        precision.check(lambda value:normalization.entity(mapper(value)),Q(1))
        # Physical ratios are independent of native floating normalization.
        source_ratio=Q(str(capsule.snapshot.factor))
        matches=compare(source,raw,source_ratio,Q(str(_CANONICAL_SCALES[unit])),work,entity_map=mapper)
        compare(raw,canonical,Q(str(_CANONICAL_SCALES[unit])),Q(1),work,entity_map=normalization.entity)
        association=Actual(document,records,normalization,capsule,work)
        association.topology=(raw,Q(str(_CANONICAL_SCALES[unit])),matches,())
        return association
    except BaseException as error:
        if document is not None:document.close()
        sentinel=getattr(cancellation,'_section_callback_error',None)
        if sentinel is not None and getattr(error,'code',None)=='cad.cancellation_check.failed' and error.__cause__ is sentinel:
            context=sentinel.__context__
            try:raise sentinel
            finally:sentinel.__context__=context
        raise


class Actual:
    def __init__(self,document,records,normalization,capsule,work):
        from .backend import document_shape
        self.document=document;self.records=records;self.normalization=normalization;self.capsule=capsule;self.work=work
        self.sha256=capsule.sha256;self.root=document_shape(document)
        self.maps={};self.refs={}
        for kind in ('vertex','edge','wire','face','shell','solid'):
            work.charge(len(document.manifest.shapes)+1);self.maps[kind]=native.shape_map(self.root,kind)
            self.refs[kind]={r.cad_ref.local_id:r.cad_ref for r in document.manifest.shapes if r.cad_ref.kind==kind}
    def close(self):self.document.close()
    def raw(self,source):return self.capsule.raw_entity(source,self.records)
    def canonical(self,source):return self.normalization.entity(self.raw(source))
    def reference(self,value):
        kind={7:'vertex',6:'edge',5:'wire',4:'face',3:'shell',2:'solid'}.get(int(value.ShapeType()))
        self.work.charge()
        if kind is None:refuse('Native container has no canonical record','geometry.association_unproved')
        index=self.maps[kind].FindIndex(value);reference=self.refs[kind].get(index)
        if reference is None:refuse('Proven native entity has no canonical record','geometry.output.references_missing')
        return reference
