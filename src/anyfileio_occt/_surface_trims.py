"""Algebraic chart transport for admitted natural surface boundaries.

No projection, fitting, healing or coordinate welding is performed here.
"""
from fractions import Fraction as Q
import math
from ._geometry import refuse,bspline_curve
from . import _native as native


def stored(value):
    try: result=float(value)
    except OverflowError: refuse('Exact surface chart coefficient overflows','geometry.exact.coefficient_unrepresentable')
    if not math.isfinite(result) or Q(result)!=value:
        refuse('Exact surface chart coefficient is not representable','geometry.exact.coefficient_unrepresentable')
    return result


def _position(point): return tuple(Q(x) for x in (point.X(),point.Y(),point.Z()))


def _linear_parameter(point,a,b):
    direction=tuple(y-x for x,y in zip(a,b))
    pivot=next((i for i,d in enumerate(direction) if d),None)
    if pivot is None: return None
    t=(point[pivot]-a[pivot])/direction[pivot]
    if not 0<=t<=1 or any(p!=x+t*d for p,x,d in zip(point,a,direction)): return None
    return t


def _grid_borders(surface):
    if surface.UDegree()!=1 or surface.VDegree()!=1 or surface.IsURational() or surface.IsVRational():
        refuse('Natural grid charts require a polynomial piecewise bilinear native support','geometry.trim.chart_unavailable')
    nu,nv=surface.NbUPoles(),surface.NbVPoles()
    if surface.NbUKnots()!=nu or surface.NbVKnots()!=nv:
        refuse('Natural grid chart knot layout is unsupported','geometry.trim.chart_unavailable')
    us=[surface.UKnot(i) for i in range(1,nu+1)]; vs=[surface.VKnot(i) for i in range(1,nv+1)]
    return [
        [((_position(surface.Pole(i,1))),(us[i-1],vs[0])) for i in range(1,nu+1)],
        [((_position(surface.Pole(nu,j))),(us[-1],vs[j-1])) for j in range(1,nv+1)],
        [((_position(surface.Pole(i,nv))),(us[i-1],vs[-1])) for i in range(nu,0,-1)],
        [((_position(surface.Pole(1,j))),(us[0],vs[j-1])) for j in range(nv,0,-1)],
    ]


def attach_grid_boundaries(model,face,surface,edges,cancellation=None):
    """Attach exact PCs for natural Straight/retained-LineRange grid borders."""
    from anygeometry.curves import Straight
    from anygeometry.line_ranges import LineRange
    from OCP.BRep import BRep_Builder,BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    borders=_grid_borders(surface); builder=BRep_Builder()
    for loop in (face.loop,)+face.holes:
        for use in loop:
            native.checkpoint(cancellation)
            edge=model.edges[use.edge]
            a=tuple(Q(float(x)) for x in model.vertices[edge.start].position)
            b=tuple(Q(float(x)) for x in model.vertices[edge.end].position)
            if isinstance(edge.curve,LineRange):
                if tuple(edge.curve.exact_point(0))!=a or tuple(edge.curve.exact_point(1))!=b:
                    refuse('Natural retained-line endpoints require exact native coefficient transport','geometry.exact.coefficient_unrepresentable')
            elif not isinstance(edge.curve,Straight):
                refuse('Natural sampled boundary charts require Straight or exact retained LineRange segments','geometry.trim.chart_unavailable')
            if len(edges[edge.id])!=1:
                refuse('A natural grid trim cannot use a split approximation','geometry.trim.chart_unavailable')
            candidates=[]
            for border in borders:
                def locations(point):
                    found={}
                    for i,((left,uv0),(right,uv1)) in enumerate(zip(border,border[1:])):
                        t=_linear_parameter(point,left,right)
                        if t is not None:
                            uv=tuple(stored(Q(x)+t*(Q(y)-Q(x))) for x,y in zip(uv0,uv1))
                            found[Q(i)+t]=(point,uv)
                    return found
                starts,ends=locations(a),locations(b)
                for start,begin in starts.items():
                    for end,finish in ends.items():
                        if start==end: continue
                        interior=[(Q(i),item) for i,item in enumerate(border) if min(start,end)<i<max(start,end)]
                        interior.sort(reverse=end<start)
                        path=[begin]+[item for station,item in interior]+[finish]
                        parameters=[_linear_parameter(p,a,b) for p,uv in path]
                        if any(t is None for t in parameters): continue
                        if any(y<=x for x,y in zip(parameters,parameters[1:])): continue
                        candidates.append((path,parameters))
            if len(candidates)!=1:
                refuse('Trim does not identify one exact natural grid boundary path','geometry.trim.chart_unavailable')
            path,parameters=candidates[0]; shape=edges[edge.id][0]
            first,last=BRep_Tool.Range_s(shape)
            knots=[stored(Q(first)+t*(Q(last)-Q(first))) for t in parameters]
            pc=bspline_curve([uv for p,uv in path],1,[knots[0]]+knots+[knots[-1]],dimension=2)
            builder.UpdateEdge(shape,pc,surface,TopLoc_Location(),1.e-7)
            builder.Range(shape,surface,TopLoc_Location(),first,last)


