"""Conservative physical fidelity of native source definitions and file records.

This is separate from record identity and from optional approximation proofs.
All arithmetic in the acceptance bounds is rational over stored binary64 data.
"""
from fractions import Fraction as Q
import math
from ._geometry import refuse


def unproved(message):refuse(message,'geometry.precision.unproved')
def exceeded(message):refuse(message,'geometry.precision.exceeded')


def _require_affine_continuation_runtime(work):
    """Only this loaded evaluator has the adopted nonperiodic span proof.

    In-domain partition-of-unity proofs do not depend on this extension.
    Report metadata strings are deliberately not runtime evidence.
    """
    from ._binding import _load_binding
    work.charge();binding=_load_binding()
    if (getattr(binding,'distribution_name',None)!='cadquery-ocp-novtk' or
        getattr(binding,'distribution_version',None)!='7.9.3.1.1' or
        getattr(getattr(binding,'module',None),'__version__',None)!='7.9.3.1'):
        unproved('Out-of-domain affine continuation requires verified OCCT 7.9.3 evaluator runtime')


class Proof:
    def __init__(self,work):self.work=work
    def q(self,x):
        self.work.charge();x=float(x)
        if not math.isfinite(x):unproved('Nonfinite native precision data')
        return Q(x)
    def vec(self,p,dim=3):return tuple(self.q(getattr(p,c)()) for c in ('X','Y','Z')[:dim])
    def frame(self,p):return (self.vec(p.Location()),self.vec(p.XDirection()),self.vec(p.YDirection()),self.vec(p.Direction()))
    def curve(self,c):
        self.work.charge()
        if c is None:unproved('Missing native precision curve')
        name=c.DynamicType().Name();kind=name.split('_',1)[-1];dim=2 if name.startswith('Geom2d_') else 3
        d={'kind':kind,'dim':dim}
        if kind=='TrimmedCurve':d.update(basis=self.curve(c.BasisCurve()));return d
        if kind=='Line':
            data=c.Lin2d() if dim==2 else c.Lin();d.update(origin=self.vec(data.Location(),dim),direction=self.vec(data.Direction(),dim))
        elif kind in ('Circle','Ellipse'):
            d.update(origin=self.vec(c.Location(),dim),x=self.vec(c.XAxis().Direction(),dim),y=self.vec(c.YAxis().Direction(),dim))
            d['radii']=(self.q(c.Radius()),)*2 if kind=='Circle' else (self.q(c.MajorRadius()),self.q(c.MinorRadius()))
        elif kind in ('BSplineCurve','BezierCurve'):
            if c.IsPeriodic():unproved('Periodic precision curve is not admitted')
            n=c.NbPoles();self.work.charge(n);d.update(degree=c.Degree(),poles=tuple(self.vec(c.Pole(i),dim) for i in range(1,n+1)),weights=tuple(self.q(c.Weight(i)) for i in range(1,n+1)))
            if min(d['weights'])<=0:unproved('Nonpositive native precision weight')
            d['knots']=tuple((self.q(c.Knot(i)),c.Multiplicity(i)) for i in range(1,c.NbKnots()+1)) if kind=='BSplineCurve' else ((Q(0),d['degree']+1),(Q(1),d['degree']+1))
        else:unproved('Unsupported native precision curve '+name)
        return d
    def surface(self,s):
        self.work.charge()
        if s is None:unproved('Missing native precision surface')
        kind=s.DynamicType().Name().split('_',1)[-1];d={'kind':kind}
        if kind=='RectangularTrimmedSurface':return self.surface(s.BasisSurface())
        if kind in ('Plane','CylindricalSurface','ConicalSurface'):
            d['frame']=self.frame(s.Position())
            if kind=='CylindricalSurface':d['radius']=self.q(s.Radius())
            if kind=='ConicalSurface':d.update(radius=self.q(s.RefRadius()),angle=self.q(s.SemiAngle()))
        elif kind=='SurfaceOfLinearExtrusion':d.update(direction=self.vec(s.Direction()),basis=self.curve(s.BasisCurve()))
        elif kind in ('BSplineSurface','BezierSurface'):
            if s.IsUPeriodic() or s.IsVPeriodic():unproved('Periodic precision surface is not admitted')
            nu,nv=s.NbUPoles(),s.NbVPoles();self.work.charge(nu*nv)
            d.update(degrees=(s.UDegree(),s.VDegree()),poles=tuple(tuple(self.vec(s.Pole(i,j)) for j in range(1,nv+1)) for i in range(1,nu+1)),weights=tuple(tuple(self.q(s.Weight(i,j)) for j in range(1,nv+1)) for i in range(1,nu+1)))
            if min(w for row in d['weights'] for w in row)<=0:unproved('Nonpositive surface precision weight')
            d['knots']=(tuple((self.q(s.UKnot(i)),s.UMultiplicity(i)) for i in range(1,s.NbUKnots()+1)),tuple((self.q(s.VKnot(i)),s.VMultiplicity(i)) for i in range(1,s.NbVKnots()+1))) if kind=='BSplineSurface' else tuple(((Q(0),p+1),(Q(1),p+1)) for p in d['degrees'])
        else:unproved('Unsupported native precision surface '+kind)
        return d


