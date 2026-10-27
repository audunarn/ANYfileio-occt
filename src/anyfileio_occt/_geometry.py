"""Exact algebraic conversions and conservative owner-bounded curve fallback."""
from __future__ import annotations
import math
from fractions import Fraction
from decimal import Decimal, localcontext
from itertools import groupby, product
import numpy as np
from anyfileio.geometry import GeometryInterchangeError, GeometryApproximation
from . import _native as native

def outward_norm_squared(squared, cancellation=None):
    with localcontext() as ctx:
        ctx.prec=50
        diameter=float((Decimal(squared.numerator)/Decimal(squared.denominator)).sqrt())
    if math.isfinite(diameter):
        for _ in range(3):
            if Fraction(diameter)**2>=squared: break
            native.checkpoint(cancellation)
            diameter=math.nextafter(diameter,math.inf)
        if not math.isfinite(diameter) or Fraction(diameter)**2<squared:
            refuse('Conservative diameter cannot be represented safely','geometry.bounds.precision')
    return diameter

def refuse(message, code='geometry.entity.unsupported'):
    raise GeometryInterchangeError(message, code=code)

def point(p):
    from OCP.gp import gp_Pnt
    return gp_Pnt(*map(float,p))

def vector(p):
    from OCP.gp import gp_Dir
    return gp_Dir(*map(float,p))

def array1(values, cls):
    arr=cls(1,len(values))
    for i,value in enumerate(values,1): arr.SetValue(i,value)
    return arr

def knots(values):
    from OCP.TColStd import TColStd_Array1OfReal,TColStd_Array1OfInteger
    grouped=[(key,len(list(items))) for key,items in groupby(values)]
    return array1([k for k,m in grouped],TColStd_Array1OfReal),array1([m for k,m in grouped],TColStd_Array1OfInteger)

def bspline_curve(controls, degree, knot_values, weights=None, dimension=3):
    from OCP.TColgp import TColgp_Array1OfPnt,TColgp_Array1OfPnt2d
    from OCP.TColStd import TColStd_Array1OfReal
    from OCP.Geom import Geom_BSplineCurve
    from OCP.Geom2d import Geom2d_BSplineCurve
    from OCP.gp import gp_Pnt2d
    poles=array1([point(p) if dimension==3 else gp_Pnt2d(*map(float,p)) for p in controls],
        TColgp_Array1OfPnt if dimension==3 else TColgp_Array1OfPnt2d)
    k,m=knots(knot_values)
    cls=Geom_BSplineCurve if dimension==3 else Geom2d_BSplineCurve
    if weights is None: return cls(poles,k,m,degree,False)
    return cls(poles,array1(weights,TColStd_Array1OfReal),k,m,degree,False)

def bspline_surface(controls,du,dv,ku,kv,weights=None):
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array2OfReal
    from OCP.Geom import Geom_BSplineSurface
    nu,nv=len(controls),len(controls[0]); poles=TColgp_Array2OfPnt(1,nu,1,nv)
    for i in range(nu):
        for j in range(nv): poles.SetValue(i+1,j+1,point(controls[i][j]))
    u,um=knots(ku); v,vm=knots(kv)
    if weights is None: return Geom_BSplineSurface(poles,u,v,um,vm,du,dv,False,False)
    w=TColStd_Array2OfReal(1,nu,1,nv)
    for i in range(nu):
        for j in range(nv): w.SetValue(i+1,j+1,float(weights[i][j]))
    return Geom_BSplineSurface(poles,w,u,v,um,vm,du,dv,False,False)

def ellipse_curve(center,u,v,start,sweep):
    # Rational quadratic segments represent even oblique affine ellipse axes exactly.
    n=max(1,math.ceil(abs(sweep)/(math.pi/2)))
    poles=[]; weights=[]
    for i in range(n):
        a=start+sweep*i/n; b=start+sweep*(i+1)/n; mid=(a+b)/2; w=math.cos((b-a)/2)
        triplet=[np.asarray(center)+np.asarray(u)*math.cos(a)+np.asarray(v)*math.sin(a),
            np.asarray(center)+(np.asarray(u)*math.cos(mid)+np.asarray(v)*math.sin(mid))/w,
            np.asarray(center)+np.asarray(u)*math.cos(b)+np.asarray(v)*math.sin(b)]
        poles.extend(triplet if i==0 else triplet[1:]); weights.extend([1,w,1] if i==0 else [w,1])
    k=[0.]*3+[float(i) for i in range(1,n) for _ in range(2)]+[float(n)]*3
    return bspline_curve(poles,2,k,weights),0.,float(n)

