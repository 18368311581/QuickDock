"""Application settings and built-in user guide."""
import subprocess
from PySide6 import QtCore, QtWidgets
from screen_pins import HOTKEYS
from ui_scale import scale_tree
from startup import StartupManager
from responsive import AdaptiveDialog

class SettingsDialog(AdaptiveDialog):
    def __init__(self, dock):
        super().__init__(dock)
        self.dock = dock
        self.setWindowTitle('QuickDock 设置')
        self.resize(520, 270)
        body = QtWidgets.QVBoxLayout(self)
        general = QtWidgets.QWidget(); form = QtWidgets.QFormLayout(general)
        form.setContentsMargins(16, 18, 16, 16)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        self.hotkey = QtWidgets.QComboBox()
        for title, mods, key in HOTKEYS: self.hotkey.addItem(title, (mods, key))
        current = dock.store.data['settings'].get('launcher_hotkey', 'Ctrl + Alt + Q')
        self.hotkey.setCurrentIndex(max(0, self.hotkey.findText(current)))
        form.addRow('唤出快捷入口', self.hotkey)
        hint = QtWidgets.QLabel('全局生效：展开／收起大窗口；展开时回到快捷入口。')
        hint.setWordWrap(True); form.addRow(hint)
        self.opacity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity.setRange(30, 100); self.opacity.setSingleStep(1); self.opacity.setPageStep(5)
        self.opacity.setValue(round(dock.windowOpacity()*100))
        self.opacity_value = QtWidgets.QLabel(f'{self.opacity.value()} %')
        self.opacity_value.setFixedWidth(52)
        self.opacity.valueChanged.connect(lambda value: self.opacity_value.setText(f'{value} %'))
        opacity_row = QtWidgets.QHBoxLayout()
        opacity_row.addWidget(self.opacity, 1); opacity_row.addWidget(self.opacity_value)
        form.addRow('大窗口不透明度', opacity_row)
        self.interface_scale = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.interface_scale.setRange(75, 150); self.interface_scale.setSingleStep(5); self.interface_scale.setPageStep(10)
        self.interface_scale.setValue(round(dock.ui_scale*100))
        self.scale_value = QtWidgets.QLabel(f'{self.interface_scale.value()} %')
        self.scale_value.setFixedWidth(52)
        self.interface_scale.valueChanged.connect(lambda value: self.scale_value.setText(f'{value} %'))
        scale_row = QtWidgets.QHBoxLayout()
        scale_row.addWidget(self.interface_scale,1); scale_row.addWidget(self.scale_value)
        form.addRow('界面大小', scale_row)
        scale_hint = QtWidgets.QLabel('同步调整文字、按钮和间距；75%～150%，100% 为原大小。')
        scale_hint.setWordWrap(True); form.addRow(scale_hint)
        self.mini = QtWidgets.QCheckBox('显示桌面小窗')
        self.mini.setChecked(dock.show_mini.isChecked()); form.addRow(self.mini)
        self.startup_manager = StartupManager(dock.store.root)
        self.startup = QtWidgets.QCheckBox('登录 Windows 后自动启动')
        self.startup_error = None
        try: self.startup.setChecked(self.startup_manager.is_enabled())
        except OSError as exc:
            self.startup.setEnabled(False); self.startup_error = str(exc)
            self.startup.setToolTip('无法读取开机启动状态：'+str(exc))
        form.addRow('开机启动', self.startup)
        note = QtWidgets.QLabel('开机启动仅对当前用户生效，保存后应用。\n自动鼠标和截图贴图的开关、热键在各自页面设置。')
        note.setWordWrap(True); form.addRow(note)
        body.addWidget(general)
        body.addStretch()
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.Save).setText('保存')
        buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText('取消')
        for button in buttons.buttons(): button.setMinimumSize(100, 34)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); body.addWidget(buttons)
        scale_tree(self, dock.ui_scale)
        preferred = QtCore.QSize(dock.ui_px(520), max(dock.ui_px(310), self.sizeHint().height()))
        self.make_scrollable(buttons, preferred)
    def accept(self):
        settings = self.dock.store.data['settings']
        old_title = settings.get('launcher_hotkey', 'Ctrl + Alt + Q')
        title = self.hotkey.currentText()
        mods, key = self.hotkey.currentData()
        if title != old_title and key and not self.dock.launcher_hotkey.register(mods, key):
            self.dock.apply_launcher_hotkey()
            QtWidgets.QMessageBox.warning(self, '快捷键不可用', '这个组合键已被占用或不受支持，请选择其他组合键。')
            return
        startup_snapshot = None
        try:
            if self.startup_error is None and self.startup.isChecked() != self.startup_manager.is_enabled():
                startup_snapshot = self.startup_manager.snapshot()
                self.startup_manager.set_enabled(self.startup.isChecked())
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.dock.apply_launcher_hotkey()
            QtWidgets.QMessageBox.warning(self, '开机启动设置失败', str(exc))
            return
        previous = dict(settings)
        settings['launcher_hotkey'] = title
        settings['window_opacity'] = self.opacity.value()/100
        settings['mini_visible'] = self.mini.isChecked()
        settings['ui_scale'] = self.interface_scale.value()/100
        if not self.dock.save():
            if startup_snapshot is not None:
                try: self.startup_manager.restore(startup_snapshot)
                except OSError as exc: QtWidgets.QMessageBox.warning(self, '启动项恢复失败', str(exc))
            self.dock.store.data['settings'] = previous
            self.dock.apply_launcher_hotkey(); return
        self.dock.apply_launcher_hotkey()
        self.dock.setWindowOpacity(settings['window_opacity'])
        if abs(self.dock.ui_scale-settings['ui_scale']) > .0001:
            self.dock.apply_ui_scale(settings['ui_scale'])
        blocker = QtCore.QSignalBlocker(self.dock.show_mini)
        self.dock.show_mini.setChecked(settings['mini_visible'])
        del blocker
        self.dock.mini.setVisible(settings['mini_visible'])
        if not settings['mini_visible']: self.dock.hide()
        super().accept()


class HelpDialog(AdaptiveDialog):
    def __init__(self, dock):
        super().__init__(dock)
        self.setWindowTitle('QuickDock 使用说明')
        self.resize(600, 560)
        body = QtWidgets.QVBoxLayout(self)
        scroll = QtWidgets.QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.guide_label = QtWidgets.QLabel()
        self.guide_label.setTextFormat(QtCore.Qt.RichText)
        self.guide_label.setWordWrap(True)
        self.guide_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.guide_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.guide_label.setContentsMargins(18, 12, 18, 20)
        self.guide_label.setMinimumWidth(0)
        self.guide_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        try: self.guide_label.setText((dock.store.root/'使用说明.html').read_text(encoding='utf-8'))
        except OSError: self.guide_label.setText('<h3>使用说明</h3><p>未找到使用说明.html，请将它放在程序目录下。</p>')
        scroll.setWidget(self.guide_label)
        body.addWidget(scroll)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.button(QtWidgets.QDialogButtonBox.Close).setText('关闭')
        buttons.button(QtWidgets.QDialogButtonBox.Close).setMinimumSize(100, 34)
        buttons.rejected.connect(self.reject)
        body.addWidget(buttons)
        self.use_existing_scroll(QtCore.QSize(600,560))
