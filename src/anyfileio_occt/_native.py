"""Native shape I/O. All OCCT imports are deliberately operation-local."""
from __future__ import annotations

from pathlib import Path
import hashlib
import math
from contextlib import contextmanager
from functools import wraps
import sys
import tempfile

from anyfileio.cad import CadOperationError, CadOperationCancelled
from ._binding import _load_binding
from ._locking import _global_settings, _SettingBinding
from ._units import _CANONICAL_SCALES, _resolve_units

UNIT_NAMES = {'um': 'UM', 'mm': 'MM', 'cm': 'CM', 'm': 'M', 'km': 'KM', 'in': 'INCH', 'ft': 'FT'}

@contextmanager
def _message_guard():
    from OCP.Message import Message,Message_PrinterOStream,Message_Warning
    messenger=Message.DefaultMessenger_s()
    def current():
        printers=messenger.Printers()
        return tuple(printers.Value(i) for i in range(1,printers.Length()+1))
    def apply(printers):
        for printer in current():
            if not messenger.RemovePrinter(printer): fail('OCCT printer removal failed','cad.settings.invalid')
        for printer in printers:
            if not messenger.AddPrinter(printer): fail('OCCT printer installation failed','cad.settings.invalid')
    with tempfile.TemporaryDirectory(prefix='anyfileio-occt-messages-') as folder:
        path=Path(folder)/'native.log'
        printer=Message_PrinterOStream(str(path),False,Message_Warning)
        binding=_SettingBinding('occt.message.printers',current,apply)
        try:
            with _global_settings((binding,),{binding.name:(printer,)}): yield
        finally:
            del printer
            if path.exists():
                messages=path.read_text(encoding='utf-8',errors='replace')
                if messages: sys.stderr.write(messages)

def quiet_native(function):
    @wraps(function)
    def call(*args,**kwargs):
        _load_binding()
        with _message_guard(): return function(*args,**kwargs)
    return call


def checkpoint(cancellation):
    if cancellation is not None and cancellation():
        raise CadOperationCancelled('CAD operation cancelled')


def fail(message, code='cad.operation.failed'):
    raise CadOperationError(message, code=code)


def format_for(path):
    return {'.stp': 'step', '.step': 'step', '.igs': 'iges', '.iges': 'iges', '.brep': 'brep'}[Path(path).suffix.lower()]


def settings(values, cancellation=None):
    from OCP.Interface import Interface_Static
    bindings = tuple(_SettingBinding(k,
        lambda k=k: Interface_Static.CVal_s(k),
        lambda value, k=k: _set_string(Interface_Static, k, value)) for k in values)
    return _global_settings(bindings, values, cancellation=cancellation)


def _set_string(api, key, value):
    if not api.SetCVal_s(key, str(value)):
        fail(f'OCCT rejected global setting {key}', 'cad.settings.invalid')


def scaled(shape, scale):
    if scale == 1.0:
        return shape
    from OCP.gp import gp_Trsf, gp_Pnt
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    tr = gp_Trsf()
    tr.SetScale(gp_Pnt(0, 0, 0), scale)
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def _unit_name(name):
    normalized = str(name).strip().lower()
    aliases = {'millimetre': 'mm', 'millimeter': 'mm', 'metre': 'm', 'meter': 'm',
               'centimetre': 'cm', 'centimeter': 'cm', 'inch': 'in', 'foot': 'ft',
               'micrometre': 'um', 'micrometer': 'um', 'kilometre': 'km', 'kilometer': 'km'}
    return aliases.get(normalized, normalized if normalized in _CANONICAL_SCALES else None)


