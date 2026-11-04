"""Prepare isolated files from a pinned commit, without checking out or editing app code."""
import json,secrets,subprocess,tarfile
from pathlib import Path

root=Path(__file__).resolve().parents[2]
cfg=json.loads((root/'postman/staging/test-matrix.json').read_text())
out=root/'.runtime/staging-diagnostics';source=out/'source'
source.mkdir(parents=True,exist_ok=True);(out/'evidence').mkdir(exist_ok=True)
env=out/'compose.env'
if not env.exists():env.write_text('DIAG_DB_PASSWORD='+secrets.token_hex(24)+'\n')
subprocess.run(['git','archive','--format=tar','-o',str(out/'source.tar'),cfg['source_commit'],'backend'],cwd=root,check=True)
with tarfile.open(out/'source.tar') as archive:archive.extractall(source,filter='data')
subprocess.run(['docker','build','--tag','ocrlab-staging-diagnostics:67df434',str(source/'backend')],cwd=root,check=True)
print('Prepared pinned source and private local-only DB environment. No production environment read.')
