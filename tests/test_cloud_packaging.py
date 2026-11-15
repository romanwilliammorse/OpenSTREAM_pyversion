"""The transferred worker must be a real installed distribution for exports."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

from openstream.cloud.gateway import PACKAGE, source_bundle


def test_transferred_package_installs_metadata_without_changing_source(tmp_path):
    source, installed = tmp_path/'source', tmp_path/'installed'
    with zipfile.ZipFile(io.BytesIO(source_bundle())) as archive:
        archive.extractall(source)
    result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps',
                             '--no-build-isolation', '--target', str(installed), str(source)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    script = """import sys,json,importlib.metadata as m
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import openstream
d=m.distribution('openstream-python')
print(json.dumps({'version':d.version,'module':openstream.__version__,
 'installed':str(d.locate_file('openstream/__init__.py'))}))
"""
    verified = subprocess.run([sys.executable, '-c', script, str(installed)],
                              capture_output=True, text=True, check=True)
    value = json.loads(verified.stdout)
    assert value['version'] == value['module']
    assert Path(value['installed']).resolve().is_relative_to(installed.resolve())
    for path in PACKAGE.glob('*.py'):
        assert hashlib.sha256((installed/'openstream'/path.name).read_bytes()).digest() == hashlib.sha256(path.read_bytes()).digest()
