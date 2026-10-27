"""Lazy protocol-1 OCCT provider."""
from __future__ import annotations
from dataclasses import dataclass
import threading
import numpy as np
from anyfileio.cad import (CadCapabilities, CadDiagnostic, CadDocument, CadManifest,
    CadEntityRef, CadPrototypeRecord, CadOccurrenceRecord, CadShapeRecord,
    CadPrototypeMesh, CadTessellation, CadAssetWriteReport, CadTessellationOptions)
from ._binding import _load_binding
from ._session import _NativeSession
from . import _native as native
VERSION = '0.1.1'

@dataclass
class _State:
    session: _NativeSession
    shape: object
    xde_document: object = None
    prototypes: object = None
    instances: object = None
    references: object = None
    raw_brep: object = None
    raw_brep_units: object = None
    raw_records: object = None
    normalization: object = None
    def use(self):
        return self.session.use(self.shape)

def document_shape(document):
    state = document._backend_state_for('occt')
    if not isinstance(state, _State):
        native.fail('operation requires an open live OCCT document', 'cad.session.required')
    return state.use()


def document_raw_brep(document):
    """Session-owned literal BREP from the same read that produced canonical SI."""
    state=document._backend_state_for('occt')
    if not isinstance(state,_State) or state.raw_brep is None or state.raw_brep_units is None:
        native.fail('Literal BREP source is unavailable in this live document','cad.raw_brep.unavailable')
    return state.session.use(state.raw_brep),state.raw_brep_units


def document_brep_association(document):
    state=document._backend_state_for('occt')
    if not isinstance(state,_State) or state.raw_brep is None or state.normalization is None:
        native.fail('BREP normalization history is unavailable','geometry.association_unproved')
    state.session.use(state.shape);state.session.use(state.raw_brep)
    return state.raw_records,state.normalization

def _close(state):
    state.session.close()

def _assembly_records(did,definitions,instances):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf
    counters={k:0 for k in ('solid','shell','face','wire','edge','vertex')}
    prototypes=[]; occurrences=[]; records=[]; meshes={}; references={}; expanded=[]
    for pid,data in definitions.items():
        shape=data['shape']; references[pid]={}
        if data['assembly']:
            empty=TopoDS_Compound(); BRep_Builder().MakeCompound(empty); meshes[pid]=empty
        else: meshes[pid]=shape
        prototypes.append(CadPrototypeRecord(pid,CadEntityRef(did,'prototype',pid),data['name'],
            'assembly' if data['assembly'] else 'compound',native.bounds(shape),native.counts(shape)))
        for kind in counters:
            references[pid][kind]={}
            if data['assembly']: continue
            shapes=native.shape_map(shape,kind)
            for i in range(1,shapes.Extent()+1):
                counters[kind]+=1; ref=CadEntityRef(did,kind,counters[kind]); references[pid][kind][i]=ref
                records.append(CadShapeRecord(ref,pid,None,None,'',kind,native.bounds(shapes.FindKey(i)),None,None,()))
    for instance in instances:
        pid=instance['prototype']; shape=definitions[pid]['shape']; world=instance['world']
        tr=gp_Trsf(); tr.SetValues(*[float(x) for x in world[:3,:].flat])
        located=shape.Moved(TopLoc_Location(tr))
        occurrences.append(CadOccurrenceRecord(instance['id'],CadEntityRef(did,'occurrence',instance['id']),pid,
            instance['parent'],instance['local'],world,native.bounds(located),instance['name'],True))
        if not definitions[pid]['assembly']: expanded.append((instance['id'],located,references[pid]))
    return tuple(prototypes),tuple(occurrences),records,meshes,tuple(expanded),references

