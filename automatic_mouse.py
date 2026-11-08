"""Automatic mouse page, ported from the user's original Tk tool."""
import ctypes
import threading
from PySide6 import QtCore, QtWidgets

class StepSpinBox(QtWidgets.QDoubleSpinBox):
    """Explicit arrow hit targets avoid native subcontrol/QSS overlap."""
    def __init__(self):
        super().__init__()
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.setMinimumHeight(30)
        self.setStyleSheet('QDoubleSpinBox {padding-right:28px;}')
        self.up_button=QtWidgets.QToolButton(self)
        self.down_button=QtWidgets.QToolButton(self)
        for button, symbol, callback in ((self.up_button,'▴',self.stepUp),(self.down_button,'▾',self.stepDown)):
            button.setText(symbol);button.setAutoRepeat(True)
            button.setFocusPolicy(QtCore.Qt.NoFocus)
            button.setStyleSheet('QToolButton{background:#dbe7f5;border:0;border-left:1px solid #a6bdd9;color:#203b60;padding:0;} QToolButton:hover{background:#b0c9eb;} QToolButton:pressed{background:#91b3e0;} QToolButton:disabled{color:#8b9bb1;background:#e4eaf2;}')
            button.clicked.connect(callback)
        self.up_button.setToolTip('增加');self.down_button.setToolTip('减少')
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'up_button'):
            width=round(24*float(self.property('uiScale') or 1.0))
            half=(self.height()-2)//2
            self.up_button.setGeometry(self.width()-width-1,1,width,half)
            self.down_button.setGeometry(self.width()-width-1,1+half,width,self.height()-2-half)

MODES = ['左键连击', '右键连击', '中键连击', '左键长按', '右键长按', '中键长按']
HOTKEYS = [('（无）', 0), ('左 Alt', 0xA4), ('右 Alt', 0xA5), ('退格', 0x08),
           ('Caps Lock', 0x14), ('左 Ctrl', 0xA2), ('右 Ctrl', 0xA3), ('Delete', 0x2E),
           ('Enter', 0x0D), ('Esc', 0x1B), ('Page Down', 0x22), ('Page Up', 0x21),
           ('Print Screen', 0x2C), ('右 Shift', 0xA1), ('空格', 0x20), ('Tab', 0x09)]

class WindowsMouse:
    FLAGS = {'left': (0x0002, 0x0004), 'right': (0x0008, 0x0010), 'middle': (0x0020, 0x0040)}
    def __init__(self):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.user.mouse_event.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]
        self.user.mouse_event.restype = None
        self.user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user.GetAsyncKeyState.restype = ctypes.c_short
    def down(self, button):
        self.user.mouse_event(self.FLAGS[button][0], 0, 0, 0, 0)
    def up(self, button):
        self.user.mouse_event(self.FLAGS[button][1], 0, 0, 0, 0)
    def pressed(self, key):
        return bool(key and self.user.GetAsyncKeyState(key) & 0x8000)

class MouseEngine(QtCore.QObject):
    finished = QtCore.Signal(str)
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.cancel = threading.Event()
        self.thread = None
    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()
    def start(self, mode, amount, gap):
        if self.running: return False
        self.cancel.clear()
        self.thread = threading.Thread(target=self.run, args=(mode,amount,gap), daemon=True)
        self.thread.start()
        return True
    def run(self, mode, amount, gap):
        button = ('left','right','middle')[mode % 3]
        held = False
        error = ''
        try:
            while not self.cancel.is_set():
                if mode < 3:
                    for _ in range(int(amount)):
                        if self.cancel.is_set(): break
                        held = True; self.backend.down(button)
                        self.backend.up(button); held = False
                else:
                    held = True; self.backend.down(button)
                    interrupted = self.cancel.wait(amount)
                    self.backend.up(button); held = False
                    if interrupted: break
                # Even a zero interval yields briefly and remains interruptible.
                if self.cancel.wait(max(gap,0.0001)): break
        except Exception as exc:
            error = str(exc)
        finally:
            if held:
                try: self.backend.up(button)
                except Exception: pass
            self.finished.emit(error)
    def stop(self):
        self.cancel.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=1)