def l1(values):return sum(abs(x) for x in values)
def distance(a,b,sa,sb):return l1(x*s-y*t for x,y,s,t in zip(a,b,sa,sb))
def same(a,b,keys):
    if any(a[k]!=b[k] for k in keys):unproved('Native precision basis/direction changed: '+','.join(keys))
def expanded(knots,work):
    work.charge(len(knots));work.charge(sum(m for _,m in knots));return tuple(k for k,m in knots for _ in range(m))


def speed(c,scales,work):
    """Full-domain L1 derivative bound, with translated homogeneous controls."""
    work.charge()
    kind=c['kind']
    if kind=='TrimmedCurve':return speed(c['basis'],scales,work)
    if kind=='Line':return l1(a*s for a,s in zip(c['direction'],scales))
    if kind in ('Circle','Ellipse'):return sum(r*l1(v*s for v,s in zip(axis,scales)) for r,axis in zip(c['radii'],(c['x'],c['y'])))
    p=c['degree'];points=c['poles'];weights=c['weights'];knots=expanded(c['knots'],work);wmin=min(weights)
    work.charge(len(points)*3);base=points[0]
    shifted=[tuple((x-y)*s for x,y,s in zip(point,base,scales)) for point in points]
    radius=max(l1(point) for point in shifted);da=dw=Q(0)
    for i in range(len(points)-1):
        work.charge();den=knots[i+p+1]-knots[i+1]
        if den<=0:unproved('Native derivative knot span is unsupported')
        factor=Q(p)/den
        da=max(da,factor*l1(weights[i+1]*y-weights[i]*x for x,y in zip(shifted[i],shifted[i+1])))
        dw=max(dw,factor*abs(weights[i+1]-weights[i]))
    return (da+radius*dw)/wmin


def curve_bound(a,b,sa,sb,ar,br,work):
    """Normalized traversal correspondence on two retained finite domains."""
    work.charge()
    while a['kind']=='TrimmedCurve':a=a['basis']
    while b['kind']=='TrimmedCurve':b=b['basis']
    same(a,b,('kind','dim'));kind=a['kind']
    if kind=='Line':
        # Affine difference reaches its convex L1 bound at interval ends.
        return max(distance(tuple(x+d*t for x,d in zip(a['origin'],a['direction'])),tuple(x+d*u for x,d in zip(b['origin'],b['direction'])),sa,sb) for t,u in zip(ar,br))
    if kind in ('Circle','Ellipse'):
        same(a,b,('x','y'))
        origin=distance(a['origin'],b['origin'],sa,sb)
        radial=sum(l1(v*(ra*s-rb*t) for v,s,t in zip(axis,sa,sb)) for ra,rb,axis in zip(a['radii'],b['radii'],(a['x'],a['y'])))
        return origin+radial+max(abs(x-y) for x,y in zip(ar,br))*speed(b,sb,work)
    work.charge(len(a['poles'])+len(b['poles'])+len(a['knots'])+len(b['knots']))
    same(a,b,('degree','weights'))
    if len(a['poles'])!=len(b['poles']):unproved('Precision pole counts changed')
    degree=a['degree'];normalized=[]
    for curve,domain in ((a,ar),(b,br)):
        ks=expanded(curve['knots'],work);start,end=ks[degree],ks[-degree-1]
        if end<=start:unproved('Zero precision basis span')
        normalized.append((tuple(((k-start)/(end-start),m) for k,m in curve['knots']),tuple((t-start)/(end-start) for t in domain)))
    (ka,ar),(kb,br)=normalized
    if ka!=kb:unproved('Precision knots lack exact full-basis affine transport')
    if degree==1 and len(a['poles'])==2 and ka==((Q(0),2),(Q(1),2)) and a['weights'][0]==a['weights'][1]:
        if min(*ar,*br)<0 or max(*ar,*br)>1:_require_affine_continuation_runtime(work)
        # OCCT7.9.3 LocateParameter clamps the span, not nonperiodic U;
        # D0 evaluates that span's polynomial (BSplCLib.cxx207-286 and
        # BSplCLib_CurveComputation.gxx). This single span has a constant
        # homogeneous denominator, hence is globally affine, even outside.
        def value(curve,t):return tuple((1-t)*x+t*y for x,y in zip(*curve['poles']))
        return max(distance(value(a,t),value(b,u),sa,sb) for t,u in zip(ar,br))
    if min(*ar,*br)<0 or max(*ar,*br)>1:unproved('Precision curve domain is outside active basis')
    work.charge(len(a['poles']))
    coefficient=max(distance(x,y,sa,sb) for x,y in zip(a['poles'],b['poles']))
    basis=dict(b,knots=kb)
    return coefficient+max(abs(x-y) for x,y in zip(ar,br))*speed(basis,sb,work)


