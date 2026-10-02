"""Read raw restored business state without activating any service."""
from pathlib import Path
import argparse,json,hashlib,sqlite3,tempfile,shutil,os,stat,subprocess
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);args=p.parse_args();root=args.root.resolve();os.umask(0o077)
assert (root/'RECOVERY_PENDING').is_file() and root.parent.name=='r6au-consistent-20261002'
manifest=json.loads((root/'MANIFEST.json').read_text());entries=manifest['entries'];results={'files':0,'sqlite':[]}
for name,row in entries.items():
 path=root/name;info=path.lstat();assert stat.S_IMODE(info.st_mode)==row['mode'] and info.st_uid==row['uid'] and info.st_gid==row['gid']
 if row['kind']=='file':
  assert path.is_file() and not path.is_symlink() and hashlib.file_digest(path.open('rb'),'sha256').hexdigest()==row['sha256'];results['files']+=1
 elif row['kind']=='symlink':assert path.is_symlink() and os.readlink(path)==row['target']
 else:assert path.is_dir() and not path.is_symlink()
for name,row in entries.items():
 if row['kind']!='file' or row.get('size',0)<16 or not name.startswith('storage/'):continue
 path=root/name
 with path.open('rb') as f:
  if f.read(16)!=b'SQLite format 3\x00':continue
 # A scratch copy includes WAL/SHM, so readback cannot mutate the preserved restore.
 with tempfile.TemporaryDirectory(prefix='r6au-sqlite-',dir=root.parent) as td:
  copy=Path(td)/path.name;shutil.copy2(path,copy)
  for suffix in ['-wal','-shm']:
   side=path.with_name(path.name+suffix)
   if side.is_file() and not side.is_symlink():shutil.copy2(side,copy.with_name(copy.name+suffix))
  db=sqlite3.connect('file:'+str(copy)+'?mode=ro',uri=True);checks=[v[0] for v in db.execute('PRAGMA quick_check')];assert checks==['ok'],name
  tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")};counts={t:db.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in sorted(tables & {'moz_cookies','moz_places','moz_bookmarks','cookies','logins'})};db.close();results['sqlite'].append({'path':name,'quick_check':'ok','table_count':len(tables),'counts':counts})
config=json.loads((root/'adapter/config.json').read_text());directory=json.loads((root/'adapter/dependencies/profile_directory.json').read_text());journal=json.loads((root/'adapter/state.json').read_text());assert all(v['status']=='stopped' for v in journal['bindings'].values());results['journal_bindings']=len(journal['bindings']);results['directory_records']=len(directory['browsers']);results['directory_deleted']=sum(v.get('status')=='deleted' for v in directory['browsers'])
plan=json.loads((root/'metadata/source-plan.json').read_text())
def mapped(source):
 if not Path(source).is_absolute():source=str(Path(plan['adapter/config.json']).parent/source)
 matches=[(len(v),root/k/Path(source).relative_to(v)) for k,v in plan.items() if Path(source)==Path(v) or Path(v) in Path(source).parents]
 assert matches,'unclosed dependency';return max(matches,key=lambda x:x[0])[1]
for group in ['sealskin','sealskin_admin','access']:
 for key,value in config.get(group,{}).items():
  if key.endswith('_file') and isinstance(value,str):assert mapped(value).is_file()
for key in ['state_file','environment_job_spool','environment_catalog','template_catalog','network_profile_catalog','profile_directory','legacy_network_migrations']:assert mapped(config[key]).exists()
# Full actual mount closure, with ephemeral display secrets deliberately replaced for QA.
workers=json.loads((root/'metadata/active-containers.json').read_text());results['worker_images']=sorted({c['Image'] for c in workers if c['Name'].startswith('/bp-home-')})
for c in workers:
 subprocess.run(['docker','image','inspect',c['Image']],stdout=subprocess.DEVNULL,check=True)
 for m in c['Mounts']:
  if m['Destination'].startswith('/run/browser-platform-session-input') or m['Destination']=='/run/secrets':continue
  # Stopped-generation configuration has intentionally been removed by normal Stop.
  if '/profile-network-runtime/' in m['Source']:continue
  assert mapped(m['Source']).exists()
results.update(result='PASS',raw_restored_files_verified=True,identity_files_present=True,referenced_mounts_present=True,services_activated=False)
(root.parent/'readback-result.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps({k:results[k] for k in ['result','files','journal_bindings','directory_records','directory_deleted']}|{'sqlite_databases':len(results['sqlite'])}))
