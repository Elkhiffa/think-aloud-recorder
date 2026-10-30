import unittest

from window_chrome import fit, page_factor, physical_size


class WindowSizeTests(unittest.TestCase):
    def test_page_gets_its_design_size_whatever_scale_it_renders_at(self):
        # 路径 1：家里的 WebView2 按 1.46 倍渲染，窗口客户区却是 720×520，页面只剩 494×357，主页卡片相互压住。
        self.assertEqual(physical_size((720, 520), 1.46, 96), (1051, 759))
        self.assertAlmostEqual(page_factor(1.46, 96), 1.46)
        # 公司：登录时 100%，Windows 整体放大，页面按 1 倍渲染：尺寸不变。
        self.assertEqual(physical_size((720, 520), 1.0, 96), (720, 520))
        self.assertEqual(page_factor(1.0, 96), 1.0)
        # 进程按显示器 150% 感知时，pywebview 已按 1.5 倍建窗，页面也按 1.5 倍渲染：不再放大。
        self.assertEqual(physical_size((720, 520), 1.5, 144), (1080, 780))
        self.assertEqual(page_factor(1.5, 144), 1.0)

    def test_unknown_ratio_falls_back_to_the_window_scale(self):
        # 路径 5：页面没回答 devicePixelRatio，或 GetDpiForWindow 失败返回 0。
        self.assertEqual(physical_size((720, 520), None, 144), (1080, 780))
        self.assertEqual(physical_size((720, 520), None, 0), (720, 520))
        self.assertEqual(page_factor(None, 144), 1.0)

    def test_a_grown_window_stays_inside_the_work_area(self):
        # 路径 1：资料台默认 1240×900，放大 1.46 倍后超过 1920×1040 的可用区域。
        self.assertEqual(fit((1810, 1314), (1920, 1040)), (1810, 1040))
        self.assertEqual(fit((1051, 759), (1920, 1040)), (1051, 759))



class WindowEdgeTests(unittest.TestCase):
    def test_title_bar_stays_paper_and_the_outline_is_a_weak_edge(self):
        """路径 1：场次库叠在洞察上（10-30 截图），两层纸色窗口之间看不出边界。"""
        from unittest.mock import patch
        import window_chrome
        chrome = object.__new__(window_chrome.WindowChrome)
        chrome._frame_color = '#F8F5EF'
        with patch.object(window_chrome, '_dwm') as dwm:
            chrome._tint(1)
        colors = {call.args[1]: call.args[2].value for call in dwm.call_args_list}
        rgb = lambda value: '#%02X%02X%02X' % (value & 255, value >> 8 & 255, value >> 16 & 255)
        self.assertEqual(rgb(colors[window_chrome.DWMWA_CAPTION_COLOR]), '#F8F5EF')
        self.assertEqual(rgb(colors[window_chrome.DWMWA_BORDER_COLOR]), '#D5D3CE')


if __name__ == '__main__':
    unittest.main()