def chart_hull(c,domain,factors,work):
    """Full control hull (or analytic enclosure) of a retained pcurve."""
    work.charge()
    if c['kind']=='TrimmedCurve':return chart_hull(c['basis'],domain,factors,work)
    if c['kind']=='Line':points=tuple(tuple(x+t*d for x,d in zip(c['origin'],c['direction'])) for t in domain)
    elif c['kind'] in ('BSplineCurve','BezierCurve'):
        points=c['poles']
        knots=expanded(c['knots'],work);start,end=knots[c['degree']],knots[-c['degree']-1]
        outside=min(domain)<start or max(domain)>end
        affine=c['degree']==1 and len(points)==2 and c['weights'][0]==c['weights'][1]
        if outside:
            if not affine or c['knots']!=((start,2),(end,2)):unproved('Chart continuation lacks a proved global affine span')
            _require_affine_continuation_runtime(work)
        if c['degree']==1 and len(points)==2 and c['weights'][0]==c['weights'][1]:
            points=tuple(tuple((1-(t-start)/(end-start))*x+(t-start)/(end-start)*y for x,y in zip(*points)) for t in domain)
    else:
        radii=c['radii'];points=[]
        for sign in (-1,1):points.append(tuple(x+sign*sum(abs(r*axis[i]) for r,axis in zip(radii,(c['x'],c['y']))) for i,x in enumerate(c['origin'])))
    work.charge(len(points));return tuple((min(p[i]*factors[i] for p in points),max(p[i]*factors[i] for p in points)) for i in range(2))


