"""Canonical references composed from the SAME proved literal association."""
from . import _native as native
from ._geometry import refuse


def reconcile(model,source,path,fmt,unit,source_scale,source_entities,parts,scene_groups,work,cancellation=None,*,association=None):
    from anyfileio.geometry import GeometryWriteReport,GeometryDiagnostic
    from OCP.TopAbs import TopAbs_COMPOUND
    from ._topology import _children
    if 'output_document_id' not in GeometryWriteReport.__dataclass_fields__:
        refuse('Core cannot report actual-file CAD identity','geometry.core.capability_missing')
    if fmt!='brep' or association is None:
        refuse('Canonical references require proved native file-record lineage','geometry.association_unproved')
    manifest=association.document.manifest;result={};claimed={};diagnostics=[];losses=[]
    if manifest.source_sha256!=association.sha256:
        refuse('Canonical document is not the frozen native payload','geometry.association.payload_changed')
    for handle,shapes in source_entities.items():
        values=[]
        for shape in shapes:
            work.charge();reference=association.reference(association.canonical(shape))
            if reference in claimed and claimed[reference]!=handle:
                refuse('Distinct owner entities alias one canonical record','geometry.output.occurrence_unsupported')
            claimed[reference]=handle
            if reference not in values:values.append(reference)
        if not values:refuse('Source entity has no file records','geometry.output.references_missing')
        result[handle]=tuple(values)
    for handle,shape in parts:
        carriers=[]
        def closure(value):
            work.charge()
            if value.ShapeType()==TopAbs_COMPOUND:
                for child in _children(value,work):closure(child)
            else:carriers.append(association.reference(value))
        closure(association.canonical(shape))
        if not carriers:refuse('Part carrier closure is not addressable','geometry.output.references_missing')
        result[handle]=tuple(carriers)
        diagnostics.append(GeometryDiagnostic('geometry.cad.part_carrier_closure',
            'Part mapping is the verified BREP carrier closure; its compound container has no manifest-addressable identity',(handle,)))
        losses.append('BREP Part compound identity is not manifest-addressable; mapped verified carrier closure')
    if native.digest(path)!=association.sha256:refuse('Written BREP changed after association','geometry.association.payload_changed')
    return manifest.document_id,result,tuple(diagnostics),tuple(dict.fromkeys(losses)),association.sha256
