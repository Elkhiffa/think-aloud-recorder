"""Synthetic update transactions. No installed app, OBS or user data is touched."""
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from update_installer import (UpdateError, atomic_json, build_plan, extract_package,
                              install_files, rollback, safe_name, sha256, run_job, launcher_path, inventory)


def fixture(root, version='1.0.0', files=None, public=True, launcher='ExperienceRecorder.exe'):
    values = {'app.py': b'old code', launcher: b'MZ fixture',
              'portable_entry.py': b'entry', 'runtime/python.exe': b'MZ python',
              'runtime/pythonw.exe': b'MZ pythonw', 'ui/index.html': b'page',
              'vocabularies/uiux-terms.txt': b'UX',
              'portable.json': json.dumps({'version': version, 'platform': 'windows-x64',
                  'release_status': 'public' if public else 'candidate-not-for-public-redistribution'}).encode()}
    values.update(files or {})
    for name, content in values.items():
        path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    atomic_json(root/'package-manifest.json', {'schema':1, 'dependency_source_status':public,
        'files':[{'path':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()} for name,content in values.items()]})
    return root


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name); self.root=fixture(self.base/'app')
        self.stage=fixture(self.base/'stage','1.1.0', {'app.py':b'new code','updater.py':b'new module'})
        self.work=self.base/'transaction'; self.work.mkdir()

    def zip(self, extra=None):
        path=self.base/'download.zip'
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
            for item in self.stage.rglob('*'):
                if item.is_file(): archive.write(item,item.relative_to(self.stage).as_posix())
            for name,content in (extra or {}).items(): archive.writestr(name,content)
        return path

    def test_extract_checks_inventory_and_preserves_exact_bytes(self):
        result=extract_package(self.zip(),self.base/'extracted',expected_version='1.1.0')
        self.assertEqual(result['version'],'1.1.0')
        self.assertEqual((self.base/'extracted/app.py').read_bytes(),b'new code')

    def test_branded_update_and_rollback_keep_old_launcher_and_user_config(self):
        stage=fixture(self.base/'branded','1.2.0',launcher='Think Aloud.exe')
        (self.root/'config.json').write_bytes(b'private config')
        plan=build_plan(self.root,stage,self.work)
        install_files(plan)
        self.assertEqual(launcher_path(self.root).name,'Think Aloud.exe')
        self.assertTrue((self.root/'ExperienceRecorder.exe').is_file())
        self.assertEqual((self.root/'config.json').read_bytes(),b'private config')
        rollback(plan)
        self.assertEqual(launcher_path(self.root).name,'ExperienceRecorder.exe')
        self.assertFalse((self.root/'Think Aloud.exe').exists())
        self.assertTrue((self.work/'rollback-new/Think Aloud.exe').is_file())

    def test_new_launcher_package_extracts_and_updates_to_next_version(self):
        self.stage=fixture(self.base/'new-stage','1.2.0',launcher='Think Aloud.exe')
        extract_package(self.zip(),self.base/'new-extracted',expected_version='1.2.0')
        root=fixture(self.base/'new-root','1.1.0',launcher='Think Aloud.exe')
        build_plan(root,self.stage,self.work)
        result=run_job(self.work/'job.json',launch=False,checker=lambda root,work: launcher_path(root))
        self.assertEqual(result['state'],'installed')
        self.assertEqual(launcher_path(root).name,'Think Aloud.exe')

    def test_launcher_requires_owned_exact_name_and_matching_bytes(self):
        # A personal same-name file must not become an executable update target.
        (self.root/'Think Aloud.exe').write_bytes(b'personal file')
        self.assertEqual(launcher_path(self.root).name,'ExperienceRecorder.exe')
        stage=fixture(self.base/'branded','1.2.0',launcher='Think Aloud.exe')
        with self.assertRaises(UpdateError): build_plan(self.root,stage,self.work)
        (self.root/'ExperienceRecorder.exe').write_bytes(b'tampered launcher')
        with self.assertRaises(UpdateError): launcher_path(self.root)
        manifest=json.loads((stage/'package-manifest.json').read_text())
        manifest['files']=[r for r in manifest['files'] if r['path']!='Think Aloud.exe']
        with self.assertRaises(UpdateError): inventory(manifest)
        bad=fixture(self.base/'bad-launcher',launcher='arbitrary.exe')
        with self.assertRaises(UpdateError): launcher_path(bad)

    def test_branded_self_check_failure_restores_old_launcher(self):
        stage=fixture(self.base/'branded','1.2.0',launcher='Think Aloud.exe')
        build_plan(self.root,stage,self.work)
        def failed(root,work):
            self.assertEqual(launcher_path(root).name,'Think Aloud.exe')
            raise UpdateError('synthetic check failure')
        result=run_job(self.work/'job.json',launch=False,checker=failed)
        self.assertEqual(result['state'],'rolled_back')
        self.assertEqual(launcher_path(self.root).name,'ExperienceRecorder.exe')

    def test_bad_paths_and_case_aliases_are_rejected(self):
        for value in ('../config.json','C:/test','state/key','a:stream','CON.txt','ui/a.','ui/a ','ui\\a','/a'):
            with self.subTest(value=value), self.assertRaises(UpdateError):
                if value=='state/key': extract_package(self.zip({value:b'bad'}),self.base/'bad')
                else: safe_name(value)
        with self.assertRaises(UpdateError): extract_package(self.zip({'APP.py':b'bad'}),self.base/'bad2')

    def test_bad_hash_and_candidate_are_rejected(self):
        (self.stage/'app.py').write_bytes(b'corrupt')
        with self.assertRaises(UpdateError): extract_package(self.zip(),self.base/'bad')
        fixture(self.stage,'1.1.0',{'updater.py':b'new module'},public=False)
        with self.assertRaises(UpdateError): extract_package(self.zip(),self.base/'candidate')
        extract_package(self.zip(),self.base/'candidate-explicit',allow_candidate=True)

    def test_config_secrets_models_and_user_vocabulary_stay_byte_identical(self):
        saved={'config.json':b'private config','state/secrets/key.dpapi':b'encrypted',
               'state/webview/data':b'preferences','models/model.bin':b'model',
               'tools/obs/config/user.ini':b'obs','staging/raw.mkv':b'video',
               'vocabularies/personal.txt':b'private words','unknown.txt':b'user'}
        for name,value in saved.items():
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
        plan=build_plan(self.root,self.stage,self.work)
        install_files(plan)
        for name,value in saved.items():self.assertEqual((self.root/name).read_bytes(),value,name)
        self.assertEqual((self.root/'app.py').read_bytes(),b'new code')
        rollback(plan)
        self.assertEqual((self.root/'app.py').read_bytes(),b'old code')
        self.assertFalse((self.root/'updater.py').exists())
        self.assertTrue((self.work/'rollback-new/updater.py').is_file())

    def test_user_modified_bundled_vocabulary_is_preserved(self):
        (self.root/'vocabularies/uiux-terms.txt').write_bytes(b'user edit')
        plan=build_plan(self.root,self.stage,self.work)
        self.assertIn('vocabularies/uiux-terms.txt',plan['preserved'])
        install_files(plan)
        self.assertEqual((self.root/'vocabularies/uiux-terms.txt').read_bytes(),b'user edit')

    def test_unowned_collision_blocks_before_replacement(self):
        (self.root/'updater.py').write_bytes(b'user file')
        with self.assertRaises(UpdateError):build_plan(self.root,self.stage,self.work)
        self.assertEqual((self.root/'app.py').read_bytes(),b'old code')

    def test_interrupted_install_rolls_back_from_persisted_plan(self):
        plan=build_plan(self.root,self.stage,self.work)
        def fail_after_first(count):
            if count==1:raise OSError('synthetic disk failure')
        with self.assertRaises(OSError):install_files(plan,after_replace=fail_after_first)
        persisted=json.loads((self.work/'job.json').read_text(encoding='utf-8'))
        rollback(persisted)
        self.assertEqual((self.root/'app.py').read_bytes(),b'old code')
        self.assertEqual(persisted['state'],'rolled_back')

    def test_package_cannot_overwrite_protected_path_even_in_manifest(self):
        fixture(self.stage,'1.1.0',{'config.json':b'malicious'})
        with self.assertRaises(UpdateError):extract_package(self.zip(),self.base/'bad')

    def test_small_metadata_cap_rejects_before_reading_portable_json(self):
        fixture(self.stage,'1.1.0',{'portable.json':b' '*300000,'updater.py':b'new module'})
        archive=self.zip(); original=zipfile.ZipFile.read; reads=[]
        def tracked(obj,name,*args,**kwargs):
            reads.append(name);return original(obj,name,*args,**kwargs)
        with patch.object(zipfile.ZipFile,'read',tracked),self.assertRaises(UpdateError):
            extract_package(archive,self.base/'bad')
        self.assertNotIn('portable.json',reads)

    def test_symlink_zip_entry_and_declared_expansion_limit_rejected(self):
        archive=self.zip()
        with zipfile.ZipFile(archive,'a') as zipped:
            link=zipfile.ZipInfo('ui/link');link.create_system=3;link.external_attr=(0o120777<<16)
            zipped.writestr(link,b'../state')
        with self.assertRaises(UpdateError):extract_package(archive,self.base/'bad')
        with patch('update_installer.MAX_EXPANDED',1),self.assertRaises(UpdateError):
            extract_package(self.zip(),self.base/'small')

    def test_changed_staged_byte_blocks_before_first_replacement(self):
        plan=build_plan(self.root,self.stage,self.work)
        (self.stage/'app.py').write_bytes(b'changed after plan')
        with self.assertRaises(UpdateError):install_files(plan)
        self.assertEqual((self.root/'app.py').read_bytes(),b'old code')

    def test_cancel_marker_before_apply_preserves_software(self):
        plan=build_plan(self.root,self.stage,self.work)
        atomic_json(self.work/'cancel.json',{'cancelled':True})
        result=run_job(self.work/'job.json',launch=False,checker=lambda *args:None)
        self.assertEqual(result['state'],'failed')
        self.assertEqual((self.root/'app.py').read_bytes(),b'old code')

    def test_cancel_after_first_replace_allows_full_rollback(self):
        plan=build_plan(self.root,self.stage,self.work)
        def cancel(count):atomic_json(self.work/'cancel.json',{'cancelled':True})
        with self.assertRaises(UpdateError):install_files(plan,after_replace=cancel)
        rollback(plan)
        self.assertEqual((self.root/'app.py').read_bytes(),b'old code')

    def test_failed_new_self_check_restores_old_version(self):
        build_plan(self.root,self.stage,self.work)
        def failed_check(*args):raise UpdateError('synthetic self-check failure')
        result=run_job(self.work/'job.json',launch=False,checker=failed_check)
        self.assertEqual(result['state'],'rolled_back')
        self.assertEqual((self.root/'app.py').read_bytes(),b'old code')
        self.assertEqual(json.loads((self.root/'portable.json').read_text())['version'],'1.0.0')

    def test_successful_transaction_releases_both_locks(self):
        from update_installer import file_lock
        build_plan(self.root,self.stage,self.work)
        result=run_job(self.work/'job.json',launch=False,checker=lambda *args:None)
        self.assertEqual(result['state'],'installed')
        with file_lock(self.root/'app.lock'),file_lock(self.root/'update.lock'):pass

    def test_unknown_process_blocker_never_replaces_files(self):
        build_plan(self.root,self.stage,self.work)
        with patch('update_installer.blockers',return_value=[123]):
            result=run_job(self.work/'job.json',launch=False,checker=lambda *args:None)
        self.assertEqual(result['state'],'failed')
        self.assertEqual((self.root/'app.py').read_bytes(),b'old code')

    def test_late_new_file_collision_is_not_overwritten(self):
        plan=build_plan(self.root,self.stage,self.work)
        def create_unowned_after_backup(count):
            if count==1:(self.root/'updater.py').write_bytes(b'unowned concurrent file')
        with self.assertRaises(UpdateError):install_files(plan,after_replace=create_unowned_after_backup)
        self.assertEqual((self.root/'updater.py').read_bytes(),b'unowned concurrent file')
        with self.assertRaises(UpdateError):rollback(plan)
        self.assertEqual((self.root/'app.py').read_bytes(),b'old code')

    def test_cancelled_interrupted_transaction_can_recover(self):
        plan=build_plan(self.root,self.stage,self.work)
        def interrupted(count):
            if count==1:
                atomic_json(self.work/'cancel.json',{'cancelled':True})
                raise OSError('synthetic interruption')
        with self.assertRaises(OSError):install_files(plan,after_replace=interrupted)
        result=run_job(self.work/'job.json',recover=True,launch=False)
        self.assertEqual(result['state'],'rolled_back')
        self.assertEqual((self.root/'app.py').read_bytes(),b'old code')


if __name__=='__main__':unittest.main()
