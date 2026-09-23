"""No network: public-release protocol uses an injected HTTP transport."""
import json
import hashlib
import io
import os
import zipfile
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from updater import UpdateManager, SemVer, select_release
from test_update_installer import fixture


class UpdaterTests(unittest.TestCase):
    def test_semver_prerelease_numeric_and_build_precedence(self):
        versions=['1.0.0-alpha','1.0.0-alpha.1','1.0.0-beta.2','1.0.0-beta.11','1.0.0-rc.1','1.0.0','1.1.0']
        self.assertEqual(sorted(versions,key=SemVer),versions)
        self.assertEqual(SemVer('1.0.0+build.1'),SemVer('1.0.0'))
        for bad in ('01.0.0','1.0','1.0.0-01','latest'):
            with self.assertRaises(ValueError):SemVer(bad)

    def test_stable_channel_does_not_treat_preview_as_stable(self):
        releases=[{'tag_name':'v2.0.0-beta.1','prerelease':False,'draft':False},
                  {'tag_name':'v1.1.0','prerelease':False,'draft':False}]
        self.assertEqual(select_release(releases,False)['tag_name'],'v1.1.0')
        self.assertEqual(select_release(releases,True)['tag_name'],'v2.0.0-beta.1')
        self.assertIsNone(select_release([],False))

    def manager(self,handler):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name)/'app';root.mkdir()
        (root/'portable.json').write_text(json.dumps({'version':'0.6.0-preview.1'}))
        manager=UpdateManager(root,client_factory=lambda:httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(manager.cancel)
        return manager

    def test_no_releases_is_not_up_to_date(self):
        manager=self.manager(lambda request:httpx.Response(200,json=[]))
        manager.check();self.assertTrue(manager.wait(2))
        self.assertEqual(manager.snapshot()['state'],'no_release')

    def test_network_error_never_reports_current_or_leaks_url(self):
        def offline(request):raise httpx.ConnectError('SECRET_FROM_PROXY',request=request)
        manager=self.manager(offline);manager.check();manager.wait(2)
        self.assertEqual(manager.snapshot()['state'],'error')
        self.assertNotIn('SECRET_FROM_PROXY',manager.snapshot()['error'])

    def test_release_assets_must_belong_to_fixed_repository(self):
        release={'tag_name':'v1.0.0','draft':False,'prerelease':False,'html_url':'https://github.com/Elkhiffa/think-aloud-recorder/releases/tag/v1.0.0',
                 'assets':[{'name':'ExperienceRecorder-1.0.0-windows-x64.zip','browser_download_url':'https://evil.example/a','size':100,'state':'uploaded'}]}
        manager=self.manager(lambda request:httpx.Response(200,json=[release]))
        manager.check();manager.wait(2)
        self.assertEqual(manager.snapshot()['state'],'error')

    def download_fixture(self, *, partial=False, wrong_digest=False, redirect=False):
        data={}
        def handler(request):
            path=request.url.path
            if path.endswith('/releases'):return httpx.Response(200,json=[data['release']])
            if path.endswith('SHA256SUMS.txt'):return httpx.Response(200,content=data['sums'])
            if redirect:return httpx.Response(302,headers={'location':'https://example.org/package.zip'})
            content=data['archive'][:-10] if partial else data['archive']
            return httpx.Response(200,content=content)
        manager=self.manager(handler)
        stage=fixture(manager.root.parent/'fixture','1.0.0')
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in stage.rglob('*'):
                if path.is_file():archive.write(path,path.relative_to(stage).as_posix())
        data['archive']=buffer.getvalue(); digest=hashlib.sha256(data['archive']).hexdigest()
        name='ExperienceRecorder-1.0.0-windows-x64.zip'
        data['sums']=(digest+'  '+name+'\n').encode()
        base='https://github.com/Elkhiffa/think-aloud-recorder/releases/download/v1.0.0/'
        data['release']={'tag_name':'v1.0.0','draft':False,'prerelease':False,'body':'Notes','assets':[
            {'name':name,'state':'uploaded','browser_download_url':base+name,'size':len(data['archive']),
             'digest':'sha256:'+('0'*64 if wrong_digest else digest)},
            {'name':name[:-4]+'-SHA256SUMS.txt','state':'uploaded','browser_download_url':base+name[:-4]+'-SHA256SUMS.txt','size':len(data['sums'])}]}
        manager.check();self.assertTrue(manager.wait(2));self.assertEqual(manager.snapshot()['state'],'available')
        return manager

    def test_valid_download_verifies_archive_digest_manifest_and_file_hashes(self):
        manager=self.download_fixture();manager.download();self.assertTrue(manager.wait(3))
        self.assertEqual(manager.snapshot()['state'],'ready',manager.snapshot())
        self.assertEqual((manager._stage/'app.py').read_bytes(),b'old code')

    def test_partial_download_digest_conflict_and_external_redirect_never_ready(self):
        for options in ({'partial':True},{'wrong_digest':True},{'redirect':True}):
            with self.subTest(options=options):
                manager=self.download_fixture(**options);manager.download();manager.wait(3)
                self.assertEqual(manager.snapshot()['state'],'error')
                self.assertIsNone(manager._stage)

    def test_cancel_install_is_durable_and_rejects_foreign_job(self):
        manager=self.manager(lambda request:httpx.Response(200,json=[]))
        work=manager.root.parent/'work';work.mkdir()
        prepared={'job_path':str(work/'job.json'),'transaction_id':'test'}
        manager._prepared=prepared
        manager.cancel_install(prepared)
        self.assertTrue((work/'cancel.json').is_file())
        with self.assertRaises(Exception):manager.cancel_install({'job_path':'other'})

    def test_cancelled_prepare_can_retry_without_overwriting_old_attempt(self):
        manager=self.download_fixture();manager.download();self.assertTrue(manager.wait(3))
        fixture(manager.root,'0.6.0-preview.1')
        with patch('updater.self_check'):
            first=manager.prepare_install(os.getpid())
            manager.cancel_install(first)
            before=Path(first['job_path']).read_bytes()
            second=manager.prepare_install(os.getpid())
        self.assertNotEqual(first['job_path'],second['job_path'])
        self.assertEqual(Path(first['job_path']).read_bytes(),before)
        self.assertTrue((Path(first['cwd'])/'cancel.json').is_file())

    def test_prepared_recovery_entry_uses_fixed_relative_paths_and_is_failure_only(self):
        from update_installer import RECOVERY_ENTRY, read_json, status
        manager=self.download_fixture();manager.download();self.assertTrue(manager.wait(3))
        fixture(manager.root,'0.6.0-preview.1')
        with patch('updater.self_check'):prepared=manager.prepare_install(os.getpid())
        work=Path(prepared['cwd']);script=(work/RECOVERY_ENTRY).read_text(encoding='utf-8')
        self.assertIn('"%~dp0..\\package\\runtime\\python.exe"',script)
        self.assertIn('--job "%~dp0job.json" --recover --no-launch',script)
        self.assertIn('DisableDelayedExpansion',script)
        self.assertNotIn(str(manager.root),script)
        plan=read_json(work/'job.json')
        status(plan,'startup_unconfirmed','fixture')
        self.assertEqual(manager.snapshot()['last_install']['recovery_path'],str(work/RECOVERY_ENTRY))
        status(plan,'complete','fixture')
        self.assertIsNone(manager.snapshot()['last_install']['recovery_path'])


if __name__=='__main__':unittest.main()
