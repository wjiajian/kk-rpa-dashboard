"""Opt-in rehearsal of actual application releases in fresh Python environments."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from cryptography.fernet import Fernet
import pytest

from rpa_console.publisher import Publisher, excluded
from rpa_console.publishing import Publishing
from rpa_console.credentials import CredentialStore
from rpa_console.storage import Base, Database, ApplicationSource, ApplicationRelease, ImportJob


@pytest.mark.skipif(os.getenv('RPA_INSTALLATION_TEST') != '1', reason='real dependency installation is opt-in')
def test_two_current_apps_install_with_shared_packages_and_independent_environments(tmp_path, monkeypatch):
    from rpa_console import publisher
    monorepo = Path(os.environ['RPA_MONOREPO_PATH']).resolve()
    monkeypatch.syspath_prepend(str(monorepo / 'packages/rpa-executor/src'))
    from rpa_executor.installer import Installer
    repository = tmp_path / 'fixture-repository'
    repository.mkdir()
    paths = subprocess.check_output(['git', '-C', str(monorepo), 'ls-files', '--cached', '--others', '--exclude-standard', '-z']).decode().split('\0')
    for name in paths:
        if not name or not (name.startswith('apps/') or name.startswith('packages/rpa-core/')):
            continue
        relative = Path(name)
        if excluded(relative) or not (monorepo / relative).is_file():
            continue
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(monorepo / relative, target)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repository), *args], stderr=subprocess.DEVNULL).decode().strip()
    git('init', '--quiet')
    git('add', '.')
    git('-c', 'user.name=Release fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'isolated working-tree fixture')
    commit = git('rev-parse', 'HEAD')
    db = Database('sqlite:///' + str(tmp_path / 'releases.db'))
    Base.metadata.create_all(db.engine)
    service = Publishing(db, CredentialStore(Fernet.generate_key()), tmp_path / 'artifacts')
    source = service.add_source('fixture', 'https://example.invalid/repository.git')
    with db.transaction() as s:
        s.get(ApplicationSource, source['id']).url = str(repository)
    original_environment = publisher.git_environment
    @contextmanager
    def fixture_transport(credentials, directory):
        with original_environment(credentials, directory) as env:
            yield {**env, 'GIT_ALLOW_PROTOCOL': 'file'}
    monkeypatch.setattr(publisher, 'git_environment', fixture_transport)
    imported = service.import_source(source['id'], commit)
    assert Publisher(service).run_once()
    with db.transaction() as s:
        job = s.get(ImportJob, imported['id'])
        assert job.status == 'ready', job.data.get('error')
        previews = job.data['applications']
        assert len(previews) == 2
        assert not any(p.get('error') for p in previews), previews
        archive = service.artifact_dir / job.data['artifact']
    releases = service.confirm(imported['id'], [p['app_id'] for p in previews])
    first = releases[0]
    requirement = repository / first['path'] / 'requirement.md'
    requirement.write_text(requirement.read_text() + '\nRelease fixture revision two.\n')
    git('add', '.')
    git('-c', 'user.name=Release fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'second isolated revision')
    updated = service.import_source(source['id'], git('rev-parse', 'HEAD'))
    assert Publisher(service).run_once()
    releases += service.confirm(updated['id'], [first['app_id']])
    assert releases[-1]['version'] == first['version'] and releases[-1]['commit'] != first['commit']
    with db.transaction() as s:
        archives = {release['id']: service.artifact_dir / s.get(ApplicationRelease, release['id']).data['artifact'] for release in releases}
    installer = Installer(tmp_path / 'installed', 'wss://console.invalid', 'fixture-token')
    monkeypatch.setattr(installer, 'download', lambda release_id, destination: shutil.copyfile(archives[release_id], destination))
    for release in releases:
        reports = []
        async def report(status, stage, error=None):
            reports.append((status, stage, error))
        command = {'job_id': str(uuid4()), 'action': 'install', 'release_id': release['id'],
                   'commit': release['commit'], 'deployment': release, 'artifact_url': release['id']}
        asyncio.run(installer.execute(command, report))
        assert reports[-1][0] == 'installed', (release['app_id'], reports)
        assert [r[1] for r in reports] == ['download', 'extract', 'dependencies', 'doctor', 'test', 'complete']
        deployed = installer.registry[release['id']]
        assert Path(deployed['python']).is_file()
        # The import must resolve inside this release, never the source checkout or another version.
        result = subprocess.check_output([deployed['python'], '-c', 'import rpa_core,json; print(json.dumps(rpa_core.__file__))'], cwd=deployed['cwd'])
        assert Path(json.loads(result)).is_relative_to(installer.root / release['id'])
    assert len({d['python'] for d in installer.registry.values()}) == 3
    assert len(Installer(installer.root, 'wss://console.invalid', 'fixture-token').registry) == 3
    original = installer.registry[first['id']]
    newer = installer.registry[releases[-1]['id']]
    assert 'Release fixture revision two.' not in (Path(original['cwd']) / 'requirement.md').read_text()
    assert 'Release fixture revision two.' in (Path(newer['cwd']) / 'requirement.md').read_text()
    # Selecting the old interpreter after a new install remains usable without reinstalling it.
    subprocess.run([original['python'], '-c', "import importlib,sys; sys.argv=['rpa-app','doctor','--deployment']; raise SystemExit(importlib.import_module(" + repr(first['module'].rsplit('.', 1)[0] + '.cli') + ").main())"],
                   cwd=original['cwd'], check=True, capture_output=True)
