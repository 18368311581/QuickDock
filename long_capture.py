import ctypes
import datetime
from ctypes import wintypes
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from screen_pins import HOTKEYS, CaptureHotkey, SelectionOverlay


def find_shift(previous, current):
    """Match an overlapping scroll region; return pixel shift, 0, or None."""
    if previous.isNull() or previous.size() != current.size():
        return None
    width = min(80, previous.width())
    height = min(480, previous.height())
    def sample(image):
        scaled = image.scaled(width, height, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)
        scaled = scaled.convertToFormat(QtGui.QImage.Format_Grayscale8)
        raw = bytes(scaled.constBits()); stride = scaled.bytesPerLine()
        # Margins often contain scrollbars, avatars, or fixed side controls.
        left, right = width // 12, width - width // 12
        return [raw[y * stride + left:y * stride + right:2] for y in range(height)]
    if width < 16 or height < 32:
        return None
    a, b = sample(previous), sample(current)
    def row_error(x, y):
        return sum(abs(i-j) for i, j in zip(x, y)) / len(x)
    def score(shift):
        overlap = height - shift
        step = max(1, overlap // 48)
        errors = [row_error(a[y + shift], b[y]) for y in range(0, overlap, step)
                  if max(b[y]) - min(b[y]) >= 12]
        if len(errors) < 5:
            return 255
        # Allow a larger share of changing rows while keeping text rows meaningful.
        errors.sort()
        kept = errors[:max(5, int(len(errors) * .75))]
        return sum(kept) / len(kept)
    unchanged = score(0)
    if bytes(previous.constBits()) == bytes(current.constBits()):
        return 0
    if unchanged < 1.1:
        return 0
    scores = [(score(shift), shift) for shift in range(1, int(height * .70))]
    best, shift = min(scores)
    distant = [value for value, pos in scores if abs(pos - shift) > max(4, height // 35)]
    if best > 18 or best >= unchanged * .85 or (distant and min(distant) < best + .8):
        return None
    return max(1, round(shift * previous.height() / height))


def wheel_target(screen, rect):
    """Locate the native window at the selection center without moving the pointer."""
    user32 = ctypes.windll.user32
    class POINT(ctypes.Structure):
        _fields_ = [('x', wintypes.LONG), ('y', wintypes.LONG)]
    center = rect.center()
    geometry = screen.geometry()
    ratio = screen.devicePixelRatio()
    point = POINT(round(geometry.x() + (center.x() - geometry.x()) * ratio),
                  round(geometry.y() + (center.y() - geometry.y()) * ratio))
    user32.WindowFromPoint.argtypes = [POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    hwnd = user32.WindowFromPoint(point)
    return hwnd, point.x, point.y


def post_wheel(target, notches):
    """Post a wheel message at the selected screen point; never reposition the cursor."""
    hwnd, x, y = target
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    delta = -120 * notches
    wparam = (delta & 0xffff) << 16
    lparam = (x & 0xffff) | ((y & 0xffff) << 16)
    return bool(user32.PostMessageW(hwnd, 0x020a, wparam, lparam))


class LongHotkey(CaptureHotkey):
    def __init__(self, page):
        super().__init__(page)
        self.identifier = 0x5146


class LongOverlay(SelectionOverlay):
    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.releaseMouse()
            if self.page.selection_start is not None:
                rect = QtCore.QRect(self.page.selection_start, event.globalPosition().toPoint()).normalized()
                self.page.selected(rect)


class LongCapturePage(QtWidgets.QWidget):
    def __init__(self, dock, register_hotkey=True):
        super().__init__()
        self.dock = dock
        self.capturing = False
        self.overlays = []
        self.frames = []
        self.parts = []
        self.pending = None
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.sample)
        settings = dock.store.data['settings'].get('long_capture', {})
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        self.enable_switch = QtWidgets.QCheckBox('启用长截图')
        layout.addWidget(self.enable_switch)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel('长截图热键'))
        self.hotkey_choice = QtWidgets.QComboBox()
        for title, mods, key in HOTKEYS:
            self.hotkey_choice.addItem(title, (mods, key))
        self.hotkey_choice.setCurrentIndex(max(0, self.hotkey_choice.findText(settings.get('hotkey', '无'))))
        row.addWidget(self.hotkey_choice, 1)
        layout.addLayout(row)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel('保存目录'))
        default = str(Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.PicturesLocation)) / 'QuickDock 长截图')
        self.directory = QtWidgets.QLineEdit(settings.get('directory') or default)
        self.directory.setReadOnly(True)
        row.addWidget(self.directory, 1)
        choose = QtWidgets.QPushButton('选择…')
        choose.clicked.connect(self.choose_directory)
        row.addWidget(choose)
        layout.addLayout(row)
        self.start_button = QtWidgets.QPushButton('开始长截图')
        self.start_button.clicked.connect(self.begin_capture)
        layout.addWidget(self.start_button)
        self.retry = QtWidgets.QPushButton('保存未保存的截图')
        self.retry.clicked.connect(self.save_pending)
        self.retry.hide()
        layout.addWidget(self.retry)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch(1)
        self.hotkey = LongHotkey(self) if register_hotkey else None
        if self.hotkey:
            QtWidgets.QApplication.instance().installNativeEventFilter(self.hotkey)
        self.enable_switch.setChecked(bool(settings.get('enabled', False)))
        self.set_enabled(self.enable_switch.isChecked())
        self.enable_switch.toggled.connect(self.enabled_toggled)
        self.hotkey_choice.currentIndexChanged.connect(self.change_hotkey)

    def save_settings(self):
        settings = self.dock.store.data['settings'].setdefault('long_capture', {})
        settings.update(hotkey=self.hotkey_choice.currentText(), directory=self.directory.text(), enabled=self.enable_switch.isChecked())
        self.dock.save()

    def choose_directory(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, '选择长截图保存目录', self.directory.text())
        if path:
            self.directory.setText(path)
            self.save_settings()

    def change_hotkey(self):
        self.save_settings()
        self.update_hotkey()

    def update_hotkey(self):
        mods, key = self.hotkey_choice.currentData()
        success = False
        if self.hotkey:
            self.hotkey.close()
            if self.enable_switch.isChecked() and key:
                success = self.hotkey.register(mods, key)
        message = '框选单个屏幕内的滚动内容，程序将自动向下滚动并保存 PNG。'
        if self.enable_switch.isChecked() and key and not success:
            message += '\n热键被占用或不可用，请更换热键或点击按钮。'
        self.status.setText(message)

    def enabled_toggled(self, enabled):
        self.set_enabled(enabled)
        self.save_settings()

    def set_enabled(self, enabled):
        if not enabled and self.capturing:
            self.finish_capture()
        self.start_button.setEnabled(enabled)
        self.update_hotkey()

    def begin_capture(self):
        if not self.enable_switch.isChecked() or self.capturing or self.dock.pin_page.capturing or self.pending is not None or QtWidgets.QApplication.activeModalWidget():
            return
        self.capturing = True
        self.selection = self.selection_start = None
        self.parts = []
        self.previous_windows = [w for w in [self.dock, self.dock.mini, *self.dock.pin_page.pins] if w.isVisible()]
        for window in self.previous_windows:
            window.hide()
        QtCore.QTimer.singleShot(250, self.show_selection)

    def show_selection(self):
        if not self.capturing:
            return
        try:
            self.frames = [(s.geometry(), s.grabWindow(0)) for s in QtGui.QGuiApplication.screens()]
            if not self.frames or any(p.isNull() for _, p in self.frames):
                raise RuntimeError('无法读取屏幕图像')
            self.overlays = [LongOverlay(self, rect, pix) for rect, pix in self.frames]
            for overlay in self.overlays:
                overlay.show(); overlay.raise_()
            current = next((o for o in self.overlays if o.geometry().contains(QtGui.QCursor.pos())), self.overlays[0])
            current.activateWindow(); current.setFocus()
        except Exception as exc:
            self.finish_capture()
            QtWidgets.QMessageBox.warning(self, '长截图失败', str(exc))

    def selected(self, rect):
        screens = [s for s in QtGui.QGuiApplication.screens() if s.geometry().contains(rect)]
        for overlay in self.overlays:
            overlay.hide(); overlay.deleteLater()
        self.overlays = []
        if len(screens) != 1 or rect.width() < 100 or rect.height() < 100:
            self.finish_capture()
            QtWidgets.QMessageBox.warning(self, '无法开始长截图', '请选择单个屏幕内至少 100 × 100 的区域。')
            return
        self.screen, self.rect = screens[0], rect
        self.control = QtWidgets.QWidget(None, QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowTitleHint)
        self.control.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.control.setWindowTitle('长截图')
        line = QtWidgets.QHBoxLayout(self.control)
        self.progress = QtWidgets.QLabel('准备采集…')
        line.addWidget(self.progress)
        done = QtWidgets.QPushButton('完成并保存'); done.clicked.connect(self.complete)
        cancel = QtWidgets.QPushButton('取消'); cancel.clicked.connect(self.finish_capture)
        line.addWidget(done); line.addWidget(cancel)
        self.control.adjustSize()
        area = self.screen.availableGeometry()
        w, h = self.control.width(), self.control.height()
        positions = [QtCore.QPoint(area.left(), rect.top()-h-5), QtCore.QPoint(area.left(), rect.bottom()+6), QtCore.QPoint(rect.left()-w-5, area.top()), QtCore.QPoint(rect.right()+6, area.top())]
        point = next((p for p in positions if area.contains(QtCore.QRect(p, self.control.size())) and not QtCore.QRect(p, self.control.size()).intersects(rect)), None)
        if point is None:
            self.control.deleteLater(); self.finish_capture()
            QtWidgets.QMessageBox.warning(self, '无法开始长截图', '选区周围没有放置控制条的空间，请缩小选区后重试。')
            return
        self.control.move(point); self.control.show()
        self.last = None; self.unchanged = 0; self.height = 0
        self.target = None
        self.notches = 1
        QtCore.QTimer.singleShot(350, self.start_sampling)

    def grab(self):
        origin = self.screen.geometry().topLeft()
        r = self.rect.translated(-origin)
        pix = self.screen.grabWindow(0, r.x(), r.y(), r.width(), r.height())
        image = pix.toImage().convertToFormat(QtGui.QImage.Format_RGB32)
        image.setDevicePixelRatio(1.0)
        return image

    def start_sampling(self):
        if not self.capturing: return
        self.last = self.grab()
        if self.last.isNull():
            self.stop_with_message('无法读取选区画面。'); return
        self.parts = [self.last]; self.height = self.last.height()
        self.target = wheel_target(self.screen, self.rect)
        self.scroll()

    def scroll(self):
        if not self.capturing: return
        self.progress.setText(f'采集中 · {len(self.parts)} 帧')
        if not post_wheel(self.target, self.notches):
            self.stop_with_message('无法向目标窗口发送滚动消息，请检查目标窗口权限。')
            return
        self.timer.start(350)

    def sample(self):
        if not self.capturing: return
        image = self.grab()
        shift = find_shift(self.last, image) if not image.isNull() else None
        if shift is None:
            self.stop_with_message('画面变化过大或内容重复，无法可靠拼接。'); return
        if shift == 0:
            self.unchanged += 1
            if self.unchanged >= 3:
                if len(self.parts) == 1:
                    self.stop_with_message('画面没有滚动，可能已在底部，或目标程序没有响应滚轮。')
                else:
                    self.complete()
                return
        else:
            self.unchanged = 0
            # Estimate the target application's response per notch. Keep a
            # substantial overlap for matching, and cap the increase at 3.
            distance_per_notch = shift / self.notches
            self.notches = max(1, min(3, int(image.height() * .42 / max(1, distance_per_notch))))
            if shift >= image.height():
                self.stop_with_message('画面滚动过大，无法可靠拼接。'); return
            part = image.copy(0, image.height() - shift, image.width(), shift)
            if part.isNull():
                self.stop_with_message('无法分配图片内存。'); return
            self.parts.append(part)
            self.height += shift
            self.last = image
        self.scroll()

    def stop_with_message(self, message):
        self.timer.stop()
        self.progress.setText('已暂停')
        choice = QtWidgets.QMessageBox.question(self.control, '长截图已停止', message + '\n是否保存已采集的内容？', QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes)
        if choice == QtWidgets.QMessageBox.Yes: self.complete()
        else: self.finish_capture()

    def complete(self):
        if not self.capturing: return
        self.timer.stop()
        if not self.parts:
            self.finish_capture(); return
        try:
            image = QtGui.QImage(self.parts[0].width(), self.height, QtGui.QImage.Format_RGB32)
        except (MemoryError, OverflowError):
            image = QtGui.QImage()
        if image.isNull():
            self.progress.setText('内存不足，无法合成图片')
            QtWidgets.QMessageBox.warning(self.control, '无法保存', '内存不足，已保留当前采集数据，请关闭其他程序后重试。')
            return
        painter = QtGui.QPainter(image)
        y = 0
        for part in self.parts:
            painter.drawImage(0, y, part); y += part.height()
        painter.end()
        self.pending = image
        self.finish_capture()
        self.save_pending()

    def save_pending(self):
        path = Path(self.directory.text())
        try:
            path.mkdir(parents=True, exist_ok=True)
            name = datetime.datetime.now().strftime('长截图-%Y%m%d-%H%M%S-%f') + '.png'
            destination = path / name
            if not self.pending.save(str(destination), 'PNG'):
                raise OSError('无法写入图片')
        except OSError as exc:
            new_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, f'保存失败：{exc}，请选择其他位置', str(path / '长截图.png'), 'PNG 图片 (*.png)')
            if not new_path or not self.pending.save(new_path, 'PNG'):
                self.status.setText('图片尚未保存，可点击“保存未保存的截图”重试。')
                self.retry.show(); return
            destination = Path(new_path)
        self.pending = None
        self.retry.hide()
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle('长截图已保存'); box.setText('已保存到：\n' + str(destination))
        open_image = box.addButton('打开图片', QtWidgets.QMessageBox.ActionRole)
        open_folder = box.addButton('打开文件夹', QtWidgets.QMessageBox.ActionRole)
        box.addButton('关闭', QtWidgets.QMessageBox.AcceptRole)
        box.exec()
        if box.clickedButton() == open_image: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(destination)))
        elif box.clickedButton() == open_folder: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(destination.parent)))

    def finish_capture(self, pixmap=None):
        if not self.capturing: return
        self.capturing = False; self.timer.stop()
        for overlay in self.overlays:
            overlay.releaseMouse(); overlay.hide(); overlay.deleteLater()
        self.overlays = []; self.frames = []
        if hasattr(self, 'control'):
            self.control.hide(); self.control.deleteLater(); del self.control
        for window in self.previous_windows:
            window.show()
        self.parts = []

    def shutdown(self):
        self.finish_capture()
        if self.hotkey:
            self.hotkey.close()
            QtWidgets.QApplication.instance().removeNativeEventFilter(self.hotkey)
            self.hotkey = None
