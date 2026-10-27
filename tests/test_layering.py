"""Static dependency direction and lazy native imports."""
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'src'/'anyfileio_occt'

def test_native_owner_imports_are_operation_local():
    for path in ROOT.glob('*.py'):
        tree=ast.parse(path.read_text())
        for statement in tree.body:
            if isinstance(statement,ast.Import):
                assert not any(a.name.split('.')[0] in {'OCP','anygeometry','cadquery'} for a in statement.names),path
            if isinstance(statement,ast.ImportFrom):
                assert (statement.module or '').split('.')[0] not in {'OCP','anygeometry','cadquery'},path

def test_no_owner_private_imports():
    for path in ROOT.glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.ImportFrom) and (node.module or '').startswith('anygeometry'):
                assert not any(a.name.startswith('_') for a in node.names),path
                assert not any(p.startswith('_') for p in node.module.split('.')[1:]),path
