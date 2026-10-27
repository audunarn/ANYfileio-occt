"""STEP XCAF assembly identities, locations and native document ownership."""
from __future__ import annotations
import numpy as np
from . import _native as native
from ._units import _resolve_units


def name(label):
    from OCP.TDataStd import TDataStd_Name
    attr=TDataStd_Name()
    return str(attr.Get().ToExtString()) if label.FindAttribute(TDataStd_Name.GetID_s(),attr) else ''

def matrix(location):
    tr=location.Transformation(); result=np.eye(4)
    for i in range(3):
        for j in range(4): result[i,j]=tr.Value(i+1,j+1)
    return result

@native.quiet_native
def read(path,override=None,cancellation=None):
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString,TCollection_AsciiString
    from OCP.TDF import TDF_LabelSequence,TDF_Label,TDF_Tool
    from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
    from OCP.TColStd import TColStd_SequenceOfAsciiString
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Compound
    from OCP.BRep import BRep_Builder
    native._load_binding(); native.checkpoint(cancellation)
    reader=STEPCAFControl_Reader()
    if reader.ReadFile(str(path))!=IFSelect_RetDone: native.fail('STEP XCAF read failed','cad.read.failed')
    # OCP 7.9.3 does not register ExternFiles()'s DataMap return type. Inspect
    # the parsed STEP schema before transfer can follow an external dependency.
    model=reader.Reader().StepModel()
    for i in range(1,model.NbEntities()+1):
        native.checkpoint(cancellation)
        kind=model.Value(i).DynamicType().Name()
        if 'Extern' in kind or 'DocumentFile' in kind or 'AppliedDocumentReference' in kind:
            native.fail('External STEP references require retained dependency snapshots and digests','cad.source.external_references_unsupported')
    units,angles,solids=(TColStd_SequenceOfAsciiString() for _ in range(3))
    reader.Reader().FileUnits(units,angles,solids)
    known={native._unit_name(units.Value(i).ToCString()) for i in range(1,units.Length()+1)}
    if len(known)!=1 or None in known: native.fail('STEP requires one recognized length unit','cad.units.unsupported')
    try: decision=_resolve_units(known.pop(),override)
    except ValueError as error: native.fail(str(error),'cad.units.conflict')
    reader.Reader().SetSystemLengthUnit(1000.)
    doc=TDocStd_Document(TCollection_ExtendedString('BinXCAF'))
    XCAFDoc_DocumentTool.SetLengthUnit_s(doc,1.0)
    if not reader.Transfer(doc): native.fail('STEP XCAF transfer failed','cad.read.failed')
    tool=XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()); roots=TDF_LabelSequence(); tool.GetFreeShapes(roots)
    if roots.Length()==0: native.fail('STEP has no free shape','cad.read.empty')
    prototypes={}; occurrences=[]; labels={}; stack=set()
    def entry(label):
        text=TCollection_AsciiString(); TDF_Tool.Entry_s(label,text); return text.ToCString()
    def walk(label,parent=None,accumulated=None):
        native.checkpoint(cancellation)
        referred=TDF_Label(); definition=referred if XCAFDoc_ShapeTool.GetReferredShape_s(label,referred) else label
        key=entry(definition)
        if key in stack: native.fail('STEP assembly has a reference cycle','cad.assembly.cycle')
        if key not in labels:
            pid=len(labels)+1; labels[key]=pid
            sh=XCAFDoc_ShapeTool.GetShape_s(definition)
            if sh.IsNull(): native.fail('STEP contains a null/unconverted product shape','cad.read.incomplete')
            sh=sh.Located(TopLoc_Location())
            assembly=XCAFDoc_ShapeTool.IsAssembly_s(definition)
            if not assembly and not any(native.counts(sh).values()):
                native.fail('STEP contains an empty/unconverted geometric product','cad.read.incomplete')
            prototypes[pid]={'shape':sh,'name':name(definition),'assembly':assembly}
        pid=labels[key]; location=XCAFDoc_ShapeTool.GetLocation_s(label)
        local=matrix(location); world=local if accumulated is None else accumulated@local
        oid=len(occurrences)+1
        occurrences.append({'id':oid,'parent':parent,'prototype':pid,'local':local,'world':world,'name':name(label) or prototypes[pid]['name']})
        if prototypes[pid]['assembly']:
            stack.add(key); components=TDF_LabelSequence(); XCAFDoc_ShapeTool.GetComponents_s(definition,components,False)
            if components.Length()==0: native.fail('STEP assembly has no converted components','cad.read.incomplete')
            for j in range(1,components.Length()+1): walk(components.Value(j),oid,world)
            stack.remove(key)
    for i in range(1,roots.Length()+1): walk(roots.Value(i))
    builder=BRep_Builder(); shape=TopoDS_Compound(); builder.MakeCompound(shape)
    for i in range(1,roots.Length()+1): builder.Add(shape,XCAFDoc_ShapeTool.GetShape_s(roots.Value(i)))
    return shape,decision,doc,prototypes,occurrences


@native.quiet_native
def write_document(document,path,unit='m',cancellation=None):
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone
    writer=STEPCAFControl_Writer()
    with native.settings({'write.step.unit':native.UNIT_NAMES[unit],'xstep.cascade.unit':'M'},cancellation):
        if not writer.Transfer(document,STEPControl_AsIs): native.fail('STEP XCAF transfer failed','cad.write.failed')
        native.checkpoint(cancellation)
        if writer.Write(str(path))!=IFSelect_RetDone: native.fail('STEP XCAF write failed','cad.write.failed')
    native.checkpoint(cancellation)


def write_shape(shape,path,unit='m',cancellation=None):
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    doc=TDocStd_Document(TCollection_ExtendedString('BinXCAF'))
    XCAFDoc_DocumentTool.SetLengthUnit_s(doc,1.0)
    tool=XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    tool.AddShape(shape,True,True)
    tool.UpdateAssemblies()
    write_document(doc,path,unit,cancellation)


def write_groups(groups,path,unit='m',cancellation=None):
    """Write explicit product groups; faces within a product retain shared topology."""
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDataStd import TDataStd_Name
    from OCP.TopLoc import TopLoc_Location
    doc=TDocStd_Document(TCollection_ExtendedString('BinXCAF'))
    XCAFDoc_DocumentTool.SetLengthUnit_s(doc,1.)
    tool=XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()); root=tool.NewShape()
    TDataStd_Name.Set_s(root,TCollection_ExtendedString('ANYgeometry'))
    for label,shape in groups:
        definition=tool.AddShape(shape,False)
        TDataStd_Name.Set_s(definition,TCollection_ExtendedString(label))
        component=tool.AddComponent(root,definition,TopLoc_Location())
        TDataStd_Name.Set_s(component,TCollection_ExtendedString(label))
    tool.UpdateAssemblies(); write_document(doc,path,unit,cancellation)
