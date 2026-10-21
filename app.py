"""Local WebView2 desktop shell. The service is the authority for all jobs."""
from pathlib import Path
import sys
from contextlib import contextmanager

BRIDGE_METHODS = ('get_state', 'get_microphone_state', 'refresh_device_inventory', 'refresh_devices', 'save_settings', 'save_preset', 'save_general', 'select_preset', 'delete_preset', 'choose_directory',
                  'import_hotwords', 'choose_hotword_files', 'open_dictionary_site', 'open_bailian_console',
                  'start_recording', 'stop_recording',
                  'process_session', 'open_review', 'open_insight', 'open_desk', 'rename_session', 'package_session', 'open_folder',
                  'open_raw', 'save_cloud_key', 'verify_cloud_key', 'recover_cloud_task',
                  'model_action', 'update_action')


class DesktopAPI:
    """Only these methods cross into JavaScript; paths/window/lifecycle stay private."""
    def __init__(self, service, chrome=None):
        for name in BRIDGE_METHODS:
            setattr(self, name, getattr(service, name))
        if chrome is not None:
            from window_chrome import CHROME_METHODS
            for name in CHROME_METHODS:
                setattr(self, name, getattr(chrome, name))


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
    from update_installer import ensure_launch_allowed
    ensure_launch_allowed(root)
    with instance_lock(root):
        return run_window(root)


def _prepare_chrome(chrome, client_size):
    """Native window styling is cosmetic: if it fails, the window keeps working with its page buttons."""
    try:
        chrome.prepare(client_size=client_size)
    except Exception:
        pass


def main_window_options(webview):
    """A compact recorder page (720x520 of page; the sizing border is added outside it),
    bounded by the actual monitor work area."""
    options = dict(width=720, height=520, min_size=(720, 520))
    try:
        screen = list(webview.screens)[0]
        width, height = screen.width, screen.height
        frame = getattr(screen, 'frame', None)
        for name, current in (('Width', width), ('Height', height)):
            value = getattr(frame, name, None)
            if type(value) is int and 320 <= value <= current:
                if name == 'Width':
                    width = value
                else:
                    height = value
        if type(width) is int and type(height) is int and width >= 360 and height >= 400:
            available_width, available_height = width - 32, height - 48
            options.update(width=min(720, available_width), height=min(520, available_height),
                           min_size=(min(720, available_width), min(520, available_height)), screen=screen)
    except Exception:
        pass
    return options


def run_window(root):
    import webview
    from desktop_service import DesktopService

    from window_chrome import WindowChrome
    service = DesktopService(root)
    chrome = WindowChrome(frame_color='#f3ede1')
    options = main_window_options(webview)
    window = webview.create_window(
        'Think Aloud · 体验记录器', url=(root / 'ui' / 'index.html').as_uri(),
        js_api=DesktopAPI(service, chrome), **options,
        frameless=True, easy_drag=False, shadow=True, background_color='#f3ede1', text_select=True,
    )
    chrome.bind(window)
    # The page draws its own title bar; Windows keeps moving, sizing and snapping (window_chrome).
    window.events.loaded += lambda: _prepare_chrome(chrome, (options['width'], options['height']))
    from window_manager import WindowManager
    windows = WindowManager(service, webview)
    windows.bind_main(window)
    service.set_window(window)
    service.set_review_opener(windows.open_review)
    service.set_insight_opener(windows.open_insight)
    service.set_desk_hooks(windows.open_desk, windows.desk_follow)
    service.set_update_lifecycle(windows.review_count, windows.close_for_update)
    from update_installer import acknowledge_start
    window.events.loaded += lambda: acknowledge_start(root)
    window.events.loaded += service.check_startup_update
    # Explicit renderer prevents silent fallback to the obsolete MSHTML engine.
    webview.settings['ALLOW_FILE_URLS'] = True
    from vocabulary_ipc import VocabularyServer
    try:
        vocabulary_server = VocabularyServer(root, service._vocabulary_request).start()
    except OSError:
        # Optional agent integration must not prevent ordinary recording/review.
        vocabulary_server = None
    try:
        webview.start(gui='edgechromium', debug=False, private_mode=False,
                      storage_path=str(root / 'state' / 'webview'), icon=str(root / 'ui' / 'brand.ico'))
    finally:
        if vocabulary_server is not None:
            vocabulary_server.close()
        # The native loop may end before a closed-event worker finishes. Keep
        # the instance lock until verified child cleanup has completed.
        service.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