@quiet_native
def read_shape(path, fmt, override=None, cancellation=None, *, raw_coordinates=False):
    _load_binding()
    checkpoint(cancellation)
    from OCP.IFSelect import IFSelect_RetDone
    if fmt == 'step':
        from OCP.STEPControl import STEPControl_Reader
        from OCP.TColStd import TColStd_SequenceOfAsciiString
        reader = STEPControl_Reader()
        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            fail('STEP reader could not parse the source', 'cad.read.failed')
        lengths, angles, solids = (TColStd_SequenceOfAsciiString() for _ in range(3))
        reader.FileUnits(lengths, angles, solids)
        units = {_unit_name(lengths.Value(i).ToCString()) for i in range(1, lengths.Length()+1)}
        if len(units) != 1 or None in units:
            fail('STEP requires one recognized source length unit', 'cad.units.unsupported')
        unit = units.pop()
        try:
            decision = _resolve_units(unit, override)
        except ValueError as error:
            fail(str(error), 'cad.units.conflict')
        # OCCT system length unit is measured in millimetres; transfer directly to metres.
        reader.SetSystemLengthUnit(_CANONICAL_SCALES[decision.effective_unit]*1000.0 if raw_coordinates else 1000.0)
        checkpoint(cancellation)
        if reader.TransferRoots() == 0:
            fail('STEP source contains no transferable roots', 'cad.read.empty')
        shape = reader.OneShape()
    elif fmt == 'iges':
        from OCP.IGESControl import IGESControl_Reader
        reader = IGESControl_Reader()
        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            fail('IGES reader could not parse the source', 'cad.read.failed')
        unit = _unit_name(reader.IGESModel().GlobalSection().UnitName().ToCString())
        try:
            decision = _resolve_units(unit, override)
        except ValueError as error:
            fail(str(error), 'cad.units.conflict')
        if decision.source_to_metre_scale is None:
            fail('IGES source units are unknown; supply an override', 'cad.units.required')
        # IGES ReadFile captures the model's CASCADE unit before the transfer
        # guard. Set the per-reader model explicitly; changing only the global
        # parameter at TransferRoots does not change these stored units.
        if decision.override_supplied_missing:
            fail('Unknown IGES header units need a proven header override decoder', 'cad.units.override_unsupported')
        section=reader.IGESModel().ChangeGlobalSection()
        cascade=1000.0*(_CANONICAL_SCALES[decision.effective_unit] if raw_coordinates else 1.0)
        with settings({'xstep.cascade.unit': UNIT_NAMES[decision.effective_unit] if raw_coordinates else 'M'}, cancellation):
            section.SetCascadeUnit(cascade)
            if section.CascadeUnit()!=cascade:
                fail('IGES reader did not adopt the requested coordinate unit','cad.units.ineffective')
            # UnitValue is source millimetres divided by CASCADE millimetres;
            # it changes when SetCascadeUnit changes the coordinate system.
            expected=1000.0*_CANONICAL_SCALES[decision.effective_unit]/cascade
            if section.UnitValue()!=expected:
                fail('IGES unit name and numeric header unit disagree','cad.units.inconsistent')
            if reader.TransferRoots() == 0:
                fail('IGES source contains no transferable roots', 'cad.read.empty')
            shape = reader.OneShape()
    elif fmt == 'brep':
        from OCP.BRep import BRep_Builder
        from OCP.BRepTools import BRepTools
        from OCP.TopoDS import TopoDS_Shape
        decision = _resolve_units(None, override)
        if decision.source_to_metre_scale is None:
            fail('BREP has no unit declaration; supply source_length_unit_override', 'cad.units.required')
        shape = TopoDS_Shape()
        if not BRepTools.Read_s(shape, str(path), BRep_Builder()):
            fail('BREP reader could not parse the source', 'cad.read.failed')
        if not raw_coordinates: shape = scaled(shape, decision.source_to_metre_scale)
    else:
        fail('unsupported native format', 'cad.format.unsupported')
    checkpoint(cancellation)
    if shape.IsNull():
        fail('source has no shape', 'cad.read.empty')
    return shape, decision


@quiet_native
def read_brep_retained(path,override=None,cancellation=None):
    """Guarded foreign/native BREP read, with retained records when available."""
    from ._association import Decoded,scale
    from anyfileio.geometry import GeometryInterchangeError
    checkpoint(cancellation)
    try:data=Path(path).read_bytes()
    except OSError as error:fail(f'BREP input could not be read: {error}','cad.read.failed')
    checkpoint(cancellation)
    records=None
    try:records=Decoded(data,cancellation)
    except GeometryInterchangeError as error:
        if error.code!='geometry.association_unproved':raise
    if records is None:
        raw,decision=read_shape(path,'brep',override,cancellation,raw_coordinates=True)
    else:
        decision=_resolve_units(None,override)
        if decision.source_to_metre_scale is None:fail('BREP has no unit declaration; supply source_length_unit_override','cad.units.required')
        raw=records.shape
    checkpoint(cancellation)
    try:normalization=scale(raw,decision.source_to_metre_scale)
    except Exception as error:fail(f'BREP normalization failed: {error}','cad.read.failed')
    checkpoint(cancellation)
    return raw,decision,records,normalization


