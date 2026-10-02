"""Management state must be explicit recovery input, never an old absolute fallback."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('backup_dependencies', Path(__file__).with_name('secure-backup.py'))
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def private(path, data=b'{}'):
    path.write_bytes(data)
    path.chmod(0o600)
    return path


def test_management_files_and_separate_admin_are_included(tmp_path):
    tmp_path.chmod(0o700)
    fields = ('profile_directory', 'environment_catalog', 'template_catalog',
              'network_profile_catalog', 'legacy_network_migrations')
    config = {field: str(private(tmp_path / (field + '.json'))) for field in fields}
    private(tmp_path / 'admin.pem', b'private QA identity')
    config['sealskin_admin'] = {'client_private_key_file': 'admin.pem'}
    found = backup.collect_adapter_dependencies(config, tmp_path)
    assert set(found) == {'adapter/dependencies/' + key + '.json' for key in fields} | {'adapter/admin-client-private.pem'}
    assert found['adapter/admin-client-private.pem'].read_bytes() == b'private QA identity'


@pytest.mark.parametrize('case', ['missing', 'symlink', 'public', 'directory'])
def test_unsafe_dependency_is_not_silently_omitted(tmp_path, case):
    tmp_path.chmod(0o700)
    p = tmp_path / 'profiles.json'
    if case == 'symlink':
        p.symlink_to(private(tmp_path / 'other.json'))
    elif case == 'public':
        private(p).chmod(0o644)
    elif case == 'directory':
        p.mkdir()
    with pytest.raises(backup.BackupError):
        backup.collect_adapter_dependencies({'profile_directory': str(p)}, tmp_path)


def test_legacy_config_remains_supported(tmp_path):
    assert backup.collect_adapter_dependencies({}, tmp_path) == {}
