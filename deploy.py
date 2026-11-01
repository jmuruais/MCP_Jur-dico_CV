"""Despliegue local sobre una instalación existente. No imprime configuración ni secretos."""
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

BASE = Path('/opt/mcp-juridico')
STAGE = Path(__file__).resolve().parent
DROP = Path('/etc/systemd/system/tunnel-client.service.d/50-juridico-hardening.conf')
FILES = ['server.py', 'juridico.py', 'pdf_extract.py', 'smoke_mcp.py',
         'OPERACIONES.md', 'tunnel-client-hardening.conf', 'deploy.py']


def command(*args):
    r = subprocess.run(args, capture_output=True, text=True, timeout=35)
    if r.returncode:
        raise RuntimeError('Falló la operación: '+args[0])
    return r


def fingerprint():
    paths = [Path('/etc/systemd/system/tunnel-client.service')]
    paths += sorted(Path('/etc/mcp-juridico').rglob('*'))
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}


def ready():
    for _ in range(20):
        try:
            with urlopen('http://127.0.0.1:18989/readyz', timeout=2) as r:
                if r.status == 200 and r.read(100).strip() == b'ready':
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main():
    if os.geteuid() != 0 or not (BASE/'.venv/bin/python').exists():
        raise RuntimeError('Ejecutar como root en la instalación existente de /opt/mcp-juridico.')
    checked = json.loads((STAGE/'smoke-results.json').read_text())
    if not checked.get('passed') or not checked.get('tested_hashes'):
        raise RuntimeError('No hay pruebas MCP satisfactorias en staging.')
    if any(hashlib.sha256((STAGE/name).read_bytes()).hexdigest() != digest
           for name,digest in checked['tested_hashes'].items()):
        raise RuntimeError('El código ha cambiado después de las pruebas MCP; repetirlas antes de desplegar.')
    os.umask(0o077)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path('/var/backups/mcp-juridico')/stamp
    backup.mkdir(mode=0o700, parents=True)
    old_source = (BASE/'server.py').read_bytes()
    (backup/'server.py.original').write_bytes(old_source)
    old_current = os.readlink(BASE/'current') if (BASE/'current').is_symlink() else None
    if (BASE/'current').exists() and old_current is None:
        raise RuntimeError('current ya existe y no es enlace; revisar antes de desplegar.')
    old_drop = DROP.read_bytes() if DROP.exists() else None
    if old_drop is not None:
        (backup/'hardening.original').write_bytes(old_drop)
    with tarfile.open(backup/'configuracion-original.tar.gz', 'w:gz') as t:
        for p in ['/etc/systemd/system/tunnel-client.service', '/etc/mcp-juridico']:
            t.add(p, arcname=p.lstrip('/'))
    original_fingerprint = fingerprint()
    metadata = {'backup': str(backup), 'release': str(BASE/'releases'/stamp),
                'old_current': old_current, 'old_drop': old_drop is not None}
    (backup/'manifest.json').write_text(json.dumps(metadata, indent=2))
    rollback = '''import json,os,subprocess
from pathlib import Path
b=Path(__file__).resolve().parent
m=json.loads((b/'manifest.json').read_text())
base=Path('/opt/mcp-juridico')
p=base/'server.py.restore'
p.write_bytes((b/'server.py.original').read_bytes());p.chmod(0o644);os.replace(p,base/'server.py')
c=base/'current'
if c.is_symlink(): c.unlink()
if m['old_current'] is not None: c.symlink_to(m['old_current'])
d=Path('/etc/systemd/system/tunnel-client.service.d/50-juridico-hardening.conf')
if m['old_drop']:
 d.write_bytes((b/'hardening.original').read_bytes());d.chmod(0o644)
elif d.exists(): d.unlink()
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','restart','tunnel-client'],check=True)
print('Restaurada la versión anterior; comprobar readyz y una consulta MCP.')
'''
    (backup/'rollback.py').write_text(rollback)
    release = Path(metadata['release'])
    release.mkdir(mode=0o755, parents=True)
    release.chmod(0o755)
    (BASE/'releases').chmod(0o755)
    for name in FILES:
        shutil.copyfile(STAGE/name, release/name)
        (release/name).chmod(0o644)
    shutil.copytree(STAGE/'tests', release/'tests', ignore=shutil.ignore_patterns('__pycache__'))
    for p in (release/'tests').rglob('*'):
        p.chmod(0o755 if p.is_dir() else 0o644)
    (release/'tests').chmod(0o755)
    (release/'requirements.lock').write_text(command(str(BASE/'.venv/bin/pip'), 'freeze').stdout)
    (release/'requirements.lock').chmod(0o644)
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in release.iterdir() if p.is_file()}
    (release/'SHA256SUMS.json').write_text(json.dumps(hashes, indent=2))
    (release/'SHA256SUMS.json').chmod(0o644)
    # Ambas conmutaciones se hacen mediante rename en el mismo sistema de archivos.
    try:
        next_link = BASE/'current.next'
        next_link.symlink_to(release)
        os.replace(next_link, BASE/'current')
        wrapper = BASE/'server.py.next'
        wrapper.write_text('from pathlib import Path\nimport runpy,sys\np=Path(__file__).resolve().parent/"current"\nsys.path.insert(0,str(p))\nrunpy.run_path(str(p/"server.py"),run_name="__main__")\n')
        wrapper.chmod(0o644)
        os.replace(wrapper, BASE/'server.py')
        DROP.parent.mkdir(mode=0o755, exist_ok=True)
        shutil.copyfile(release/'tunnel-client-hardening.conf', DROP)
        DROP.chmod(0o644)
        if fingerprint() != original_fingerprint:
            raise RuntimeError('La configuración o identidad original del túnel cambió inesperadamente.')
        command('systemctl', 'daemon-reload')
        command('systemctl', 'restart', 'tunnel-client')
        if not ready():
            raise RuntimeError('El túnel no pasó readyz después del despliegue.')
        if command('systemctl', 'is-active', 'tunnel-client').stdout.strip() != 'active':
            raise RuntimeError('El servicio no está activo.')
        report = {**metadata, 'readyz': True, 'configuracion_tunel_inalterada': True,
                  'desplegado_en': datetime.now(timezone.utc).isoformat()}
        (backup/'deployment.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, ensure_ascii=False))
    except Exception:
        subprocess.run(['/usr/bin/python3', str(backup/'rollback.py')], check=True)
        raise


if __name__ == '__main__':
    main()
