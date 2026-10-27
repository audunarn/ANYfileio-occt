"""Bounded native topology witnesses; coordinates propose, incidence proves."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import cmp_to_key
from fractions import Fraction as Q
from . import _native as native
from ._geometry import refuse

@dataclass
class Work:
    limit: int
    cancellation: object = None
    used: int = 0
    def charge(self, n=1):
        self.used += n
        if self.used > self.limit:
            refuse('Topology proof exceeded max_topology_work', 'geometry.topology.budget')
        native.checkpoint(self.cancellation)

class Graph:
    def __init__(self, work):
        self.work=work; self.colors=[]; self.out=[]; self.inc=[]
        self.points={}; self.entities={}; self.ports={}; self.groups=[]
    def node(self, color):
        self.work.charge(); i=len(self.colors)
        self.colors.append(color); self.out.append(Counter()); self.inc.append(Counter()); return i
    def link(self,a,b,label):
        self.work.charge(); self.out[a][(label,b)]+=1; self.inc[b][(label,a)]+=1

def _children(shape,work=None):
    from OCP.TopoDS import TopoDS_Iterator
    it=TopoDS_Iterator(shape,False,True)
    while it.More():
        if work is not None: work.charge()
        yield it.Value(); it.Next()

def extract(shape, ratio, work, *, transparent_compounds=False, transparent_shells=()):
    """Keep placed identity, direct use multiplicity and consistent directions.

    Transparency is reserved for explicitly approved writer wrappers.
    """
    from OCP.TopAbs import TopAbs_FORWARD,TopAbs_REVERSED,TopAbs_VERTEX
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.TopExp import TopExp
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools,BRepTools_WireExplorer
    from OCP.TopLoc import TopLoc_Location
    graph=Graph(work); identities=TopTools_IndexedMapOfShape(); active=set()
    names={0:'compound',1:'compsolid',2:'solid',3:'shell',4:'face',5:'wire',6:'edge',7:'vertex'}
    def sign(s):
        work.charge(); orientation=s.Orientation()
        if orientation not in (TopAbs_FORWARD,TopAbs_REVERSED):
            refuse('INTERNAL/EXTERNAL native uses cannot be proved', 'geometry.topology.orientation_unsupported')
        return int(orientation==TopAbs_REVERSED)
    def flatten(s):
        kind=names[int(s.ShapeType())]
        remove=(kind=='compound' and transparent_compounds)
        if kind=='shell':
            for t in transparent_shells:
                work.charge()
                if s.IsSame(t): remove=True; break
        if remove:
            work.charge()
            for child in _children(s,work):
                if sign(s): child=child.Reversed()
                yield from flatten(child)
        else: yield s
    def build(s):
        direction=sign(s); canonical=s.Oriented(TopAbs_FORWARD)
        index=identities.FindIndex(canonical)
        if index:
            if index in active: refuse('Cyclic native containers cannot be proved','geometry.topology.cycle')
            return graph.ports[index][direction]
        index=identities.Add(canonical); active.add(index)
        kind=names[int(canonical.ShapeType())]
        closed=bool(BRep_Tool.IsClosed_s(canonical)) if kind in ('wire','shell') else False
        entity=graph.node((kind,closed)); plus=graph.node((kind+' direction',)); minus=graph.node((kind+' direction',))
        graph.entities[index]=(kind,entity,canonical); graph.ports[index]=(plus,minus)
        for port,opposite in ((plus,minus),(minus,plus)):
            graph.link(port,entity,'entity'); graph.link(port,opposite,'opposite')
        if kind=='vertex':
            raw=TopoDS.Vertex_s(canonical.Located(TopLoc_Location()))
            p=BRep_Tool.Pnt_s(raw); xyz=tuple(Q(x) for x in (p.X(),p.Y(),p.Z()))
            t=canonical.Location().Transformation()
            graph.points[entity]=tuple((sum(Q(t.Value(r,c))*xyz[c-1] for c in range(1,4))+Q(t.Value(r,4)))*ratio for r in range(1,4))
        elif kind=='edge':
            edge=TopoDS.Edge_s(canonical)
            endpoints=(TopExp.FirstVertex_s(edge,True),TopExp.LastVertex_s(edge,True))
            if any(v.IsNull() for v in endpoints): refuse('Edgeless parameter endpoints are unsupported','geometry.topology.endpoint_unsupported')
            vertices=[]
            for v in endpoints:
                build(v.Oriented(TopAbs_FORWARD)); vi=identities.FindIndex(v); vertices.append(graph.entities[vi][1])
            if graph.points[vertices[0]]==graph.points[vertices[1]]:
                refuse('Closed/seam edge parameter direction needs an admitted proof','geometry.topology.direction_unsupported')
            for port,values in ((plus,vertices),(minus,vertices[::-1])):
                graph.link(port,values[0],'start'); graph.link(port,values[1],'end')
            direct=list(_children(canonical,work)); work.charge(len(direct))
            if len(direct)!=2 or any(c.ShapeType()!=TopAbs_VERTEX for c in direct):
                refuse('Unsupported edge endpoint-use multiplicity','geometry.topology.endpoint_unsupported')
        elif kind=='wire':
            direct=list(_children(canonical,work)); work.charge(len(direct))
            explorer=BRepTools_WireExplorer(TopoDS.Wire_s(canonical)); ordered=[]
            while explorer.More(): work.charge(); ordered.append(explorer.Current()); explorer.Next()
            unmatched=list(direct)
            for edge in ordered:
                found=None
                for j,value in enumerate(unmatched):
                    work.charge()
                    if edge.IsEqual(value): found=j; break
                if found is None: refuse('Wire order does not cover direct uses','geometry.topology.wire_unsupported')
                unmatched.pop(found)
            if unmatched or not ordered: refuse('Branched or empty wires cannot be proved','geometry.topology.wire_unsupported')
            for port,values in ((plus,ordered),(minus,[v.Reversed() for v in reversed(ordered)])):
                uses=[]
                for value in values:
                    u=graph.node(('coedge',)); graph.link(port,u,'use'); graph.link(u,build(value),'edge'); uses.append(u)
                for a,b in zip(uses,uses[1:]): graph.link(a,b,'next')
                if closed: graph.link(uses[-1],uses[0],'next')
                else: graph.link(port,uses[0],'first'); graph.link(port,uses[-1],'last')
        else:
            children=list(_children(canonical,work)); work.charge(len(children))
            outer=BRepTools.OuterWire_s(TopoDS.Face_s(canonical)) if kind=='face' else None
            for port,reverse in ((plus,False),(minus,True)):
                for child in children:
                    for value in flatten(child):
                        u=graph.node(('use',)); graph.link(port,u,'use')
                        label='outer' if outer is not None and child.IsSame(outer) else 'hole' if kind=='face' else 'child'
                        graph.link(u,build(value.Reversed() if reverse else value),label)
        active.remove(index); return graph.ports[index][direction]
    root=graph.node(('publication',))
    for value in flatten(shape):
        use=graph.node(('publication use',)); graph.link(root,use,'use'); graph.link(use,build(value),'child')
    graph.identities=identities; graph.flatten=flatten
    return graph

def _sorted(values,work):
    def compare(a,b):
        work.charge()
        return (a>b)-(a<b)
    return sorted(values,key=cmp_to_key(compare))

def witness(left,right,work,entity_pins=None):
    """Complete bijection including coincident independent automorphisms."""
    if Counter(left.colors)!=Counter(right.colors): refuse('CAD material/use counts changed','geometry.topology.changed')
    n=len(left.colors); colors=[list(left.colors),list(right.colors)]
    for _ in range(n+1):
        signatures=[]
        for graph,palette in zip((left,right),colors):
            values=[]
            for i in range(n):
                work.charge(1+len(graph.out[i])+len(graph.inc[i]))
                outgoing=Counter(); incoming=Counter()
                for (label,j),k in graph.out[i].items(): outgoing[label,palette[j]]+=k
                for (label,j),k in graph.inc[i].items(): incoming[label,palette[j]]+=k
                values.append((palette[i],tuple(_sorted(outgoing.items(),work)),tuple(_sorted(incoming.items(),work))))
            signatures.append(values)
        work.charge(sum(len(repr(v)) for values in signatures for v in values)//32+1)
        ids={v:i for i,v in enumerate(_sorted(set(signatures[0]+signatures[1]),work))}
        new=[[ids[v] for v in values] for values in signatures]
        if Counter(new[0])!=Counter(new[1]): refuse('CAD incidence partitions changed','geometry.topology.changed')
        stable=len(set(new[0]))==len(set(colors[0])); colors=new
        if stable: break
    buckets=defaultdict(list)
    for j,color in enumerate(colors[1]): buckets[color].append(j)
    # World embedding proposals precede oriented refinement: otherwise a
    # reversed chain's refined start/end roles can force the wrong endpoint.
    nearest={}
    for i,point in left.points.items():
        minimum=None; values=[]
        degree=sum(k for (label,_),k in left.inc[i].items() if label in ('start','end'))
        for j,target in right.points.items():
            work.charge()
            target_degree=sum(k for (label,_),k in right.inc[j].items() if label in ('start','end'))
            if degree!=target_degree: continue
            distance=sum((a-b)**2 for a,b in zip(point,target))
            if minimum is None or distance<minimum: minimum=distance; values=[j]
            elif distance==minimum: values.append(j)
        nearest[i]=set(values)
    candidates=[]
    for i,color in enumerate(colors[0]):
        values=[]
        for j in buckets[color]:
            work.charge()
            if entity_pins is not None and i in entity_pins:
                if j==entity_pins[i]:values.append(j)
            elif i not in nearest or j in nearest[i]: values.append(j)
        candidates.append(values)
    forward={}; inverse={}
    def compatible(i,j):
        work.charge()
        for source,target,graph,other,mapping in ((i,j,left,right,forward),(j,i,right,left,inverse)):
            for adjacency,comparison in ((graph.out[source],other.out[target]),(graph.inc[source],other.inc[target])):
                for (label,k),count in adjacency.items():
                    work.charge()
                    if k in mapping and comparison[(label,mapping[k])]!=count: return False
        return True
    stack=[]
    while len(forward)<n:
        best=None; available=None
        for i in range(n):
            work.charge()
            if i in forward: continue
            choices=[]
            for j in candidates[i]:
                work.charge()
                if j not in inverse and compatible(i,j): choices.append(j)
            if available is None or len(choices)<len(available): best,available=i,choices
            if not choices: break
        if available:
            j=available.pop(0); forward[best]=j; inverse[j]=best; stack.append((best,available)); continue
        while stack:
            i,remaining=stack.pop(); old=forward.pop(i); inverse.pop(old); work.charge()
            if remaining:
                j=remaining.pop(0); forward[i]=j; inverse[j]=i; stack.append((i,remaining)); break
        else: refuse('No complete material-incidence witness exists','geometry.topology.changed')
    for i,j in forward.items():
        work.charge(1+len(left.out[i]))
        translated=Counter({(label,forward[k]):count for (label,k),count in left.out[i].items()})
        if translated!=right.out[j] or j not in candidates[i]: refuse('Invalid topology witness','geometry.topology.changed')
    return forward

def _edge_correspondence(left,right,mapping,source,target,work):
    work.charge(len(left.entities)+len(right.entities))
    source_edges=native.shape_map(source,'edge'); target_edges=native.shape_map(target,'edge')
    target_entities={entity:(index,s) for index,(kind,entity,s) in right.entities.items() if kind=='edge'}
    result={}
    for index,(kind,entity,s) in left.entities.items():
        if kind!='edge': continue
        work.charge()
        target_index,t=target_entities[mapping[entity]]
        reverse=mapping[left.ports[index][0]]==right.ports[target_index][1]
        result[source_edges.FindIndex(s)]=(target_edges.FindIndex(t),reverse)
    return result

def _add_groups(graph,groups,work):
    """Bind every oriented product use, retaining repeated use multiplicity."""
    from OCP.TopAbs import TopAbs_FORWARD,TopAbs_REVERSED
    from OCP.TopAbs import TopAbs_COMPOUND
    for name,shape in groups:
        group=graph.node(('declared product',name))
        work.charge(); graph.groups.append(group)
        # The part compound is a synthetic writer group; flatten ONLY its
        # approved wrappers. Every remaining direct material use gets a node.
        def uses(value):
            if value.ShapeType()==TopAbs_COMPOUND:
                for child in _children(value,work):
                    if value.Orientation()==TopAbs_REVERSED: child=child.Reversed()
                    yield from uses(child)
            else: yield from graph.flatten(value)
        for value in uses(shape):
            work.charge(); orientation=value.Orientation()
            if orientation not in (TopAbs_FORWARD,TopAbs_REVERSED):
                refuse('Unsupported product use orientation','geometry.topology.orientation_unsupported')
            candidates=[]; t=value.Location().Transformation()
            placement=tuple(Q(t.Value(r,c)) for r in range(1,4) for c in range(1,5))
            for index,(kind,entity,member) in graph.entities.items():
                work.charge()
                if not value.IsPartner(member): continue
                u=member.Location().Transformation()
                if placement==tuple(Q(u.Value(r,c)) for r in range(1,4) for c in range(1,5)):
                    candidates.append(index)
            if len(candidates)!=1:
                refuse('Product native identity/placement binding is ambiguous or absent','geometry.topology.scene_unsupported')
            use=graph.node(('product use',)); graph.link(group,use,'use')
            graph.link(use,graph.ports[candidates[0]][int(orientation==TopAbs_REVERSED)],'child')

@dataclass(frozen=True)
class Correspondence:
    entities: tuple
    groups: tuple


def compare(source,target,source_ratio,target_ratio,work,*,transport=False,source_groups=(),target_groups=(),detailed=False,entity_map=None):
    """Prove all material and direct uses, allowing only extra open carriers.

    Source shell identities must survive in the graph. Enumerating a possible
    transparent target shell never deletes its faces or repeated material uses.
    """
    from itertools import combinations
    from OCP.BRep import BRep_Tool
    # Extract and charge each entity/use BEFORE any auxiliary native map or
    # candidate list allocation. The graph itself bounds later native indices.
    left=extract(source,source_ratio,work,transparent_compounds=transport)
    original_right=extract(target,target_ratio,work,transparent_compounds=transport)
    _add_groups(left,source_groups,work)
    source_shells=[]; target_shells=[]; solids=[]
    for graph,shells in ((left,source_shells),(original_right,target_shells)):
        for kind,entity,value in graph.entities.values():
            work.charge()
            if kind=='shell': shells.append(value)
            if graph is original_right and kind=='solid': solids.append(value)
    extra=len(target_shells)-len(source_shells)
    if extra<0 or (extra and not transport): refuse('Declared shells changed','geometry.topology.changed')
    eligible=[]
    for shell in target_shells:
        work.charge(); inside=False
        for solid in solids:
            work.charge(len(original_right.entities))
            if native.shape_map(solid,'shell').Contains(shell): inside=True; break
        if not inside and not BRep_Tool.IsClosed_s(shell): eligible.append(shell)
    for removed in combinations(eligible,extra):
        work.charge()
        right=extract(target,target_ratio,work,transparent_compounds=transport,transparent_shells=removed) if removed else original_right
        _add_groups(right,target_groups,work)
        pins=None
        if entity_map is not None:
            pins={};pinned_targets=set()
            for kind,node,value in left.entities.values():
                work.charge();mapped=entity_map(value);index=right.identities.FindIndex(mapped)
                if not index:refuse('Native provenance has no target entity','geometry.association.history_invalid')
                target_kind,target_node,_=right.entities[index]
                if target_kind!=kind:refuse('Native provenance changed entity kind','geometry.association.history_invalid')
                if target_node in pinned_targets:refuse('Native provenance merged distinct entities','geometry.association.history_invalid')
                pinned_targets.add(target_node)
                pins[node]=target_node
        try: mapping=witness(left,right,work,pins) if pins is not None else witness(left,right,work)
        except Exception as error:
            # Only an unsuccessful witness is an alternative; budget, cancel,
            # unsupported orientation and malformed native data remain terminal.
            if error is getattr(work.cancellation,'_section_callback_error',None): raise
            if getattr(error,'code',None)!='geometry.topology.changed': raise
            continue
        if not detailed: return _edge_correspondence(left,right,mapping,source,target,work)
        work.charge(len(right.entities)+len(right.groups))
        targets={entity:(index,kind,value) for index,(kind,entity,value) in right.entities.items()}
        target_groups_by_node={node:i for i,node in enumerate(right.groups)}
        pairs=[]; group_pairs=[]
        for index,(kind,entity,value) in left.entities.items():
            work.charge()
            ti,tk,target=targets[mapping[entity]]
            if tk!=kind: refuse('Witness entity kind changed','geometry.topology.changed')
            reverse=mapping[left.ports[index][0]]==right.ports[ti][1]
            pairs.append((kind,value,target,reverse))
        for i,node in enumerate(left.groups):
            work.charge(); group_pairs.append((i,target_groups_by_node[mapping[node]]))
        return Correspondence(tuple(pairs),tuple(group_pairs))
    refuse('No complete material/use witness survives serialization','geometry.topology.changed')

def verify_file(source,path,fmt,unit,options,cancellation=None,source_scale=1.,groups=(),*,work=None):
    """Actual-file topology gate; geometric approximation has a separate proof."""
    from ._units import _CANONICAL_SCALES
    from anyfileio.geometry import GeometryDiagnostic
    if work is None: work=Work(options.max_topology_work,cancellation)
    output,decision=native.read_shape(path,fmt,unit if fmt=='brep' else None,cancellation,raw_coordinates=True)
    ratio=Q(str(_CANONICAL_SCALES[decision.effective_unit])); source_ratio=Q(str(source_scale))
    matches=compare(source,output,source_ratio,ratio,work,transport=fmt in ('step','iges'))
    diagnostics=[]
    if fmt=='step':
        if groups:
            from . import _xde
            scene,_,document,definitions,occurrences=_xde.read(path,None,cancellation)
            roots=[o for o in occurrences if o['parent'] is None]
            if len(roots)!=1 or roots[0]['name']!='ANYgeometry' or not definitions[roots[0]['prototype']]['assembly']:
                refuse('Unexpected STEP product root','geometry.topology.scene_changed')
            if any(Q(float(roots[0]['local'][r,c]))!=Q(int(r==c)) for r in range(4) for c in range(4)):
                refuse('Writer root placement changed','geometry.topology.scene_changed')
            leaves=[]
            for occurrence in occurrences:
                work.charge()
                if occurrence is roots[0]: continue
                definition=definitions[occurrence['prototype']]
                if occurrence['parent']!=roots[0]['id'] or definition['assembly']:
                    refuse('Unexpected nested STEP products','geometry.topology.scene_changed')
                # This writer emits baked world geometry and identity product
                # placements. A new location datum, even numerically identity,
                # would not retain native IsSame membership in the scene.
                values=occurrence['world']
                if any(Q(float(values[r,c]))!=Q(int(r==c)) for r in range(4) for c in range(4)):
                    refuse('Writer product placement changed','geometry.topology.scene_changed')
                leaves.append((occurrence['name'],definition['shape']))
            if Counter(n for n,s in groups)!=Counter(n for n,s in leaves):
                refuse('STEP product names or multiplicities changed','geometry.topology.scene_changed')
            compare(source,scene,source_ratio,Q(1),work,transport=True,source_groups=groups,target_groups=leaves)
        else:
            diagnostics.append(GeometryDiagnostic('geometry.cad.transport_products',
                'STEP writer product wrappers are transport only; no structural part intent is inferred. Full material/use incidence was verified.'))
    elif groups and fmt=='brep':
        diagnostics.append(GeometryDiagnostic('geometry.cad.product_names_lost',
            'BREP preserves declared part container/use boundaries, but does not encode product names.'))
    elif groups:
        refuse('This format has no admitted proof of declared product boundaries','geometry.topology.scene_unsupported')
    return output,ratio,matches,diagnostics
