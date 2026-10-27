"""Explicit CAD product affiliation for nonstructural reference geometry."""
from ._geometry import refuse

KEY='anyfileio.cad_reference_geometry'
PREFIX='anyfileio.cad_reference_geometry.v1/'


def capture(model,references,*,part_id,document_id,occurrence_id,prototype_id):
    """Create a public group while native occurrence membership is known."""
    members=tuple(sorted(set(references),key=lambda r:(r.kind,r.id)))
    if not members: return {}
    name=PREFIX+str(occurrence_id)
    if name in model.groups:
        refuse('Reference geometry group already exists','geometry.reference_geometry.ambiguous')
    model.add_to_group(name,members)
    return {KEY:{'version':1,'model_id':str(model.model_id),'part_id':part_id,'group':name,
        'members':tuple((r.kind,r.id) for r in members),'source_document_id':document_id,
        'source_occurrence_id':occurrence_id,'source_prototype_id':prototype_id}}


def affiliations(model,cancellation=None):
    """Validate exact, model-bound active references; never follow replacements."""
    from . import _native as native
    from anyfileio.cad import CadEntityRef
    result={}; claimed=set(); groups=set()
    for part in model.parts.values():
        native.checkpoint(cancellation)
        value=part.metadata.get(KEY)
        if value is None: continue
        def invalid(message): refuse(message,'geometry.reference_geometry.invalid')
        if not hasattr(value,'get') or type(value.get('version')) is not int or value.get('version')!=1:
            invalid('Unsupported CAD reference geometry provenance version')
        if set(value)!={'version','model_id','part_id','group','members','source_document_id','source_occurrence_id','source_prototype_id'}:
            invalid('Malformed CAD reference geometry provenance fields')
        if type(value.get('part_id')) is not int or value.get('part_id')!=part.id:
            invalid('CAD reference geometry provenance belongs to another Part')
        if value.get('model_id')!=str(model.model_id):
            invalid('CAD reference geometry provenance belongs to another model')
        name=value.get('group')
        if not isinstance(name,str) or not name.startswith(PREFIX) or name not in model.groups or name in groups:
            invalid('CAD reference geometry group is missing or ambiguous')
        groups.add(name)
        try:
            for kind,field in (('occurrence','source_occurrence_id'),('prototype','source_prototype_id')):
                if type(value[field]) is not int: invalid('Malformed source CAD affiliation identity')
                CadEntityRef(value['source_document_id'],kind,value[field])
            if name!=PREFIX+str(value['source_occurrence_id']):
                invalid('CAD reference geometry group does not match its source occurrence')
            expected=tuple(tuple(item) for item in value['members'])
            if any(len(item)!=2 or item[0] not in ('vertex','edge') or type(item[1]) is not int or item[1]<=0 for item in expected):
                invalid('Malformed CAD reference geometry member identity')
            refs=model.group(name,resolve=False)
            actual=tuple((r.kind,r.id) for r in refs)
            if not expected or actual!=expected or len(set(expected))!=len(expected):
                invalid('CAD reference geometry membership was changed')
            for ref in refs:
                native.checkpoint(cancellation)
                if ref.kind not in ('vertex','edge') or ref in claimed:
                    invalid('CAD reference geometry has unsupported or duplicate affiliation')
                if model.resolve_ref(ref)!=(ref,):
                    invalid('CAD reference geometry was replaced or deleted')
                model.entity_ref(ref.kind,ref.id)
                claimed.add(ref)
        except (KeyError,TypeError,ValueError) as error:
            invalid(f'Malformed CAD reference geometry provenance: {error}')
        result[part.id]=refs
    orphaned={name for name in model.groups if name.startswith(PREFIX)}-groups
    if orphaned:
        refuse('CAD reference geometry group has no owning product','geometry.reference_geometry.invalid')
    return result