@quiet_native
def write_shape(shape, path, fmt, unit='m', cancellation=None):
    _load_binding()
    checkpoint(cancellation)
    if unit not in UNIT_NAMES:
        fail('unsupported output length unit', 'cad.units.unsupported')
    if fmt == 'step':
        from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
        from OCP.IFSelect import IFSelect_RetDone
        writer = STEPControl_Writer()  # initializes STEP global parameters before guard
        with settings({'write.step.unit': UNIT_NAMES[unit], 'xstep.cascade.unit': 'M'}, cancellation):
            if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
                fail('STEP shape transfer failed', 'cad.write.failed')
            checkpoint(cancellation)
            if writer.Write(str(path)) != IFSelect_RetDone:
                fail('STEP write failed', 'cad.write.failed')
    elif fmt == 'iges':
        from OCP.IGESControl import IGESControl_Writer,IGESControl_Controller
        from OCP.IGESData import IGESData_IGESWriter
        import io
        # Register parameters before the reversible unit guard snapshots them.
        # The enclosing messenger guard already holds the backend global lock.
        IGESControl_Controller.Init_s()
        controller=IGESControl_Controller()
        with settings({'xstep.cascade.unit': 'M'}, cancellation):
            writer = IGESControl_Writer(UNIT_NAMES[unit], 1)
            # AddShape consumes canonical-metre native coordinates. The model
            # captures its own CASCADE unit independently of the global guard.
            section=writer.Model().ChangeGlobalSection()
            section.SetCascadeUnit(1000.0)
            if section.CascadeUnit()!=1000.0 or section.UnitValue()!=_CANONICAL_SCALES[unit]:
                fail('IGES writer model did not adopt metre input coordinates','cad.units.ineffective')
            if not writer.AddShape(shape):
                fail('IGES shape transfer failed', 'cad.write.failed')
            writer.ComputeModel()
            # IGESControl_Writer.Write uses the default short FloatWriter format.
            # Format locally before SendModel; 17 significant digits preserve
            # binary64 coefficients without changing any geometric tolerance.
            serializer=IGESData_IGESWriter(writer.Model())
            serializer.FloatWriter().SetFormat('%.16E',True)
            serializer.SendModel(controller.Protocol())
            checkpoint(cancellation)
            stream=io.BytesIO()
            if not serializer.Print(stream):
                fail('IGES write failed', 'cad.write.failed')
            checkpoint(cancellation)
            Path(path).write_bytes(stream.getvalue())
    elif fmt == 'brep':
        from OCP.BRepTools import BRepTools
        from ._association import current_writer,Capsule
        snapshot=current_writer()
        if snapshot is not None:
            capsule=Capsule(shape,unit,snapshot)
            checkpoint(cancellation)
            Path(path).write_bytes(capsule.payload)
            checkpoint(cancellation)
            return capsule
        if not BRepTools.Write_s(scaled(shape, 1.0 / _CANONICAL_SCALES[unit]), str(path)):
            fail('BREP write failed', 'cad.write.failed')
    else:
        fail('unsupported output format', 'cad.format.unsupported')
    checkpoint(cancellation)


def shape_map(shape, kind):
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.TopExp import TopExp
    from OCP import TopAbs
    result = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, getattr(TopAbs, 'TopAbs_' + kind.upper()), result)
    return result


def counts(shape):
    return {kind: shape_map(shape, kind).Extent() for kind in ('solid', 'shell', 'face', 'wire', 'edge', 'vertex')}


def bounds(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if box.IsVoid():
        return None
    value = box.Get()
    return tuple(value)


def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
