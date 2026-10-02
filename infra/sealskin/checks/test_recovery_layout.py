import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('recovery_layout', Path(__file__).with_name('recovery-layout.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def inputs(tmp_path):
    b = tmp_path / 'bundle'
    (b / 'adapter/dependencies').mkdir(parents=True)
    for leaf in ('server-public.pem', 'client-private.pem', 'admin-client-private.pem', 'access-users.json', 'session-ca.pem'):
        (b / 'adapter' / leaf).write_text('fixture')
    for field in m.DEPENDENCIES:
        (b / 'adapter/dependencies' / (field + '.json')).write_text('{}')
    cfg = {'sealskin': {'username': 'network-qa'}, 'sealskin_admin': {}, 'access': {},
           **{key: '/retired/source/' + key for key in m.DEPENDENCIES}}
    return b, cfg


def test_rebind_never_uses_retired_absolute_paths(tmp_path):
    b, cfg = inputs(tmp_path)
    target = tmp_path / 'new/qa'
    new = m.rebind_config(cfg, b, target)
    for key in m.DEPENDENCIES:
        assert new[key].startswith(str(target))
        assert cfg[key].startswith('/retired/source/')
    assert new['sealskin_admin']['client_private_key_file'] == str(target / 'access/admin-private.pem')


@pytest.mark.parametrize('field', m.DEPENDENCIES)
def test_missing_catalog_cannot_fall_back_to_original(tmp_path, field):
    b, cfg = inputs(tmp_path)
    (b / 'adapter/dependencies' / (field + '.json')).unlink()
    with pytest.raises(ValueError, match='RECOVERY_DEPENDENCY_MISSING'):
        m.rebind_config(cfg, b, tmp_path / 'new/qa')


def test_live_owner_is_rejected(tmp_path):
    b, cfg = inputs(tmp_path)
    cfg['sealskin']['username'] = 'profile-adapter'
    with pytest.raises(ValueError, match='RECOVERY_QA_OWNER_REQUIRED'):
        m.rebind_config(cfg, b, tmp_path / 'new/qa')


def test_unpacked_job_spool_is_not_ignored(tmp_path):
    b, cfg = inputs(tmp_path)
    cfg['environment_job_spool'] = '/retired/source/jobs'
    with pytest.raises(ValueError, match='RECOVERY_JOB_SPOOL_INPUT_REQUIRED'):
        m.rebind_config(cfg, b, tmp_path / 'new/qa')
