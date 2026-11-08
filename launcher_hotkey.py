"""Windows global shortcut and foreground activation for QuickDock."""
import ctypes
from ctypes import wintypes
from PySide6 import QtCore

class LauncherHotkey(QtCore.QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.identifier = 0x5145
        self.registered = False
    def register(self, modifiers, key):
        self.close()
        if key:
            self.registered = bool(ctypes.windll.user32.RegisterHotKey(None, self.identifier, 0x4000 | modifiers, key))
        return self.registered
    def nativeEventFilter(self, kind, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312 and msg.wParam == self.identifier:
            self.callback()
            return True, 0
        return False, 0
    def close(self):
        if self.registered:
            ctypes.windll.user32.UnregisterHotKey(None, self.identifier)
            self.registered = False


def foreground_window(widget):
    """Request foreground while processing the user's WM_HOTKEY, without elevation."""
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = int(widget.winId())
    requested = bool(user32.SetForegroundWindow(hwnd))
    foreground = user32.GetForegroundWindow()
    return foreground == hwnd