def surface_to_native(surface, model=None, face=None):
    from anygeometry.surfaces import Plane,Cylinder,Cone,RuledSurface,CoonsSurface,ExtrudedSurface
    from anygeometry.nurbs import NurbsSurface
    from anygeometry.extrusions import BezierDirectrix,EllipseDirectrix
    from OCP.gp import gp_Ax3
    from OCP.Geom import Geom_Plane,Geom_CylindricalSurface,Geom_ConicalSurface
    if isinstance(surface,Plane):
        return Geom_Plane(gp_Ax3(point(surface.origin),vector(surface.normal),vector(surface.u_vector)))
    if isinstance(surface,(Cylinder,Cone)):
        axes=gp_Ax3(point(surface.origin),vector(surface.axis),vector(surface.radial_direction))
        if isinstance(surface,Cylinder): return Geom_CylindricalSurface(axes,surface.radius)
        return Geom_ConicalSurface(axes,math.atan((surface.radius_end-surface.radius_start)/surface.height),surface.radius_start)
    if isinstance(surface,NurbsSurface):
        return bspline_surface(surface.controls,surface.degree_u,surface.degree_v,surface.knots_u,surface.knots_v,surface.weights)
    if isinstance(surface,RuledSurface):
        n=len(surface.first_boundary); us=[i/(n-1) for i in range(n)]
        return bspline_surface([[a,b] for a,b in zip(surface.first_boundary,surface.second_boundary)],1,1,[0]+us+[1],[0,0,1,1])
    if isinstance(surface,CoonsSurface):
        if surface.has_boundaries:
            # Coons' explicit definition is bilinear on each boundary-knot cell.
            # Form its tensor controls algebraically, not from rounded samples.
            us=sorted({Fraction(i,len(a)-1) for a in (surface.bottom,surface.top) for i in range(len(a))})
            vs=sorted({Fraction(i,len(a)-1) for a in (surface.left,surface.right) for i in range(len(a))})
            def sample(points,t):
                scaled=t*(len(points)-1); index=min(scaled.numerator//scaled.denominator,len(points)-2); local=scaled-index
                return tuple((1-local)*Fraction(float(a))+local*Fraction(float(b)) for a,b in zip(points[index],points[index+1]))
            c00=sample(surface.bottom,Fraction(0)); c10=sample(surface.bottom,Fraction(1))
            c01=sample(surface.top,Fraction(0)); c11=sample(surface.top,Fraction(1)); net=[]
            for u in us:
                row=[]
                for v in vs:
                    bottom,top=sample(surface.bottom,u),sample(surface.top,u)
                    left,right=sample(surface.left,v),sample(surface.right,v)
                    exact=[(1-v)*bottom[k]+v*top[k]+(1-u)*left[k]+u*right[k]-
                        ((1-u)*(1-v)*c00[k]+u*(1-v)*c10[k]+u*v*c11[k]+(1-u)*v*c01[k]) for k in range(3)]
                    stored=[float(x) for x in exact]
                    if any(Fraction(x)!=q for x,q in zip(stored,exact)):
                        refuse('Exact explicit Coons tensor coefficient is not representable','geometry.exact.coefficient_unrepresentable')
                    row.append(stored)
                net.append(row)
            u_knots=[float(u) for u in us]; v_knots=[float(v) for v in vs]
            return bspline_surface(net,1,1,[0]+u_knots+[1],[0]+v_knots+[1])
        if model is None or face is None: refuse('Topology-backed Coons needs its owner model context')
        try:
            from anygeometry.interchange import face_support_for_interchange,InterchangeSupportError
        except ImportError as error:
            refuse('Topology-backed Coons requires the public ANYgeometry interchange capability from the tested source candidate','geometry.owner.capability_missing')
        if not callable(face_support_for_interchange):
            refuse('ANYgeometry exact support materialization capability is unavailable','geometry.owner.capability_missing')
        try: explicit=face_support_for_interchange(model,face.id)
        except InterchangeSupportError as error: refuse(str(error),error.code)
        return surface_to_native(explicit)
    if isinstance(surface,ExtrudedSurface):
        if isinstance(surface.directrix,EllipseDirectrix):
            from ._surface_trims import ellipse_extrusion_surface
            return ellipse_extrusion_surface(surface)
        from OCP.Geom import Geom_SurfaceOfLinearExtrusion,Geom_TrimmedCurve
        directrix=surface.directrix
        if isinstance(directrix,BezierDirectrix):
            n=len(directrix.controls); curve=bspline_curve(directrix.controls,n-1,[0.]*n+[1.]*n)
            # Surface support is infinite in extrusion direction; trims retain actual range.
        else: refuse('Unsupported extrusion directrix')
        return Geom_SurfaceOfLinearExtrusion(curve,vector(surface.vector))
    refuse(f'No exact CAD surface conversion for {type(surface).__name__}')

def bounded_polyline(curve, options, source, cancellation=None, scale=1.0, endpoints=None, *,work=None):
    if options.fidelity!='approximate' or options.max_deviation_m is None:
        refuse(f'{type(curve).__name__} requires fidelity=approximate with max_deviation_m', 'geometry.exact.unsupported')
    if not callable(getattr(curve,'bounds',None)):
        refuse(f'{type(curve).__name__} has no public conservative bounds API','geometry.bounds.unavailable')
    requested=options.max_deviation_m
    # Reserve half the prospective tolerance for native serialization endpoints.
    tol=math.nextafter(requested/2,0.)
    if tol<=0: refuse('Tolerance has no representable approximation reserve','geometry.bounds.precision')
    pending=[(0.,1.,0)]; accepted=[]; worst=0.
    while pending:
        native.checkpoint(cancellation)
        a,b,depth=pending.pop()
        if work is not None: work.charge(2) # endpoint evaluation and enclosure query
        p,q=np.asarray(curve.evaluate(np.array([a,b]))),None
        p,q=p[0],p[1]
        box=curve.bounds(a,b)
        # Owner contracts use either (lo,hi) or a six-coordinate bounds tuple.
        values=np.asarray(box,dtype=float)
        if values.shape==(6,): lo,hi=values[:3],values[3:]
        elif values.shape==(2,3): lo,hi=values
        else: refuse('Owner curve bounds has unsupported shape','geometry.bounds.invalid')
        lo=np.minimum(lo,np.minimum(p,q)); hi=np.maximum(hi,np.maximum(p,q))
        if endpoints is not None:
            if a==0.: lo=np.minimum(lo,endpoints[0]); hi=np.maximum(hi,endpoints[0])
            if b==1.: lo=np.minimum(lo,endpoints[1]); hi=np.maximum(hi,endpoints[1])
        # Conservative diameter covers the entire owner enclosure and every chord point.
        squared=sum((Fraction(float(h))-Fraction(float(l)))**2 for l,h in zip(lo,hi))*Fraction(str(scale))**2
        # Exact rational arithmetic tests the stored outward enclosure. The reported
        # float norm is explicitly rounded upward and checked against the same bound.
        diameter=outward_norm_squared(squared,cancellation)
        if squared<=Fraction(tol)**2 and diameter<=tol:
            if work is not None: work.charge()
            accepted.append((a,b,p,q)); worst=max(worst,diameter)
        else:
            if depth>=options.max_depth or len(pending)+len(accepted)+2>options.max_segments:
                refuse('Conservative curve approximation exceeded max_depth/max_segments','geometry.approximation.budget')
            mid=(a+b)/2
            if work is not None: work.charge(2)
            pending.extend([(mid,b,depth+1),(a,mid,depth+1)])
    return accepted,GeometryApproximation(source,requested,worst,'owner conservative AABB diameter')

def verify_serialized_polylines(shape,path,fmt,unit,groups,reports,cancellation=None,scale=1.0,*,work=None,association=None):
    """Enclose actual serialized straight segments, independently of native edge order."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    from OCP.TopExp import TopExp
    from OCP.TopAbs import TopAbs_FORWARD
    from ._units import _CANONICAL_SCALES
    if association is None:refuse('Polyline certificate lacks proved literal targets','geometry.association_unproved')
    output,output_ratio,matches,_=association.topology
    def lines(sh,source=False):
        result=[]; exact=[]; indices=[]; edges=native.shape_map(sh,'edge')
        for i in range(1,edges.Extent()+1):
            native.checkpoint(cancellation)
            if work is not None: work.charge()
            edge=TopoDS.Edge_s(edges.FindKey(i).Oriented(TopAbs_FORWARD)); c=BRepAdaptor_Curve(edge)
            if c.GetType()!=GeomAbs_Line: continue
            if source:
                points=[BRep_Tool.Pnt_s(v) for v in (TopExp.FirstVertex_s(edge,True),TopExp.LastVertex_s(edge,True))]
                rational=[tuple(Fraction(x)*Fraction(str(scale)) for x in (p.X(),p.Y(),p.Z())) for p in points]
            else:
                line=c.Line(); origin=line.Location(); direction=line.Direction()
                rational=[tuple((Fraction(x)+Fraction(t)*Fraction(d))*output_ratio for x,d in zip(
                    (origin.X(),origin.Y(),origin.Z()),(direction.X(),direction.Y(),direction.Z())))
                    for t in (c.FirstParameter(),c.LastParameter())]
            result.append([[float(x) for x in p] for p in rational]); exact.append(rational); indices.append(i)
        return np.asarray(result),indices,exact
    expected,indices,expected_exact=lines(shape,True); actual,actual_indices,actual_exact=lines(output)
    if len(expected)!=len(actual): refuse('Serialization changed straight-edge topology','geometry.approximation.serialization')
    remaining=np.ones(len(actual),dtype=bool); errors={}
    for pair,index,exact_pair in zip(expected,indices,expected_exact):
        native.checkpoint(cancellation)
        if work is not None: work.charge(2*len(actual))
        target_index,reverse=matches[index]
        if target_index not in actual_indices:refuse('Proven literal target is not a line','geometry.association_unproved')
        j=actual_indices.index(target_index)
        if not remaining[j]:refuse('Literal target was claimed twice','geometry.association_unproved')
        remaining[j]=False
        target=actual_exact[j][::-1] if reverse else actual_exact[j]
        squared=max(sum((x-y)**2 for x,y in zip(p,q)) for p,q in zip(exact_pair,target))
        errors[index]=outward_norm_squared(squared,cancellation)
    output_reports=[]
    for report in reports:
        native.checkpoint(cancellation)
        if work is not None: work.charge(len(groups[report.source])+1)
        error=max((errors[i] for i in groups[report.source]),default=0.)
        total=math.nextafter(report.bound_m+error,math.inf)
        if not math.isfinite(total) or total>report.max_deviation_m:
            refuse('Serialized CAD endpoints exceed prospective deviation budget','geometry.approximation.serialization')
        output_reports.append(GeometryApproximation(report.source,report.max_deviation_m,total,
            report.method+' + reread CAD endpoint enclosure'))
    return output_reports

def curve_edge(model, edge, vertices, surface_cache, options, cancellation, *, trim=False,work=None):
    from anygeometry.curves import Straight,Arc,Spline,arc_frame
    from anygeometry.line_ranges import LineRange
    from anygeometry.exact_curves import EllipticArc
    from anygeometry.nurbs import NurbsCurve,CurveOnSurface
    from anygeometry.support_curves import PlaneNurbsCurve
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.BRepLib import BRepLib
    v1,v2=vertices[edge.start],vertices[edge.end]; curve=edge.curve
    a,b=model.vertices[edge.start].position,model.vertices[edge.end].position
    report=None
    def approximate():
        from ._units import _CANONICAL_SCALES
        segments,report=bounded_polyline(curve,options,edge.ref,cancellation,
            _CANONICAL_SCALES[model.units],(a,b),work=work)
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        output=[]; prev=v1
        for i,(_,_,p,q) in enumerate(segments):
            end=v2 if i==len(segments)-1 else BRepBuilderAPI_MakeVertex(point(q)).Vertex()
            builder=BRepBuilderAPI_MakeEdge(prev,end)
            if not builder.IsDone(): refuse('Bounded polyline segment is below native representable edge precision','geometry.approximation.degenerate')
            output.append(builder.Edge()); prev=end
        return output,report
    def fitted_trim(pcurve,s,first,last):
        if options.fidelity!='approximate' or options.max_deviation_m is None:
            refuse('General nonplanar CurveOnSurface needs public exact composition or explicit bounded trim approximation','geometry.exact.composition_unavailable')
        if options.max_segments<30:
            refuse('Native trim fitting needs a minimum 30-segment work allowance','geometry.approximation.budget')
        from ._units import _CANONICAL_SCALES
        from OCP.BRep import BRep_Builder
        from OCP.GeomAbs import GeomAbs_C1
        from ._trim_bounds import METHOD
        tolerance=options.max_deviation_m/(_CANONICAL_SCALES[model.units]*8.)
        if not math.isfinite(tolerance) or tolerance<=0:
            refuse('Native fit tolerance cannot be represented','geometry.bounds.precision')
        builder=BRepBuilderAPI_MakeEdge(pcurve,s,v1,v2,first,last)
        if not builder.IsDone(): refuse('Native pcurve trim construction failed','geometry.edge.invalid')
        shape=builder.Edge(); native.checkpoint(cancellation)
        if not BRepLib.BuildCurves3d_s(shape,tolerance,GeomAbs_C1,14,options.max_segments):
            refuse('Explicit native trim fitting failed','geometry.approximation.fit_failed')
        native.checkpoint(cancellation)
        BRep_Builder().UpdateEdge(shape,tolerance)
        # This is an internal pending record. No report returns before actual file
        # source/3D/pcurve union-box certification replaces the provisional zero.
        return [shape],GeometryApproximation(edge.ref,options.max_deviation_m,0.,METHOD)
    if isinstance(curve,Straight): result=BRepBuilderAPI_MakeEdge(v1,v2)
    elif isinstance(curve,LineRange):
        # Use the retained exact support, not finite topology proxies.
        p,q=curve.evaluate(np.array([0.,1.]))
        result=BRepBuilderAPI_MakeEdge(bspline_curve([p,q],1,[0,0,1,1]),v1,v2)
    elif isinstance(curve,Arc):
        geom=GC_MakeArcOfCircle(point(a),point(model.vertices[curve.via_vertex].position),point(b)).Value()
        result=BRepBuilderAPI_MakeEdge(geom,v1,v2)
    elif isinstance(curve,Spline):
        controls=[a]+[model.vertices[i].position for i in curve.control_vertices]+[b]; n=len(controls)
        result=BRepBuilderAPI_MakeEdge(bspline_curve(controls,n-1,[0.]*n+[1.]*n),v1,v2)
    elif isinstance(curve,EllipticArc):
        geom,first,last=ellipse_curve(curve.center,curve.u_vector,curve.v_vector,curve.start_angle,curve.sweep_angle)
        result=BRepBuilderAPI_MakeEdge(geom,v1,v2,first,last)
    elif isinstance(curve,NurbsCurve):
        if curve.dimension!=3: refuse('Standalone 2D NURBS curve has no world support')
        geom=bspline_curve(curve.controls,curve.degree,curve.knots,curve.weights); first,last=curve.domain
        if first>last:
            geom.Reverse(); first,last=geom.ReversedParameter(first),geom.ReversedParameter(last)
        result=BRepBuilderAPI_MakeEdge(geom,v1,v2,first,last)
    elif isinstance(curve,PlaneNurbsCurve):
        if not trim: return approximate()
        if options.fidelity!='approximate' or options.max_deviation_m is None:
            refuse('Implicit plane/NURBS trims require explicit bounded approximation','geometry.exact.composition_unavailable')
        # Samples propose a pcurve only. The actual-file source/3D/ALL-support
        # enclosure is the sole acceptance criterion, including endpoint error.
        count=min(options.max_segments,256)
        if count<30: refuse('Section proposal exceeded max_segments','geometry.approximation.budget')
        if work is not None: work.charge() # public breakpoints query
        parameters=np.unique(np.r_[np.linspace(0.,1.,count+1),curve.breakpoints()])
        if len(parameters)-1>options.max_segments: refuse('Section proposal exceeded max_segments','geometry.approximation.budget')
        native.checkpoint(cancellation)
        support=curve.surface
        s=surface_cache.get(id(support))
        if s is None: s=surface_to_native(support); surface_cache[id(support)]=s
        if work is not None: work.charge() # public chart evaluation
        uv=curve.chart(parameters)
        controls=[(support.u_range[0]+u*(support.u_range[1]-support.u_range[0]),
                   support.v_range[0]+v*(support.v_range[1]-support.v_range[0])) for u,v in uv]
        knots=(0.,0.)+tuple(float(t) for t in parameters[1:-1])+(1.,1.)
        return fitted_trim(bspline_curve(controls,1,knots,None,2),s,0.,1.)
    elif isinstance(curve,CurveOnSurface):
        if not np.array_equal(curve.transform,np.eye(4)):
            if options.fidelity=='approximate': return approximate()
            refuse('Transformed CurveOnSurface requires exact affine native support conversion')
        s=surface_cache.get(id(curve.support))
        if s is None: s=surface_to_native(curve.support); surface_cache[id(curve.support)]=s
        from anygeometry.nurbs import NurbsSurface
        pc=curve.pcurve; controls=np.asarray(pc.controls,dtype=float)
        if isinstance(curve.support,NurbsSurface):
            ur,vr=curve.support.u_range,curve.support.v_range
            mapped=[]
            for pair in pc.controls:
                exact=[Fraction(r[0])+Fraction(x)*(Fraction(r[1])-Fraction(r[0])) for x,r in zip(pair,(ur,vr))]
                stored=[float(x) for x in exact]
                if any(Fraction(x)!=q for x,q in zip(stored,exact)):
                    refuse('Exact chart control is not representable in native coordinates','geometry.exact.coefficient_unrepresentable')
                mapped.append(stored)
            controls=np.asarray(mapped)
        else: refuse('CurveOnSurface chart mapping is currently implemented for NurbsSurface')
        pcurve=bspline_curve(controls,pc.degree,pc.knots,pc.weights,2)
        first,last=pc.domain
        if first>last:
            pcurve.Reverse(); first,last=pcurve.ReversedParameter(first),pcurve.ReversedParameter(last)
        # Construct an algebraic 3D curve. BRepLib.BuildCurves3d would fit general
        # nonplanar compositions numerically and cannot authorize exact fidelity.
        start=pcurve.Value(first); end=pcurve.Value(last)
        uv0=np.array([start.X(),start.Y()]); uv1=np.array([end.X(),end.Y()])
        affine_pc=pc.degree==1 and len(pc.controls)==2 and (pc.weights is None or len(set(pc.weights))==1)
        exact_fixed=[pc.controls[0][k]==pc.controls[1][k] for k in range(2)] if affine_pc else (False,False)
        if affine_pc and any(exact_fixed):
            from OCP.GeomConvert import GeomConvert
            from OCP.Geom import Geom_TrimmedCurve
            from OCP.TColStd import TColStd_Array1OfReal
            fixed=0 if exact_fixed[0] else 1
            q0,q1=uv0[1-fixed],uv1[1-fixed]
            iso=s.UIso(float(uv0[0])) if fixed==0 else s.VIso(float(uv0[1]))
            geom=GeomConvert.CurveToBSplineCurve_s(Geom_TrimmedCurve(iso,float(min(q0,q1)),float(max(q0,q1))))
            if q0>q1: geom.Reverse()
            low,high=geom.FirstParameter(),geom.LastParameter()
            newknots=[first+(geom.Knot(j)-low)*(last-first)/(high-low) for j in range(1,geom.NbKnots()+1)]
            geom.SetKnots(array1(newknots,TColStd_Array1OfReal))
        else:
            support=curve.support
            net=np.asarray(support.controls)
            affine_support=(support.degree_u==support.degree_v==1 and net.shape==(2,2,3)
                and (support.weights is None or len({w for row in support.weights for w in row})==1)
                and all(Fraction(float(net[1,1,k]))-Fraction(float(net[1,0,k]))-
                    Fraction(float(net[0,1,k]))+Fraction(float(net[0,0,k]))==0 for k in range(3)))
            if not affine_support:
                if options.fidelity=='approximate':
                    return fitted_trim(pcurve,s,first,last) if trim else approximate()
                refuse('General nonplanar CurveOnSurface needs public exact composition or certified trim construction','geometry.exact.composition_unavailable')
            lifted=[]
            for uv in pc.controls:
                u=(Fraction(support.u_range[0])+Fraction(uv[0])*(Fraction(support.u_range[1])-Fraction(support.u_range[0]))-Fraction(support.knots_u[1]))/(Fraction(support.knots_u[-2])-Fraction(support.knots_u[1]))
                v=(Fraction(support.v_range[0])+Fraction(uv[1])*(Fraction(support.v_range[1])-Fraction(support.v_range[0]))-Fraction(support.knots_v[1]))/(Fraction(support.knots_v[-2])-Fraction(support.knots_v[1]))
                values=[Fraction(float(net[0,0,k]))+u*(Fraction(float(net[1,0,k]))-Fraction(float(net[0,0,k])))+
                    v*(Fraction(float(net[0,1,k]))-Fraction(float(net[0,0,k]))) for k in range(3)]
                stored=[float(x) for x in values]
                if any(Fraction(x)!=q for x,q in zip(stored,values)):
                    refuse('Exact affine composition coefficient is not representable','geometry.exact.coefficient_unrepresentable')
                lifted.append(stored)
            geom=bspline_curve(lifted,pc.degree,pc.knots,pc.weights)
            if pc.domain[0]>pc.domain[1]: geom.Reverse()
        result=BRepBuilderAPI_MakeEdge(geom,v1,v2,first,last)
        if not result.IsDone(): refuse('Exact curve-on-surface construction failed','geometry.edge.invalid')
        from OCP.BRep import BRep_Builder
        from OCP.TopLoc import TopLoc_Location
        updater=BRep_Builder(); updater.UpdateEdge(result.Edge(),pcurve,s,TopLoc_Location(),1.e-7)
        updater.Range(result.Edge(),s,TopLoc_Location(),first,last)
    else:
        return approximate()
    if not result.IsDone(): refuse(f'OCCT refused edge {edge.id}','geometry.edge.invalid')
    shape=result.Edge()
    return [shape],report


def attach_section_plane(edge,surface,source_plane):
    """Project full fitted coefficients into the ACTUAL native plane chart.

    Projection is a proposal; serialized plane-PC lifts are certified separately.
    """
    from anygeometry.surfaces import Plane
    from anygeometry.surface_capabilities import capabilities
    from ._trim_bounds import _native_curve,_stored
    from OCP.BRep import BRep_Builder
    from OCP.TopLoc import TopLoc_Location
    position=surface.Position()
    xyz=lambda p:(p.X(),p.Y(),p.Z())
    plane=Plane(xyz(position.Location()),xyz(position.XDirection()),xyz(position.YDirection()))
    a=capabilities(plane).implicit.coefficients
    b=capabilities(source_plane).implicit.coefficients
    pivot=next(i for i,x in enumerate(a) if x)
    if any(x*b[pivot]!=y*a[pivot] for x,y in zip(a,b)):
        refuse('Incident plane is not exactly the implicit section plane','geometry.trim.support_mismatch')
    curve=_native_curve(edge)
    controls=[tuple(_stored(x) for x in capabilities(plane).exact_uv(p)) for p in curve.controls]
    pc=bspline_curve(controls,curve.degree,curve.knots,curve.weights,2)
    builder=BRep_Builder(); location=TopLoc_Location()
    builder.UpdateEdge(edge,pc,surface,location,1.e-7)
    builder.Range(edge,surface,location,*curve.domain)