def surface_bound(a,b,rs,rt,bounds,work):
    """Support error, target-to-source chart factors and source-chart speed."""
    work.charge();same(a,b,('kind',));kind=a['kind'];metric=rs/rt
    if kind in ('BSplineSurface','BezierSurface'):
        nu,nv=len(a['poles']),len(a['poles'][0]);work.charge(nu*nv*3)
        same(a,b,('degrees','knots','weights'))
        if tuple(map(len,a['poles']))!=tuple(map(len,b['poles'])):unproved('Precision surface pole counts changed')
        error=max(distance(x,y,(rs,)*3,(rt,)*3) for row,other in zip(a['poles'],b['poles']) for x,y in zip(row,other))
        # Each tensor direction is a convex blend of rational curve sections.
        def partial(axis):
            size=nv if axis==0 else nu
            # Varying rational row weights need a global homogeneous bound,
            # not a maximum of row derivative speeds. Use tensor-wide radius
            # and min weight in the same derivative inequality.
            allpoints=[p for row in a['poles'] for p in row];base=allpoints[0]
            radius=max(l1((x-y)*rs for x,y in zip(p,base)) for p in allpoints)
            knots=expanded(a['knots'][axis],work);degree=a['degrees'][axis];da=dw=Q(0)
            for j in range(size):
                count=nu if axis==0 else nv
                for i in range(count-1):
                    work.charge();p0=a['poles'][i][j] if axis==0 else a['poles'][j][i];p1=a['poles'][i+1][j] if axis==0 else a['poles'][j][i+1]
                    w0=a['weights'][i][j] if axis==0 else a['weights'][j][i];w1=a['weights'][i+1][j] if axis==0 else a['weights'][j][i+1]
                    den=knots[i+degree+1]-knots[i+1]
                    if den<=0:unproved('Precision surface derivative knot span unsupported')
                    factor=Q(degree)/den;da=max(da,factor*l1((w1*(y-z)-w0*(x-z))*rs for x,y,z in zip(p0,p1,base)));dw=max(dw,factor*abs(w1-w0))
            return (da+radius*dw)/min(w for row in a['weights'] for w in row)
        return error,(Q(1),Q(1)),max(partial(0),partial(1))
    if kind=='SurfaceOfLinearExtrusion':
        same(a,b,('direction',));basis=a['basis']
        while basis['kind']=='TrimmedCurve':basis=basis['basis']
        u_metric=metric if basis['kind']=='Line' else Q(1)
        error=curve_bound(a['basis'],b['basis'],(rs,)*3,(rt,)*3,bounds[:2],tuple(t*u_metric for t in bounds[:2]),work)
        return error,(1/u_metric,1/metric),max(speed(a['basis'],(rs,)*3,work),rs*l1(a['direction']))
    same({'directions':a['frame'][1:]},{'directions':b['frame'][1:]},('directions',))
    origin=distance(a['frame'][0],b['frame'][0],(rs,)*3,(rt,)*3);x,y,z=a['frame'][1:]
    if kind=='Plane':return origin,(1/metric,1/metric),rs*max(l1(x),l1(y))
    radial=abs(a['radius']*rs-b['radius']*rt)*(l1(x)+l1(y))
    if kind=='ConicalSurface':same(a,b,('angle',))
    maxv=max(abs(v) for v in bounds[2:])
    angular=(abs(a['radius'])+(maxv if kind=='ConicalSurface' else 0))*rs*(l1(x)+l1(y))
    vertical=rs*(l1(z)+(l1(x)+l1(y) if kind=='ConicalSurface' else 0))
    return origin+radial,(Q(1),1/metric),max(angular,vertical)


def chart_factors(surface,rs,rt):
    """Target chart coordinates -> source chart, from public support semantics."""
    kind=surface['kind'];length=rt/rs
    if kind=='Plane':return length,length
    if kind in ('CylindricalSurface','ConicalSurface'):return Q(1),length
    if kind=='SurfaceOfLinearExtrusion':
        curve=surface['basis']
        while curve['kind']=='TrimmedCurve':curve=curve['basis']
        return (length if curve['kind']=='Line' else Q(1)),length
    return Q(1),Q(1)