class _OcctBackend:
    backend_id = 'occt'
    protocol_version = 1
    backend_compatibility_version = 1
    backend_version = VERSION
    capabilities = CadCapabilities(read_formats=frozenset({'step','iges','brep'}),
        write_formats=frozenset({'step','iges','brep'}),
        import_modes=frozenset({'manifest_only','preview','live'}),
        inspect=True, assembly=True, tessellate=True, preserve=True, translate=True)

    def read(self, source_snapshot, *, source_sha256, source_name, options,
             tessellation_options=None, cancellation=None):
        if options.heal:
            native.fail('healing is not implemented', 'cad.healing.unsupported')
        fmt = native.format_for(source_name)
        try:
            from anyfileio.cad import cad_import_document_id
        except ImportError:
            native.fail('OCCT import requires the public core canonical CAD identity capability','cad.core.capability_missing')
        if not callable(cad_import_document_id):
            native.fail('Core canonical CAD identity capability is unavailable','cad.core.capability_missing')
        assembly_data=None; raw_brep=None; raw_brep_units=None;raw_records=None;normalization=None
        if fmt=='step':
            from . import _xde
            shape,decision,xdoc,xprototypes,xoccurrences=_xde.read(source_snapshot,options.source_length_unit_override,cancellation)
            assembly_data=(xdoc,xprototypes,xoccurrences)
        elif fmt=='brep':
            raw_brep,decision,raw_records,normalization=native.read_brep_retained(source_snapshot,options.source_length_unit_override,cancellation)
            raw_brep_units=decision
            shape=normalization.shape
        else:
            shape, decision = native.read_shape(source_snapshot, fmt, options.source_length_unit_override, cancellation)
        binding = _load_binding()
        did = cad_import_document_id(source_sha256=source_sha256,source_format=fmt,
            effective_source_length_unit=decision.effective_unit,heal=options.heal,
            backend_id=self.backend_id,backend_compatibility_version=self.backend_compatibility_version)
        ref = lambda kind, i: CadEntityRef(did, kind, i)
        box, topology = native.bounds(shape), native.counts(shape)
        records = []
        for kind in ('solid','shell','face','wire','edge','vertex'):
            shapes = native.shape_map(shape, kind)
            for i in range(1, shapes.Extent()+1):
                bounds = native.bounds(shapes.FindKey(i))
                records.append(CadShapeRecord(ref(kind,i),1,1,None,'',kind,bounds,bounds,None,()))
        prototypes=(CadPrototypeRecord(1,ref('prototype',1),source_name,'compound',box,topology),)
        occurrences=(CadOccurrenceRecord(1,ref('occurrence',1),1,None,np.eye(4),np.eye(4),box,source_name,True),)
        prototype_shapes=instances=references=None
        if assembly_data is not None:
            prototypes,occurrences,records,prototype_shapes,instances,references=_assembly_records(did,*assembly_data[1:])
        manifest = CadManifest(document_id=did, source_sha256=source_sha256,
            source_name=source_name, source_format=fmt, source_length_unit=decision.effective_unit,
            source_to_metre_scale=decision.source_to_metre_scale, internal_length_unit='m',
            root_occurrence_ids=tuple(o.id for o in occurrences if o.parent_id is None),
            prototypes=prototypes,occurrences=occurrences,
            shapes=tuple(records), world_bounds_m=box, topology_counts=topology, external_references=(),
            diagnostics=(CadDiagnostic('cad.metadata.partial','warning',
                'STEP product hierarchy/names retained; colours/layers and IGES hierarchy are not retained'),),
            normalized_read_options=options, backend_id='occt', backend_version=VERSION,
            backend_compatibility_version=1,binding_distribution=binding.distribution_name,
            binding_version=binding.distribution_version,occt_version='7.9.3')
        session = _NativeSession()
        session.acquire(shape, lambda value: None)
        if raw_brep is not None and raw_brep is not shape: session.acquire(raw_brep,lambda value:None)
        if assembly_data is not None: session.acquire(assembly_data[0],lambda value:None)
        state=_State(session,shape,assembly_data[0] if assembly_data else None,prototype_shapes,instances,references,raw_brep,raw_brep_units,raw_records,normalization)
        document = CadDocument._from_backend(manifest=manifest,backend_state=state,
            close_backend_state=_close,owner_thread_id=threading.get_ident())
        try:
            if options.mode == 'preview':
                tessellation_options = tessellation_options or CadTessellationOptions()
                meshes = self.tessellate(document, options=tessellation_options, cancellation=cancellation)
                document.close()
                return CadDocument._from_backend(manifest=manifest,tessellation_options=tessellation_options,
                    prototype_meshes=meshes,source_snapshot=source_snapshot if options.retain_source else None)
            if options.mode == 'manifest_only':
                document.close()
                return CadDocument._from_backend(manifest=manifest,
                    source_snapshot=source_snapshot if options.retain_source else None)
            meshes=() if tessellation_options is None else self.tessellate(document,
                options=tessellation_options,cancellation=cancellation)
            return CadDocument._from_backend(manifest=manifest,tessellation_options=tessellation_options,
                prototype_meshes=meshes,source_snapshot=source_snapshot if options.retain_source else None,
                backend_state=state,close_backend_state=_close,owner_thread_id=threading.get_ident())
        except BaseException:
            document.close()
            raise

    def tessellate(self, document, *, options, cancellation=None):
        state=document._backend_state_for('occt')
        if isinstance(state,_State) and state.prototypes is not None:
            from dataclasses import replace
            output=[]
            for pid,prototype_shape in state.prototypes.items():
                native.checkpoint(cancellation)
                session=_NativeSession(); session.acquire(prototype_shape,lambda value:None)
                child=CadDocument._from_backend(manifest=document.manifest,
                    backend_state=_State(session,prototype_shape,references=state.references[pid]),
                    close_backend_state=_close,owner_thread_id=threading.get_ident())
                try:
                    mesh=self.tessellate(child,options=options,cancellation=cancellation)[0]
                    output.append(replace(mesh,prototype_id=pid,local_bounds_m=native.bounds(prototype_shape)))
                finally: child.close()
            return tuple(output)
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRep import BRep_Tool
        from OCP.TopoDS import TopoDS
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopAbs import TopAbs_REVERSED
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GCPnts import GCPnts_QuasiUniformDeflection
        shape = document_shape(document)
        native.checkpoint(cancellation)
        mesh = BRepMesh_IncrementalMesh(shape,options.linear_deflection,options.relative_deflection,options.angular_deflection,options.parallel)
        if not mesh.IsDone(): native.fail('OCCT meshing failed','cad.tessellation.failed')
        positions, triangles, owners, offsets = [], [], [], [0]
        did = document.manifest.document_id
        faces = native.shape_map(shape,'face')
        for i in range(1,faces.Extent()+1):
            native.checkpoint(cancellation)
            face = TopoDS.Face_s(faces.FindKey(i))
            location = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(face,location)
            if tri is None or tri.NbTriangles() == 0: native.fail('a face has no tessellation','cad.tessellation.failed')
            base = len(positions)
            for j in range(1,tri.NbNodes()+1):
                p = tri.Node(j).Transformed(location.Transformation())
                positions.append((p.X(),p.Y(),p.Z()))
            for j in range(1,tri.NbTriangles()+1):
                a,b,c = tri.Triangle(j).Get()
                if face.Orientation() == TopAbs_REVERSED: b,c = c,b
                triangles.append((base+a-1,base+b-1,base+c-1))
            owners.append(state.references['face'][i] if state.references else CadEntityRef(did,'face',i)); offsets.append(len(triangles))
        edge_indices,edge_owners,edge_offsets = [],[],[0]
        if options.include_edges:
            edges = native.shape_map(shape,'edge')
            for i in range(1,edges.Extent()+1):
                native.checkpoint(cancellation)
                edge = TopoDS.Edge_s(edges.FindKey(i))
                if BRep_Tool.Degenerated_s(edge): continue
                sampler = GCPnts_QuasiUniformDeflection(BRepAdaptor_Curve(edge),options.linear_deflection)
                if not sampler.IsDone() or sampler.NbPoints()<2: native.fail('edge tessellation failed','cad.tessellation.failed')
                base = len(positions)
                for j in range(1,sampler.NbPoints()+1):
                    p = sampler.Value(j); positions.append((p.X(),p.Y(),p.Z()))
                edge_indices.extend((base+j,base+j+1) for j in range(sampler.NbPoints()-1))
                edge_owners.append(state.references['edge'][i] if state.references else CadEntityRef(did,'edge',i)); edge_offsets.append(len(edge_indices))
        xyz = np.asarray(positions,dtype=np.float64).reshape((-1,3))
        indices = np.asarray(triangles,dtype=np.int64).reshape((-1,3))
        normals = None
        if options.generate_normals:
            normals = np.zeros_like(xyz)
            if len(indices):
                cross = np.cross(xyz[indices[:,1]]-xyz[indices[:,0]],xyz[indices[:,2]]-xyz[indices[:,0]])
                for k in range(3): np.add.at(normals,indices[:,k],cross)
                lengths = np.linalg.norm(normals,axis=1)
                normals[lengths>0] /= lengths[lengths>0,None]
        precision = 'float32' if options.precision_policy == 'float32' else 'float64'
        result = CadTessellation(np.zeros(3),xyz,indices,normals,tuple(owners),np.asarray(offsets),
            np.asarray(edge_indices).reshape((-1,2)) if options.include_edges else None,
            tuple(edge_owners),np.asarray(edge_offsets),precision)
        native.checkpoint(cancellation)
        return (CadPrototypeMesh(1,result,document.manifest.world_bounds_m),)

    def translate(self, document, destination_temporary, *, options, cancellation=None):
        if options.heal: native.fail('healing is not implemented','cad.healing.unsupported')
        shape = document_shape(document); m = document.manifest
        fmt = options.target_format or native.format_for(destination_temporary)
        unit = options.target_length_unit or m.source_length_unit
        state=document._backend_state_for('occt')
        if fmt=='step' and state.xde_document is not None:
            from ._xde import write_document
            write_document(state.xde_document,destination_temporary,unit,cancellation)
        else: native.write_shape(shape,destination_temporary,fmt,unit,cancellation)
        return CadAssetWriteReport(source_document_id=m.document_id,
            mode='translate',source_format=m.source_format,target_format=fmt,
            source_length_unit=m.source_length_unit,target_length_unit=unit,backend_id='occt',backend_version=VERSION,
            backend_compatibility_version=1,binding_version=m.binding_version,occt_version=m.occt_version,
            output_sha256=native.digest(destination_temporary),byte_identical=False,
            source_topology_counts=m.topology_counts,output_topology_counts=native.counts(shape),
            healing_applied=False,geometry_changed=False,exported_entities=tuple(r.cad_ref for r in m.shapes),
            unsupported_entities=(),approximations=(),metadata_losses=('assembly hierarchy, names, colours and layers',),
            diagnostics=(),execution_mode='provider_translation')

_BACKEND = _OcctBackend()
def get_backend():
    return _BACKEND
