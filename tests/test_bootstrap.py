"""Provider discovery remains lazy and capability claims remain explicit."""
import inspect
import os
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT=Path(__file__).resolve().parents[1]

def test_metadata_contract():
    with (ROOT/'pyproject.toml').open('rb') as stream: project=tomllib.load(stream)['project']
    assert 'ANYfileio>=0.3.2,<0.4' in project['dependencies']
    assert project['optional-dependencies']['geometry']==['ANYgeometry>=0.4.7,<0.5']
    assert project['entry-points']['anyfileio.backends']['occt']=='anyfileio_occt.backend:get_backend'

def test_factory_identity_and_honest_capabilities():
    from anyfileio_occt.backend import get_backend
    b=get_backend()
    assert b is get_backend()
    assert (b.backend_id,b.protocol_version,b.backend_compatibility_version)==('occt',1,1)
    assert b.capabilities.read_formats==frozenset({'step','iges','brep'})
    assert b.capabilities.write_formats==frozenset({'step','iges','brep'})
    assert b.capabilities.tessellate and b.capabilities.translate
    assert b.capabilities.assembly

def test_protocol_call_shapes():
    from anyfileio_occt.backend import get_backend
    b=get_backend()
    for name,required in {'read':('source_snapshot','source_sha256','source_name','options','tessellation_options','cancellation'),
        'tessellate':('document','options','cancellation'),
        'translate':('document','destination_temporary','options','cancellation')}.items():
        assert tuple(inspect.signature(getattr(b,name)).parameters)==required

def test_native_and_owner_imports_are_lazy():
    env=dict(os.environ)
    env['PYTHONPATH']=os.pathsep.join([str(ROOT/'src'),str(ROOT.parent/'ANYfileIO'/'src')])
    code='''
import importlib.abc,sys
class Blocker(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'OCP','anygeometry','cadquery'}: raise AssertionError(fullname)
sys.meta_path.insert(0,Blocker())
from anyfileio_occt.backend import get_backend
import anyfileio_occt.geometry_export,anyfileio_occt.geometry_import
assert get_backend().protocol_version==1
assert not any(n.split('.')[0] in {'OCP','anygeometry','cadquery'} for n in sys.modules)
'''
    p=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=20)
    assert p.returncode==0,p.stderr
