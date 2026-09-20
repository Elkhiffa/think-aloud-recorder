"""Local WebView2 desktop shell. The service is the authority for all jobs."""
from pathlib import Path
import sys
import threading
from contextlib import contextmanager

BRIDGE_METHODS = ('get_state', 'refresh_devices', 'save_settings', 'save_preset', 'select_preset', 'choose_directory',
                  'choose_obsidian', 'import_hotwords', 'start_recording', 'stop_recording',
                  'process_session', 'open_review', 'package_session', 'open_folder',
                  'open_raw', 'save_cloud_key', 'verify_cloud_key', 'recover_cloud_task',
                  'model_action', 'open_official_obsidian')


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


def _close_is_allowed(result):
    """Fail closed if a bridge/service response is missing or malformed."""
    if isinstance(result, bool):
        return result
    if isinstance(result, dict) and result.get('ok') is True:
        data = result.get('data')
        if isinstance(data, bool):
            return data
        if isinstance(data, dict):
            return data.get('allowed') is True
    return False


def build_close_guard(service, window):
    def closing():
        try:
            allowed = _close_is_allowed(service.close_allowed())
        except Exception:
            allowed = False
        if not allowed:
            # Returning False cancels the native close; do not block its UI event.
            def minimize():
                try:
                    window.minimize()
                except Exception:
                    pass
            threading.Thread(target=minimize, name='minimize-on-active-close', daemon=True).start()
        return allowed
    return closing


def main():
    root = Path(__file__).resolve().parent
    with instance_lock(root):
        return run_window(root)


def run_window(root):
    import webview
    from desktop_service import DesktopService

    service = DesktopService(root)
    window = webview.create_window(
        '游戏体验记录器', url=(root / 'ui' / 'index.html').as_uri(),
        js_api=DesktopAPI(service), width=1000, height=740, min_size=(820, 620),
        frameless=False, background_color='#ffffff', text_select=True,
    )
    service.set_window(window)
    window.events.closing += build_close_guard(service, window)
    # Explicit renderer prevents silent fallback to the obsolete MSHTML engine.
    webview.start(gui='edgechromium', debug=False, private_mode=False,
                  storage_path=str(root / 'state' / 'webview'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