def ellipse_extrusion_surface(source):
    """Restricted rational profile tensor, with exactly stored extrusion deltas."""
    from ._geometry import ellipse_curve,bspline_surface
    directrix=source.directrix; ur,vr=source.u_range,source.v_range
    start=stored(Q(directrix.start_angle)+Q(ur[0])*Q(directrix.sweep_angle))
    sweep=stored((Q(ur[1])-Q(ur[0]))*Q(directrix.sweep_angle))
    stored(Q(start)+Q(sweep))
    if not 0<abs(sweep)<2*math.pi:
        refuse('Elliptic extrusion needs a nonperiodic effective angular interval','geometry.trim.periodic_unsupported')
    profile,first,last=ellipse_curve(directrix.center,directrix.u_vector,directrix.v_vector,start,sweep)
    controls=[]; weights=[]
    for i in range(1,profile.NbPoles()+1):
        p=_position(profile.Pole(i))
        controls.append([tuple(stored(x+Q(level)*Q(d)) for x,d in zip(p,source.vector)) for level in vr])
        weights.append([profile.Weight(i),profile.Weight(i)])
    knots=tuple(profile.Knot(i) for i in range(1,profile.NbKnots()+1) for _ in range(profile.Multiplicity(i)))
    return bspline_surface(controls,profile.Degree(),1,knots,(0.,0.,1.,1.),weights)


def _curve_signature(curve):
    from OCP.Geom import Geom_BSplineCurve,Geom_TrimmedCurve
    while isinstance(curve,Geom_TrimmedCurve): curve=curve.BasisCurve()
    if not isinstance(curve,Geom_BSplineCurve) or curve.IsPeriodic():
        refuse('Elliptic boundary must retain the admitted rational native profile','geometry.trim.chart_unavailable')
    return (curve.Degree(),tuple((curve.Knot(i),curve.Multiplicity(i)) for i in range(1,curve.NbKnots()+1)),
        tuple((_position(curve.Pole(i)),Q(curve.Weight(i))) for i in range(1,curve.NbPoles()+1)))


