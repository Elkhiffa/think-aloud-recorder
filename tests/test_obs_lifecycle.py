"""Synthetic process/socket/native-control evidence only; never touch a running OBS."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import recorder


class ObsLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.process = MagicMock(pid=12345)
        self.process.poll.return_value = None
        self.process.wait.return_value = 0
        self.child = MagicMock()
        self.child.pid = 12345
        self.child.ppid.return_value = recorder.os.getpid()
        self.child.exe.return_value = str(self.root / 'tools/obs/bin/64bit/obs64.exe')
        self.child.create_time.return_value = 1790000000.0
        self.child.is_running.return_value = True
        self.child.net_connections.return_value = [SimpleNamespace(
            laddr=('127.0.0.1', 11223), raddr=('127.0.0.1', 22334),
            status=recorder.psutil.CONN_ESTABLISHED)]
        self.connection = MagicMock()
        self.connection.base_client.ws.sock.getsockname.return_value = ('127.0.0.1', 22334)
        self.connection.base_client.ws.sock.getpeername.return_value = ('127.0.0.1', 11223)
        for name in ('get_record_status', 'get_stream_status', 'get_replay_buffer_status', 'get_virtual_cam_status'):
            getattr(self.connection, name).return_value = SimpleNamespace(output_active=False)
        self.connection.get_output_list.return_value.outputs = [
            {'outputName': 'synthetic file output', 'outputActive': False},
            {'outputName': 'synthetic virtual camera', 'outputActive': False}]
        self.connection.get_profile_list.return_value.current_profile_name = 'Experience'
        self.connection.get_scene_collection_list.return_value.current_scene_collection_name = 'Experience'
        self.cfg = dict(port=11223, password='synthetic-only-credential')
        self.patches = [patch.object(recorder, 'ROOT', self.root),
                        patch.object(recorder, '_owned_obs', {}),
                        patch.object(recorder, '_obs_closed_roots', set()),
                        patch.object(recorder, 'config', return_value=self.cfg),
                        patch.object(recorder.psutil, 'Process', return_value=self.child),
                        patch.object(recorder.obs, 'ReqClient', return_value=self.connection),
                        patch.object(recorder.time, 'sleep'),
                        patch.object(recorder.subprocess, 'Popen', return_value=self.process),
                        patch.object(recorder, '_request_obs_window_close', return_value=True)]
        self.mocks = [item.start() for item in self.patches]
        for item in self.patches:
            self.addCleanup(item.stop)
        self.req, self.popen, self.native_close = self.mocks[5], self.mocks[7], self.mocks[8]

    def launch(self):
        self.req.side_effect = [ConnectionRefusedError('synthetic unavailable'), self.connection]
        self.assertIs(recorder.client(), self.connection)
        self.req.side_effect = None
        return recorder._owned_obs[self.root]

    def test_launch_retains_original_handle_and_close_verifies_idle_then_waits(self):
        owned = self.launch()
        self.assertIs(owned['process'], self.process)
        self.assertEqual(owned['exe'], Path(self.child.exe.return_value))
        def wait_after_disconnect(timeout):
            self.connection.disconnect.assert_called_once()
            return 0
        self.process.wait.side_effect = wait_after_disconnect
        def close_after_disconnect(process):
            self.connection.disconnect.assert_called_once()
            return True
        self.native_close.side_effect=close_after_disconnect
        result = recorder.shutdown_owned_obs(self.root)
        self.assertEqual(result, {'status': 'closed'})
        self.native_close.assert_called_once_with(self.process)
        self.process.wait.assert_called_once_with(timeout=8)
        self.process.kill.assert_not_called()
        self.process.terminate.assert_not_called()
        self.connection.disconnect.assert_called_once()
        self.assertNotIn(self.root, recorder._owned_obs)

    def test_connected_existing_process_is_never_adopted_or_closed(self):
        self.assertIs(recorder.client(), self.connection)
        self.popen.assert_not_called()
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'not_owned'})
        self.native_close.assert_not_called()

    def test_connection_loss_does_not_launch_second_live_owned_obs(self):
        self.launch()
        self.req.side_effect = [ConnectionRefusedError('synthetic lost'), self.connection]
        self.assertIs(recorder.client(), self.connection)
        self.popen.assert_called_once()

    def test_closed_root_cannot_relaunch_on_late_request(self):
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'not_owned'})
        with self.assertRaisesRegex(RuntimeError, '正在关闭'):
            recorder.client()
        self.popen.assert_not_called()
        self.req.assert_not_called()

    def test_restart_recovers_only_the_exact_child_from_its_receipt(self):
        self.launch()
        recorder._owned_obs.clear()
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'closed'})
        self.native_close.assert_called_once()
        self.popen.assert_called_once()
        self.assertEqual(recorder.read(self.root / recorder._OBS_RECEIPT)['status'], 'exited')

    def test_stale_receipt_cannot_adopt_a_reused_pid(self):
        self.launch()
        recorder._owned_obs.clear()
        self.child.create_time.return_value += 30
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'not_owned'})
        self.native_close.assert_not_called()

    def test_other_installation_cannot_close_or_block_this_child(self):
        self.launch()
        other_root = self.root / 'different-version'
        self.assertEqual(recorder.shutdown_owned_obs(other_root), {'status': 'not_owned'})
        self.native_close.assert_not_called()
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'closed'})

    def test_exited_original_handle_does_not_target_reused_pid(self):
        self.launch()
        self.process.poll.return_value = 0
        self.req.reset_mock()
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'already_exited'})
        self.req.assert_not_called()
        self.native_close.assert_not_called()

    def test_foreign_parent_or_image_prevents_close_before_connecting(self):
        self.launch()
        for attribute, value in [('ppid', recorder.os.getpid() + 1), ('exe', str(self.root / 'foreign/obs64.exe'))]:
            with self.subTest(attribute=attribute):
                method = getattr(self.child, attribute)
                original = method.return_value
                method.return_value = value
                self.req.reset_mock()
                self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'identity_unverified'})
                self.req.assert_not_called()
                method.return_value = original
        self.native_close.assert_not_called()

    def test_wrong_socket_endpoint_cannot_authorize_an_owned_process_close(self):
        self.launch()
        self.child.net_connections.return_value[0].raddr = ('127.0.0.1', 33445)
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'endpoint_unverified'})
        self.native_close.assert_not_called()

    def test_any_active_or_missing_output_status_preserves_obs(self):
        self.launch()
        for name in ('get_record_status', 'get_stream_status'):
            method = getattr(self.connection, name)
            for state in (SimpleNamespace(output_active=True), SimpleNamespace()):
                with self.subTest(request=name, state=state):
                    method.return_value = state
                    self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'output_active_or_unknown'})
                    self.native_close.assert_not_called()
            method.return_value = SimpleNamespace(output_active=False)

    def test_active_or_unknown_auxiliary_output_inventory_preserves_obs(self):
        self.launch()
        for outputs in ([{'outputName': 'replay buffer', 'outputActive': True}],
                        [{'outputName': 'virtual camera', 'outputActive': True}],
                        [{'outputName': 'plugin output'}], ['malformed'], None):
            with self.subTest(outputs=outputs):
                self.connection.get_output_list.return_value.outputs = outputs
                self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'output_active_or_unknown'})
                self.native_close.assert_not_called()

    def test_disabled_replay_buffer_does_not_require_unavailable_status_request(self):
        self.launch()
        self.connection.get_replay_buffer_status.side_effect = recorder.OBSSDKRequestError(
            'GetReplayBufferStatus', 604, 'Replay buffer is not available.')
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'closed'})
        self.connection.get_replay_buffer_status.assert_not_called()

    def test_status_or_identity_query_failure_fails_closed_without_exception_details(self):
        self.launch()
        self.connection.get_record_status.side_effect = ConnectionError('synthetic secret must not be returned')
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'unverified'})
        self.native_close.assert_not_called()
        self.connection.get_record_status.side_effect = None
        self.child.net_connections.side_effect = recorder.psutil.AccessDenied()
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'unverified'})
        self.native_close.assert_not_called()

    def test_changed_profile_and_collection_preserve_manually_repurposed_child(self):
        self.launch()
        self.connection.get_profile_list.return_value.current_profile_name = 'Manual profile'
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'configuration_changed'})
        self.connection.get_profile_list.return_value.current_profile_name = 'Experience'
        self.connection.get_scene_collection_list.return_value.current_scene_collection_name = 'Manual scenes'
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'configuration_changed'})
        self.native_close.assert_not_called()

    def test_identity_rechecked_after_status_before_native_close(self):
        self.launch()
        with patch.object(recorder, '_owned_obs_identity', side_effect=[True, True, False]):
            self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'identity_unverified'})
        self.native_close.assert_not_called()

    def test_stalled_normal_close_terminates_only_the_verified_idle_child(self):
        self.launch()
        self.process.wait.side_effect = [subprocess.TimeoutExpired('synthetic child', 8), 0]
        self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'terminated_after_close_timeout'})
        self.process.kill.assert_not_called()
        self.process.terminate.assert_called_once()
        self.assertEqual(self.process.wait.call_args_list[-1].kwargs['timeout'], 5)

    def test_changed_identity_after_close_timeout_never_terminates(self):
        self.launch()
        self.process.wait.side_effect = subprocess.TimeoutExpired('synthetic child', 8)
        with patch.object(recorder, '_owned_obs_identity', side_effect=[True, True, True, False]):
            self.assertEqual(recorder.shutdown_owned_obs(self.root), {'status': 'close_unconfirmed'})
        self.process.terminate.assert_not_called()


@unittest.skipUnless(recorder.os.name == 'nt', 'Windows native close boundary')
class NativeCloseBoundaryTests(unittest.TestCase):
    def test_wm_close_targets_only_live_owned_obs_window(self):
        process = MagicMock(pid=12345)
        process.poll.return_value = None
        user32 = MagicMock()
        owners = {101: 55555, 102: 12345, 103: 12345}
        titles = {101: 'OBS foreign', 102: 'OBS synthetic owned', 103: 'Hidden helper'}
        def owner(hwnd, pointer):
            ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents.value = owners[hwnd]
        def title(hwnd, buffer, count):
            buffer.value = titles[hwnd]
        user32.GetWindowThreadProcessId.side_effect = owner
        user32.GetWindowTextW.side_effect = title
        user32.EnumWindows.side_effect = lambda callback, arg: [callback(hwnd, arg) for hwnd in owners]
        user32.PostMessageW.return_value = True
        with patch.object(ctypes, 'WinDLL', return_value=user32):
            self.assertTrue(recorder._request_obs_window_close(process))
        user32.PostMessageW.assert_called_once_with(102, 0x0010, 0, 0)

    def test_changed_hwnd_owner_is_not_sent_a_close_message(self):
        process = MagicMock(pid=12345)
        process.poll.return_value = None
        user32 = MagicMock()
        identities = iter([12345, 55555])
        def owner(hwnd, pointer):
            ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents.value = next(identities)
        user32.GetWindowThreadProcessId.side_effect = owner
        user32.GetWindowTextW.side_effect = lambda hwnd, buffer, count: setattr(buffer, 'value', 'OBS synthetic owned')
        user32.EnumWindows.side_effect = lambda callback, arg: callback(102, arg)
        with patch.object(ctypes, 'WinDLL', return_value=user32):
            self.assertFalse(recorder._request_obs_window_close(process))
        user32.PostMessageW.assert_not_called()


if __name__ == '__main__':
    unittest.main()
