# Reproducir el smoke del wheel: ODF output

Desde el checkout del SHA de código indicado en [el recibo](health.json), con el backend de build ya instalado, usar destinos nuevos:

```sh
python -m build --wheel --no-isolation --outdir /var/tmp/deidflow-wheel-review-dist
python -m venv /var/tmp/deidflow-wheel-review
/var/tmp/deidflow-wheel-review/bin/python -m pip install --no-index --no-cache-dir /var/tmp/deidflow-wheel-review-dist/*.whl
cd /var/tmp
/var/tmp/deidflow-wheel-review/bin/python -I - output <<'PY'
import base64
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import deidflow
from deidflow import DeidEngine, Policy
from deidflow.benchmarks.runner import offline_network

assert '/workspace/' not in str(Path(deidflow.__file__).resolve())
NS='urn:oasis:names:tc:opendocument:xmlns:'
DECL=' '.join(f'xmlns:{name}="{NS}{name}:1.0"' for name in ('office','text','table','config','draw'))
SECRET='synthetic.patient@example.test'

def package(root, name, suffix, body, settings=None):
    media='application/vnd.oasis.opendocument.'+('text' if suffix=='.odt' else 'spreadsheet')
    content=f'<office:document-content {DECL} office:version="1.3"><office:body>{body}</office:body></office:document-content>'
    parts={'content.xml':content}
    if settings is not None:
        parts['settings.xml']=settings
    entries=''.join(f'<manifest:file-entry manifest:full-path="{p}" manifest:media-type="text/xml"/>' for p in parts)
    manifest=f'<manifest:manifest xmlns:manifest="{NS}manifest:1.0" manifest:version="1.3"><manifest:file-entry manifest:full-path="/" manifest:media-type="{media}"/>{entries}</manifest:manifest>'
    path=root/(name+suffix)
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('mimetype',media)
        for part,data in parts.items():
            archive.writestr(part,data)
        archive.writestr('META-INF/manifest.xml',manifest)
    return path

with TemporaryDirectory(dir='/var/tmp') as temporary, offline_network() as network:
    root=Path(temporary);engine=DeidEngine(country='ES');policy=Policy.strict(require_ner=False)
    clean=package(root,'clean','.odt','<office:text><text:p>Informe.</text:p></office:text>')
    assert engine.read(clean).complete
    assert engine.verify(clean,policy=policy).status=='APPROVED'
    encoded=base64.b64encode(SECRET.encode('utf-16-le')).decode()
    settings=f'<office:document-settings {DECL}><office:settings><config:config-item config:name="PrinterSetup" config:type="base64Binary">{encoded}</config:config-item></office:settings></office:document-settings>'
    opaque=package(root,'opaque','.odt','<office:text><text:p>Informe.</text:p></office:text>',settings=settings)
    assert not engine.read(opaque).complete
    assert engine.verify(opaque,policy=policy).status=='BLOCKED'
    sheet=package(root,'sheet','.ods',f'<office:spreadsheet><table:table table:name="Datos"><table:table-row><table:table-cell office:value-type="string"><text:p>Correo</text:p></table:table-cell></table:table-row><table:table-row><table:table-cell office:value-type="string"><text:p>{SECRET}</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet>')
    if sys.argv[1]=='reader':
        for source in (clean,sheet):
            target=source.with_stem(source.stem+'-out')
            result=engine.deidentify(source,output=target,policy=policy)
            assert result.status=='UNSUPPORTED' and result.output_path is None and not target.exists()
    elif sys.argv[1]=='output':
        sanitized=engine.deidentify(opaque,output=root/'sanitized.odt',policy=policy)
        assert sanitized.status=='APPROVED' and engine.verify(sanitized.output_path,policy=policy).status=='APPROVED'
        result=engine.deidentify(sheet,output=root/'safe.ods',policy=policy)
        assert result.status=='REVIEW_REQUIRED'
        with zipfile.ZipFile(result.output_path) as archive:
            assert SECRET.encode() not in archive.read('content.xml')
    else:
        raise AssertionError('Unknown probe')
    assert network['attempts']==0
print('ODF',sys.argv[1],'wheel probes passed; network attempts: 0')
PY
```

El bloque se ejecutó también desde stdin con `-I` sobre el wheel aislado medido; [el recibo](health.json) fija el SHA-256 del cuerpo Python. Todo el contenido es ficticio y temporal. El guard de sockets informa cero intentos; no representa aislamiento nativo del sistema operativo. El smoke general de modelos/API sin extras se conserva en `.github/workflows/ci.yml`, job `package`, paso “Smoke-test the wheel without any optional dependency”.