class Source:
    def __init__(self,shape,source_unit,tolerance,work):
        from ._association import Pool
        from ._units import _CANONICAL_SCALES
        self.work=work;self.proof=Proof(work);self.pool=Pool(shape,work)
        self.ratio=Q(str(_CANONICAL_SCALES[source_unit]))
        self.budget=min(Q(tolerance.length),Q(tolerance.surface_residual))*self.ratio/2
        self.data={};self.raw_pcs={}
        for i in range(1,self.pool.map.Extent()+1):
            value=self.pool.shape(i)
            if int(value.ShapeType()) in (7,6,4):self.data[i]=self.capture(value)
        from . import _native
        from OCP.TopoDS import TopoDS
        for i,data in self.data.items():
            if 'surface' not in data:continue
            face=TopoDS.Face_s(self.pool.shape(i));work.charge(self.pool.map.Extent());edges=_native.shape_map(face,'edge');data['pcs']={}
            for j in range(1,edges.Extent()+1):
                edge=edges.FindKey(j);data['pcs'][self.pool.index(edge)]=self.pc(TopoDS.Edge_s(edge),face)
    def capture(self,shape):
        from OCP.TopoDS import TopoDS
        from OCP.TopLoc import TopLoc_Location
        from OCP.BRep import BRep_Tool
        p=self.proof;self.work.charge()
        if shape is None or shape.IsNull():unproved('Pinned precision entity is missing')
        kind=int(shape.ShapeType())
        self.identity(shape.Location())
        if kind==7:return {'point':p.vec(BRep_Tool.Pnt_s(TopoDS.Vertex_s(shape)))}
        location=TopLoc_Location()
        if kind==6:
            edge=TopoDS.Edge_s(shape);curve=BRep_Tool.Curve_s(edge,location,0.,0.);self.identity(location)
            return {'curve':p.curve(curve),'range':tuple(p.q(t) for t in BRep_Tool.Range_s(edge))}
        face=TopoDS.Face_s(shape);surface=BRep_Tool.Surface_s(face,location);self.identity(location)
        return {'surface':p.surface(surface)}
    def identity(self,location):
        # Literal factors, including cancelling chains; cached composite is not proof.
        while not location.IsIdentity():
            self.work.charge(13);transform=location.FirstDatum().Transformation()
            if location.FirstPower()!=0 and any(Q(transform.Value(i,j))!=Q(int(i==j)) for i in range(1,4) for j in range(1,5)):
                unproved('Located precision data needs exact transform transport')
            location=location.NextLocation()
    def pc(self,edge,face):
        from OCP.BRep import BRep_Tool
        return self.proof.curve(BRep_Tool.CurveOnSurface_s(edge,face,0.,0.)),tuple(self.proof.q(t) for t in BRep_Tool.Range_s(edge,face))
    def freeze_raw_pcs(self,capsule):
        from OCP.TopoDS import TopoDS
        from ._association import _definition
        from . import _native
        from OCP.BRep import BRep_Tool
        for i,data in self.data.items():
            if 'surface' not in data:continue
            source=self.pool.shape(i);raw=TopoDS.Face_s(capsule.raw.entity(capsule.snapshot.si.entity(source)))
            self.work.charge(self.pool.map.Extent());edges=_native.shape_map(source,'edge')
            for j in range(1,edges.Extent()+1):
                edge=edges.FindKey(j);index=self.pool.index(edge);target=TopoDS.Edge_s(capsule.raw.entity(capsule.snapshot.si.entity(edge)))
                self.raw_pcs[i,index]=_definition(BRep_Tool.CurveOnSurface_s(target,raw,0.,0.),self.work)
    def check(self,mapper,ratio,*,raw=False):
        from OCP.TopoDS import TopoDS
        from OCP.BRep import BRep_Tool
        from ._association import _definition
        from . import _native
        rs=self.ratio;rt=ratio
        for i,data in self.data.items():
            self.work.charge();source=self.pool.shape(i);target=mapper(source);other=self.capture(target)
            if 'point' in data:error=distance(data['point'],other['point'],(rs,)*3,(rt,)*3)
            elif 'curve' in data:error=curve_bound(data['curve'],other['curve'],(rs,)*3,(rt,)*3,data['range'],other['range'],self.work)
            else:
                face=TopoDS.Face_s(source);actual=TopoDS.Face_s(target);self.work.charge(self.pool.map.Extent());edges=_native.shape_map(face,'edge')
                factors=chart_factors(data['surface'],rs,rt);pairs=[];hulls=[]
                for j in range(1,edges.Extent()+1):
                    edge=edges.FindKey(j);index=self.pool.index(edge);mapped=TopoDS.Edge_s(mapper(edge))
                    if raw and self.raw_pcs.get((i,index))!=_definition(BRep_Tool.CurveOnSurface_s(mapped,actual,0.,0.),self.work):unproved('Serialized raw pcurve defining coefficients changed')
                    a,ar=data['pcs'][index];b,br=self.pc(mapped,actual)
                    self.work.charge();pairs.append((a,ar,b,br))
                    pair_hulls=(chart_hull(a,ar,(Q(1),Q(1)),self.work),chart_hull(b,br,factors,self.work));hulls.extend(pair_hulls)
                    if data['surface']['kind'] in ('BSplineSurface','BezierSurface'):
                        surface=data['surface']
                        for hull in pair_hulls:
                            for axis in range(2):
                                knots=expanded(surface['knots'][axis],self.work);degree=surface['degrees'][axis]
                                if hull[axis][0]<knots[degree] or hull[axis][1]>knots[-degree-1]:unproved('Pcurve enclosure leaves active surface basis')
                if not hulls:unproved('Face has no certified pcurve chart enclosure')
                # No native UVBounds heuristic participates in this proof.
                bounds=tuple(v for axis in range(2) for v in (min(h[axis][0] for h in hulls),max(h[axis][1] for h in hulls)))
                error,_,lipschitz=surface_bound(data['surface'],other['surface'],rs,rt,bounds,self.work)
                for a,ar,b,br in pairs:
                    uv_error=curve_bound(a,b,(Q(1),Q(1)),factors,ar,br,self.work)
                    error_pc=uv_error*lipschitz
                    if error+error_pc>self.budget:exceeded('Physical face/pcurve precision exceeds owner verification reserve')
            if error>self.budget:exceeded('Physical native precision exceeds owner verification reserve')