def attach_ellipse_extrusion_boundaries(model,face,surface,edges,cancellation=None):
    """Exact natural profile/generator PCs; CAD u is the rational conic chart."""
    from anygeometry.curves import Straight
    from anygeometry.exact_curves import EllipticArc
    from OCP.BRep import BRep_Builder,BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    source=face.surface; profile=source.directrix; ur,vr=source.u_range,source.v_range
    angle=stored(Q(profile.start_angle)+Q(ur[0])*Q(profile.sweep_angle))
    sweep=stored((Q(ur[1])-Q(ur[0]))*Q(profile.sweep_angle)); end=stored(Q(angle)+Q(sweep))
    u0,u1=surface.FirstUKnotIndex(),surface.LastUKnotIndex()
    first_u,last_u=surface.UKnot(u0),surface.UKnot(u1)
    corners=[(_position(surface.Pole(1,1)),(first_u,0.)),
        (_position(surface.Pole(surface.NbUPoles(),1)),(last_u,0.)),
        (_position(surface.Pole(surface.NbUPoles(),2)),(last_u,1.)),
        (_position(surface.Pole(1,2)),(first_u,1.))]
    centers=[tuple(Q(c)+Q(level)*Q(d) for c,d in zip(profile.center,source.vector)) for level in vr]
    builder=BRep_Builder()
    for loop in (face.loop,)+face.holes:
        for use in loop:
            native.checkpoint(cancellation); edge=model.edges[use.edge]
            if len(edges[edge.id])!=1: refuse('Elliptic natural trim cannot be a split approximation','geometry.trim.chart_unavailable')
            shape=edges[edge.id][0]; first,last=BRep_Tool.Range_s(shape)
            if isinstance(edge.curve,EllipticArc):
                curve=edge.curve
                if tuple(map(Q,curve.u_vector))!=tuple(map(Q,profile.u_vector)) or tuple(map(Q,curve.v_vector))!=tuple(map(Q,profile.v_vector)):
                    refuse('Elliptic boundary uses a different authoritative profile basis','geometry.trim.chart_unavailable')
                levels=[i for i,c in enumerate(centers) if tuple(map(Q,curve.center))==c]
                if len(levels)!=1: refuse('Elliptic boundary is not one exact extrusion level','geometry.trim.chart_unavailable')
                if curve.start_angle==angle and curve.sweep_angle==sweep:
                    pair=[(first_u,float(levels[0])),(last_u,float(levels[0]))]; reverse=False
                elif curve.start_angle==end and curve.sweep_angle==-sweep:
                    pair=[(last_u,float(levels[0])),(first_u,float(levels[0]))]; reverse=True
                else: refuse('Elliptic boundary needs the admitted effective angular interval','geometry.trim.chart_unavailable')
                row=1 if levels[0]==0 else surface.NbVPoles()
                knots=tuple(surface.UKnot(i) for i in range(1,surface.NbUKnots()+1) for _ in range(surface.UMultiplicity(i)))
                # Direct stored border data avoids VIso's homogeneous evaluation
                # introducing an unnecessary divide/rounding operation.
                candidate=bspline_curve([tuple(float(x) for x in _position(surface.Pole(i,row))) for i in range(1,surface.NbUPoles()+1)],
                    surface.UDegree(),knots,[surface.Weight(i,row) for i in range(1,surface.NbUPoles()+1)])
                if reverse: candidate.Reverse()
                if _curve_signature(candidate)!=_curve_signature(BRep_Tool.Curve_s(shape,0.,0.)):
                    refuse('Elliptic boundary and support have different stored rational coefficients','geometry.exact.coefficient_unrepresentable')
                if (first,last)!=(candidate.FirstParameter(),candidate.LastParameter()):
                    refuse('Elliptic profile parameter range differs from the native conic chart','geometry.trim.chart_unavailable')
            elif isinstance(edge.curve,Straight):
                pair=[]
                for vertex in (edge.start,edge.end):
                    point=tuple(Q(float(x)) for x in model.vertices[vertex].position)
                    matches=[uv for p,uv in corners if p==point]
                    if len(matches)!=1: refuse('Extrusion generator does not match an exact native corner','geometry.exact.coefficient_unrepresentable')
                    pair.append(matches[0])
                if pair[0][0]!=pair[1][0] or pair[0][1]==pair[1][1]:
                    refuse('Elliptic extrusion natural generator must keep one profile parameter','geometry.trim.chart_unavailable')
            else: refuse('Elliptic extrusion natural trims require EllipticArc profiles and Straight generators','geometry.trim.chart_unavailable')
            pc=bspline_curve(pair,1,(first,first,last,last),dimension=2)
            builder.UpdateEdge(shape,pc,surface,TopLoc_Location(),1.e-7)
            builder.Range(shape,surface,TopLoc_Location(),first,last)