class AutomaticMousePage(QtWidgets.QWidget):
    def __init__(self, dock, backend=None):
        super().__init__()
        self.dock = dock
        self.backend = backend or WindowsMouse()
        self.engine = MouseEngine(self.backend)
        self.engine.finished.connect(self.on_finished)
        self.active = False
        self.feature_enabled = False
        body = QtWidgets.QVBoxLayout(self)
        body.setContentsMargins(14,16,14,14); body.setSpacing(12)
        title = QtWidgets.QLabel('自动鼠标'); title.setStyleSheet('font-size:16px;font-weight:600;')
        body.addWidget(title)
        self.enable_switch=QtWidgets.QCheckBox('启用自动鼠标')
        self.enable_switch.setToolTip('记住上次启用状态；关闭后停止操作并禁用启停热键')
        body.addWidget(self.enable_switch)
        self.status = QtWidgets.QLabel('已停止')
        body.addWidget(self.status)
        form = QtWidgets.QFormLayout(); form.setVerticalSpacing(12)
        self.mode = QtWidgets.QComboBox(); self.mode.addItems(MODES)
        self.amount = StepSpinBox(); self.amount.setRange(1,10000)
        self.gap = StepSpinBox(); self.gap.setRange(0,86400); self.gap.setDecimals(4); self.gap.setSingleStep(.01); self.gap.setSuffix(' 秒')
        self.hotkey = QtWidgets.QComboBox()
        for label, code in HOTKEYS: self.hotkey.addItem(label,code)
        self.amount_label = QtWidgets.QLabel()
        form.addRow('操作',self.mode); form.addRow(self.amount_label,self.amount)
        form.addRow('每轮间隔',self.gap); form.addRow('启停热键',self.hotkey)
        body.addLayout(form)
        row = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton('开始')
        self.stop_button = QtWidgets.QPushButton('停止')
        for button in (self.start_button,self.stop_button): button.setMinimumHeight(36); row.addWidget(button)
        body.addLayout(row)
        hint = QtWidgets.QLabel('在鼠标当前位置执行操作。\n松开启停热键，可在游戏中切换运行状态。\n连击：每轮点击指定次数，再等待间隔。\n长按：按住指定秒数、松开，再等待间隔。')
        hint.setWordWrap(True); hint.setStyleSheet('color:#718096;')
        body.addWidget(hint); body.addStretch()
        saved = dock.store.data['settings'].get('automatic_mouse',{})
        self.mode.setCurrentIndex(max(0,min(5,int(saved.get('mode',1)))))
        self.update_mode()
        self.amount.setValue(float(saved.get('amount',1)))
        self.gap.setValue(float(saved.get('gap',.01)))
        index=self.hotkey.findData(saved.get('hotkey',0x2E)); self.hotkey.setCurrentIndex(max(0,index))
        self.key_was_down = self.backend.pressed(self.hotkey.currentData())
        self.mode.currentIndexChanged.connect(self.mode_changed)
        self.amount.valueChanged.connect(self.save_settings)
        self.gap.valueChanged.connect(self.save_settings)
        self.hotkey.currentIndexChanged.connect(self.hotkey_changed)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        self.timer = QtCore.QTimer(self); self.timer.setInterval(15)
        self.timer.timeout.connect(self.poll_key)
        self.enable_switch.setChecked(bool(saved.get('enabled', False)))
        self.set_feature_enabled(self.enable_switch.isChecked())
        self.enable_switch.toggled.connect(self.feature_toggled)
    def feature_toggled(self, enabled):
        self.set_feature_enabled(enabled)
        self.save_settings()
    def set_feature_enabled(self,enabled):
        self.feature_enabled=enabled
        if enabled:
            self.key_was_down=self.backend.pressed(self.hotkey.currentData())
            self.timer.start()
        else:
            self.timer.stop();self.engine.stop();self.active=False;self.key_was_down=False
        self.set_running_ui(self.active)
    def update_mode(self):
        hold = self.mode.currentIndex() >= 3
        self.amount_label.setText('每次按住' if hold else '每轮次数')
        self.amount.setDecimals(3 if hold else 0)
        self.amount.setRange(.001 if hold else 1,86400 if hold else 10000)
        self.amount.setSuffix(' 秒' if hold else ' 次')
    def mode_changed(self):
        self.update_mode(); self.save_settings()
    def save_settings(self):
        settings=self.dock.store.data['settings'].setdefault('automatic_mouse',{})
        settings.update(mode=self.mode.currentIndex(),amount=self.amount.value(),gap=self.gap.value(),hotkey=self.hotkey.currentData(),enabled=self.enable_switch.isChecked())
        self.dock.save()
    def hotkey_changed(self):
        self.key_was_down = self.backend.pressed(self.hotkey.currentData()); self.save_settings()
    def poll_key(self):
        if not self.feature_enabled: return
        down = self.backend.pressed(self.hotkey.currentData())
        released = self.key_was_down and not down
        self.key_was_down = down
        if released and QtWidgets.QApplication.activeModalWidget() is None and QtWidgets.QApplication.activePopupWidget() is None:
            self.stop() if self.active else self.start()
    def start(self):
        if not self.feature_enabled or self.active or self.engine.running: return
        self.save_settings()
        self.active = True; self.set_running_ui(True)
        self.engine.start(self.mode.currentIndex(),self.amount.value(),self.gap.value())
    def set_running_ui(self, active):
        self.status.setText('未启用' if not self.feature_enabled else ('运行中 · '+self.mode.currentText() if active else '已停止'))
        self.status.setStyleSheet('color:#21834d;font-weight:600;' if active else 'color:#718096;')
        self.start_button.setEnabled(self.feature_enabled and not active);self.stop_button.setEnabled(self.feature_enabled)
        for field in (self.mode,self.amount,self.gap,self.hotkey): field.setEnabled(self.feature_enabled and not active)
    def stop(self):
        self.engine.stop(); self.active=False;self.set_running_ui(False)
    def on_finished(self,error):
        if not self.engine.running:
            self.active=False;self.set_running_ui(False)
            if error: self.status.setText('已停止：'+error)
    def shutdown(self):
        self.timer.stop();self.stop()
