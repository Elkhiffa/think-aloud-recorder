"""Local WebView2 desktop shell. The service is the authority for all jobs."""
from pathlib import Path
import sys
from contextlib import contextmanager

BRIDGE_METHODS = ('get_state', 'refresh_devices', 'save_settings', 'save_preset', 'select_preset', 'choose_directory',
                  'import_hotwords', 'choose_hotword_files', 'open_dictionary_site', 'open_bailian_console',
                  'start_recording', 'stop_recording',
                  'process_session', 'open_review', 'rename_session', 'package_session', 'open_folder',
                  'open_raw', 'save_cloud_key', 'verify_cloud_key', 'recover_cloud_task',
                  'model_action')


class DesktopAPI:
    """Only these methods cross into JavaScript; paths/window/lifecycle stay private."""
    def __init__(self, service):
        for name in BRIDGE_METHODS:
            setattr(self, name, getattr(service, name))


@contextmanager
def instance_lock(root):
    """A second window must never race the first window's OBS ownership."""
    import msvcrt
    with (root / 'app.lock').open('a+b') as handle:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError('记录器已经运行，请打开任务栏中的窗口。') from error
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def main():
    root = Path(__file__).resolve().parent
    with instance_lock(root):
        return run_window(root)


def run_window(root):
    import webview
    from desktop_service import DesktopService

    service = DesktopService(root)
    window = webview.create_window(
        'Think Aloud · 体验记录器', url=(root / 'ui' / 'index.html').as_uri(),
        js_api=DesktopAPI(service), width=1240, height=960, min_size=(820, 620),
        frameless=False, background_color='#fcfaf5', text_select=True,
    )
    from window_manager import WindowManager
    windows = WindowManager(service, webview)
    windows.bind_main(window)
    service.set_window(window)
    service.set_review_opener(windows.open_review)
    # Explicit renderer prevents silent fallback to the obsolete MSHTML engine.
    webview.settings['ALLOW_FILE_URLS'] = True
    try:
        webview.start(gui='edgechromium', debug=False, private_mode=False,
                      storage_path=str(root / 'state' / 'webview'), icon=str(root / 'ui' / 'brand.ico'))
    finally:
        # The native loop may end before a closed-event worker finishes. Keep
        # the instance lock until verified child cleanup has completed.
        service.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
