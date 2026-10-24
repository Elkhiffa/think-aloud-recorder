from types import SimpleNamespace
import unittest

from input_capture_windows import ButtonStateProbe

MEDIUM, HIGH = 0x2000, 0x3000


def probe(foreground, levels):
    """A probe at the normal (medium) level whose window in front belongs to process 42."""
    instance = ButtonStateProbe.__new__(ButtonStateProbe)
    instance.integrity, instance._foreground_pid, instance._foreground_integrity = MEDIUM, None, None
    instance.user = SimpleNamespace(GetForegroundWindow=lambda: foreground,
                                    GetWindowThreadProcessId=lambda hwnd, ref: setattr(ref._obj, 'value', 42))
    instance._integrity = lambda pid: levels.get(pid)
    return instance


class RaisedForegroundTests(unittest.TestCase):
    def test_game_above_the_recorder_withholds_keyboard_and_mouse(self):
        # 路径 1：燕云以管理员身份运行（高完整性），本软件是普通权限：键鼠收不到，要标缺口。
        self.assertTrue(probe(7, {42: HIGH}).raised_foreground())

    def test_unreadable_token_counts_as_above(self):
        # 路径 1：普通权限读不了管理员进程的令牌，_integrity 返回 None。
        self.assertTrue(probe(7, {}).raised_foreground())

    def test_same_level_game_is_captured(self):
        self.assertFalse(probe(7, {42: MEDIUM}).raised_foreground())

    def test_no_window_in_front_is_not_a_gap(self):
        # 路径 5：切换窗口的瞬间没有前台窗口。
        self.assertFalse(probe(0, {42: HIGH}).raised_foreground())


if __name__ == '__main__':
    unittest.main()
