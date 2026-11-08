import sys, os, json, uuid, shutil, re, difflib, urllib.request, urllib.parse, math, copy
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from automatic_mouse import AutomaticMousePage
from single_instance import SingleInstance
from screen_pins import ScreenPinsPage, HOTKEYS
from long_capture import LongCapturePage
from launcher_hotkey import LauncherHotkey, foreground_window
from settings_dialog import SettingsDialog, HelpDialog
from pinyin_search import pinyin_score, aliases
from ui_scale import scale_tree
from responsive import AdaptiveDialog, ScreenWatcher, available_area, scroll_page

ROOT = Path(__file__).resolve().parent

def builtin_icon(kind):
    pixmap = QtGui.QPixmap(64,64); pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap); painter.setRenderHint(QtGui.QPainter.Antialiasing)
    if kind == 'star':
        points = []
        for i in range(10):
            angle = -math.pi/2 + i*math.pi/5
            radius = 27 if i%2==0 else 12
            points.append(QtCore.QPointF(32+radius*math.cos(angle),32+radius*math.sin(angle)))
        painter.setPen(QtGui.QPen(QtGui.QColor('#d99412'),2))
        painter.setBrush(QtGui.QColor('#ffd44a')); painter.drawPolygon(QtGui.QPolygonF(points))
    elif kind == 'globe':
        painter.setPen(QtGui.QPen(QtGui.QColor('#3882cf'),3))
        painter.setBrush(QtGui.QColor('#e7f3ff')); painter.drawEllipse(7,7,50,50)
        painter.setBrush(QtCore.Qt.NoBrush); painter.drawEllipse(21,7,22,50)
        painter.drawLine(7,32,57,32); painter.drawLine(12,19,52,19); painter.drawLine(12,45,52,45)
    elif kind == 'link':
        painter.setPen(QtGui.QPen(QtGui.QColor('#3882cf'),5,QtCore.Qt.SolidLine,QtCore.Qt.RoundCap))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.translate(32,32); painter.rotate(-40)
        painter.drawRoundedRect(QtCore.QRectF(-27,-10,32,20),10,10)
        painter.drawRoundedRect(QtCore.QRectF(-5,-10,32,20),10,10)
        painter.drawLine(-8,0,8,0)
    painter.end()
    return QtGui.QIcon(pixmap)

def normalize(value):
    value = value.strip().strip('"')
    if re.match(r'^https?://', value, re.I):
        return value
    if value.lower().startswith('www.'):
        return 'https://' + value
    if value.lower().startswith('file:'):
        return QtCore.QUrl(value).toLocalFile()
    return os.path.expandvars(os.path.expanduser(value))

def suggested_name(target):
    if target.startswith(('https://', 'http://')):
        return urllib.parse.urlparse(target).netloc
    return Path(target).stem or target

def special_target(value):
    return value.lower().startswith(('http://','https://','shell:'))

def portable_target(value, root):
    value=normalize(value)
    if not value or special_target(value): return value
    path=Path(value)
    if path.is_absolute():
        try: return str(path.resolve().relative_to(Path(root).resolve()))
        except ValueError: pass
    return value

def resolve_local(value, root, command=False):
    value=normalize(value)
    if not value or special_target(value): return value
    path=Path(value)
    if path.is_absolute(): return str(path)
    local=(Path(root)/path).resolve()
    # Keep bare executable names usable through Windows PATH, e.g. pwsh.exe.
    if command and not local.exists() and len(path.parts)==1 and path.suffix.lower() in ('.exe','.cmd','.bat','.com'):
        return shutil.which(value) or value
    return str(local)

def score(name, description, target, query):
    q = query.casefold().strip()
    n = name.casefold()
    if not q:
        return 0
    return (100 if n == q else 0) + (50 if n.startswith(q) else 0) + (30 if q in n else 0) + 20 * difflib.SequenceMatcher(None, q, n).ratio() + (5 if q in (description + ' ' + target).casefold() else 0) + pinyin_score(name, q)

class RankedEntryItem(QtWidgets.QListWidgetItem):
    def __lt__(self, other):
        return self.sort_key < other.sort_key

class Store:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.icons = self.root / 'icons'
        self.icons.mkdir(exist_ok=True)
        self.path = self.root / 'shortcuts.json'
        self.data = {'version': 1, 'items': [], 'settings': {}}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.data.get('items'), list):
                raise ValueError('快捷方式文件格式不正确')
        self.baseline = copy.deepcopy(self.data)
    @staticmethod
    def merge(base, local, remote):
        """Apply only local changes; retain unrelated external changes."""
        if local == base: return copy.deepcopy(remote)
        if all(isinstance(x,dict) for x in (base,local,remote)):
            result=copy.deepcopy(remote)
            for key in base.keys() | local.keys():
                if key not in local:
                    result.pop(key,None)
                elif key not in base:
                    result[key]=copy.deepcopy(local[key])
                elif key in remote:
                    result[key]=Store.merge(base[key],local[key],remote[key])
                elif local[key] != base[key]:
                    result[key]=copy.deepcopy(local[key])
            return result
        return copy.deepcopy(local)
    def sync(self):
        if not self.path.exists(): return False
        remote=json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(remote.get('items'),list): raise ValueError('快捷方式文件格式不正确')
        if remote==self.baseline: return False
        base,local=copy.deepcopy(self.baseline),copy.deepcopy(self.data)
        for record in (base,local,remote):
            record['items']={x['id']:x for x in record['items']}
        merged=self.merge(base,local,remote)
        merged['items']=list(merged['items'].values())
        remote['items']=list(remote['items'].values())
        changed=merged!=self.data
        self.data=merged;self.baseline=copy.deepcopy(remote)
        return changed
    def save(self):
        self.sync()
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        if self.path.exists():
            shutil.copy2(self.path, self.path.with_suffix('.json.bak'))
        os.replace(temp, self.path)
        self.baseline=copy.deepcopy(self.data)

class Editor(AdaptiveDialog):
    def __init__(self, dock, item=None, target=''):
        super().__init__(dock)
        self.dock = dock
        self.item = dict(item or {})
        self.icon_path = self.item.get('icon', '')
        self.setAcceptDrops(True)
        self.setWindowTitle('编辑快捷入口' if item else '添加快捷入口')
        self.resize(500, 245)
        form = QtWidgets.QFormLayout(self)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        self.drop_hint = QtWidgets.QLabel('将文件、文件夹或快捷方式拖到此窗口，自动识别')
        self.drop_hint.setAlignment(QtCore.Qt.AlignCenter)
        self.drop_hint.setWordWrap(True)
        self.drop_hint.setStyleSheet('padding:5px;color:#536981;')
        form.addRow(self.drop_hint)
        self.name = QtWidgets.QLineEdit(self.item.get('name', ''))
        self.target = QtWidgets.QLineEdit(self.item.get('target', target))
        self.description = QtWidgets.QLineEdit(self.item.get('description', ''))
        self.arguments = QtWidgets.QLineEdit(self.item.get('arguments', ''))
        self.cwd = QtWidgets.QLineEdit(self.item.get('cwd', ''))
        for field in (self.name, self.target, self.description, self.arguments, self.cwd):
            field.setAcceptDrops(False)
        self.preview = QtWidgets.QPushButton('选择图标…')
        self.preview.clicked.connect(self.choose_icon)
        form.addRow('名称', self.name)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.target)
        file_button = QtWidgets.QPushButton('文件…')
        folder_button = QtWidgets.QPushButton('文件夹…')
        self.file_button, self.folder_button = file_button, folder_button
        for widget in (self.target, file_button, folder_button): widget.setFixedHeight(30)
        file_button.setMinimumWidth(65); folder_button.setMinimumWidth(75)
        file_button.clicked.connect(self.choose_file)
        folder_button.clicked.connect(self.choose_folder)
        row.addWidget(file_button); row.addWidget(folder_button)
        form.addRow('地址', row)
        form.addRow('简介', self.description)
        form.addRow('图标', self.preview)
        tip = QtWidgets.QLabel('地址就是文件/文件夹的位置，或者网页链接。\n拖入或选择文件后会自动填写名称和图标；简介可以留空。')
        tip.setWordWrap(True); form.addRow(tip)
        self.advanced_toggle = QtWidgets.QToolButton()
        self.advanced_toggle.setText('高级选项'); self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.advanced_toggle.setArrowType(QtCore.Qt.RightArrow)
        self.advanced = QtWidgets.QWidget()
        advanced_form = QtWidgets.QFormLayout(self.advanced)
        advanced_form.setContentsMargins(0, 0, 0, 0)
        for field in (self.arguments, self.cwd): field.setFixedHeight(30)
        advanced_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        advanced_form.setVerticalSpacing(6)
        advanced_form.addRow('程序参数', self.arguments)
        advanced_form.addRow('工作目录', self.cwd)
        advanced_form.addRow(QtWidgets.QLabel('仅特殊命令需要填写；普通快捷方式不需要。'))
        policy = self.advanced.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.advanced.setSizePolicy(policy)
        form.addRow(self.advanced_toggle); form.addRow(self.advanced)
        self.advanced_toggle.toggled.connect(self.toggle_advanced)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        self.save_button = buttons.button(QtWidgets.QDialogButtonBox.Save)
        self.cancel_button = buttons.button(QtWidgets.QDialogButtonBox.Cancel)
        self.save_button.setText('保存'); self.cancel_button.setText('取消')
        for button in (self.save_button, self.cancel_button): button.setMinimumSize(110,36)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.target.editingFinished.connect(self.autofill)
        self.autofill()
        scale_tree(self, dock.ui_scale)
        # Polish visible advanced fields before computing the reserved geometry.
        self.ensurePolished(); self.advanced.ensurePolished()
        advanced_form.invalidate(); advanced_form.activate()
        self.advanced.setFixedHeight(advanced_form.sizeHint().height())
        form.invalidate(); form.activate()
        preferred = QtCore.QSize(max(dock.ui_px(540), self.sizeHint().width()), max(dock.ui_px(360), self.sizeHint().height()))
        self.make_scrollable(buttons, preferred)
        self.advanced.hide()
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self); painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor('#9bafc7'),1,QtCore.Qt.DashLine))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(4.5,4.5,-4.5,-4.5),6,6)
    def toggle_advanced(self, visible):
        self.advanced.setVisible(visible)
        self.advanced_toggle.setArrowType(QtCore.Qt.DownArrow if visible else QtCore.Qt.RightArrow)
        self.advanced.layout().invalidate()
        self.advanced.layout().activate()
        self.layout().activate()
    def autofill(self):
        target = portable_target(self.target.text(),self.dock.store.root)
        self.target.setText(target)
        if not self.name.text().strip():
            self.name.setText(suggested_name(resolve_local(target,self.dock.store.root)))
        self.preview.setIcon(self.dock.entry_icon({'target': target, 'icon': self.icon_path}))
    def choose_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, '选择文件或软件', str(self.dock.store.root), options=QtWidgets.QFileDialog.DontResolveSymlinks)
        if path: self.set_target(path)
    def choose_folder(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, '选择文件夹', str(self.dock.store.root))
        if path: self.set_target(path)
    def set_target(self, target):
        previous = self.target.text()
        if not self.name.text().strip() or self.name.text() == suggested_name(previous):
            self.name.setText(suggested_name(normalize(target)))
        self.target.setText(portable_target(target,self.dock.store.root))
        self.icon_path = ''
        self.autofill()
    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls() or (mime.hasText() and mime.text().strip()):
            event.acceptProposedAction()
    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls():
            url = mime.urls()[0]
            target = url.toLocalFile() if url.isLocalFile() else url.toString()
        else:
            target = mime.text().strip()
        if target:
            self.set_target(target)
            event.acceptProposedAction()
    def choose_icon(self):
        picker = AdaptiveDialog(self)
        picker.setWindowTitle('选择图标')
        layout = QtWidgets.QVBoxLayout(picker)
        layout.addWidget(QtWidgets.QLabel('选择内置图标，或使用自己的图片'))
        grid = QtWidgets.QGridLayout(); layout.addLayout(grid)
        options = [('文件', 'SP_FileIcon'), ('文件夹', 'SP_DirIcon'), ('软件', 'SP_ComputerIcon'),
                   ('网页', 'globe'), ('收藏', 'star'), ('文档', 'SP_FileDialogDetailedView'),
                   ('图片', 'SP_FileDialogContentsView'), ('音乐', 'SP_MediaVolume'), ('视频', 'SP_MediaPlay'),
                   ('工具', 'SP_FileDialogInfoView'), ('命令', 'SP_CommandLink'), ('下载', 'SP_ArrowDown'),
                   ('链接', 'link')]
        for index, (title, identifier) in enumerate(options):
            icon = builtin_icon(identifier) if identifier in ('globe','star','link') else self.style().standardIcon(getattr(QtWidgets.QStyle, identifier))
            button = QtWidgets.QToolButton()
            button.setText(title); button.setIcon(icon); button.setIconSize(QtCore.QSize(28,28))
            button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon); button.setFixedSize(75,65)
            button.clicked.connect(lambda checked=False, selected=icon: (self.apply_icon(selected), picker.accept()))
            grid.addWidget(button,index//4,index%4)
        actions_widget = QtWidgets.QWidget()
        actions = QtWidgets.QHBoxLayout(actions_widget); layout.addWidget(actions_widget)
        automatic = QtWidgets.QPushButton('自动识别')
        automatic.clicked.connect(lambda: (setattr(self,'icon_path',''),self.autofill(),picker.accept()))
        browse = QtWidgets.QPushButton('从图片选择…')
        browse.clicked.connect(lambda: self.browse_icon(picker))
        actions.addWidget(automatic); actions.addWidget(browse)
        scale_tree(picker, self.dock.ui_scale)
        picker.make_scrollable(actions_widget, picker.sizeHint())
        picker.exec()
    def browse_icon(self, picker):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, '选择图标', str(self.dock.store.root), '图片 (*.png *.ico *.jpg *.jpeg *.svg *.webp)')
        if path:
            icon = QtGui.QIcon(path)
            if icon.isNull(): return
            self.apply_icon(icon); picker.accept()
    def apply_icon(self, icon):
        destination = self.dock.store.icons / (uuid.uuid4().hex + '.png')
        if icon.pixmap(64, 64).save(str(destination), 'PNG'):
            self.icon_path = 'icons/' + destination.name
            self.autofill()
    def accept(self):
        if not self.name.text().strip() or not self.target.text().strip():
            QtWidgets.QMessageBox.warning(self, '信息不完整', '请填写名称和地址。'); return
        self.item.update(id=self.item.get('id', uuid.uuid4().hex), name=self.name.text().strip(), target=portable_target(self.target.text(),self.dock.store.root), description=self.description.text().strip(), icon=self.icon_path, arguments=self.arguments.text().strip(), cwd=portable_target(self.cwd.text(),self.dock.store.root))
        super().accept()

class Mini(QtWidgets.QPushButton):
    def __init__(self, dock):
        super().__init__('')
        self.dock = dock
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setFixedSize(32, 32)
        self.setAcceptDrops(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip('快捷入口 · 点击展开/收起；右键打开菜单')
        self.setStyleSheet('QPushButton {background:transparent;border:0;}')
        self.clicked.connect(dock.toggle)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda p: dock.menu.exec(self.mapToGlobal(p)))
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor('#aebed0'), 1))
        painter.setBrush(QtGui.QColor('#e4edf8' if self.underMouse() else '#f4f7fc'))
        # Three square corners and a larger rounded bottom-left corner.
        w, h, radius = float(self.width()), float(self.height()), 12.0
        path = QtGui.QPainterPath()
        path.moveTo(0, 0); path.lineTo(w, 0); path.lineTo(w, h)
        path.lineTo(radius, h); path.quadTo(0, h, 0, h-radius)
        path.lineTo(0, 0); path.closeSubpath()
        painter.drawPath(path)
        icon = QtGui.QIcon(str(ROOT / 'assets' / 'app-icon.ico'))
        icon.paint(painter, QtCore.QRect(5, 4, 23, 23))
    def enterEvent(self, event):
        self.update(); super().enterEvent(event)
    def leaveEvent(self, event):
        self.update(); super().leaveEvent(event)
    def dragEnterEvent(self, event):
        self.dock.dragEnterEvent(event)
    def dropEvent(self, event):
        self.dock.expand()
        self.dock.dropEvent(event)

class Dock(QtWidgets.QWidget):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.ui_scale = max(0.75, min(1.5, float(store.data['settings'].get('ui_scale', 1.0))))
        self.provider = QtWidgets.QFileIconProvider()
        self.network = QNetworkAccessManager(self)
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setWindowTitle('快捷入口')
        self.setWindowOpacity(max(0.30, min(1.0, float(self.store.data['settings'].get('window_opacity', 0.82)))))
        self.resize(420, 640); self.setMinimumSize(360, 350)
        self.setAcceptDrops(True)
        self.setStyleSheet('QWidget{font-family:"Microsoft YaHei UI";font-size:13px;color:#24334a;} QWidget#panel{background:#f3f6fa;border:1px solid #d6deea;border-radius:10px;} QLineEdit{background:white;border:1px solid #ccd6e3;border-radius:7px;padding:9px;} QPushButton{background:#e7edf5;border:0;border-radius:6px;padding:7px 10px;} QPushButton:hover{background:#d5e2f4;} QTabWidget::pane{border:0;} QTabBar::tab{padding:10px 20px;} QTabBar::tab:selected{color:#2563eb;} QListWidget{background:transparent;border:0;} QListWidget::item{background:white;border:1px solid #e0e6ef;border-radius:8px;margin-bottom:7px;}')
        self.setObjectName('panel')
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet(self.styleSheet() + ' QWidget{font-size:11px;} QLineEdit{padding:5px;} QPushButton{padding:3px 5px;border-radius:3px;} QTabBar::tab{padding:5px 10px;} QListWidget::item{background:transparent;border:0;border-bottom:1px solid #e1e7ef;border-radius:0;margin:0;} QListWidget::item:selected{background:#e3edfc;} QListWidget::item:hover{background:#eaf0f8;}')
        self.setStyleSheet(self.styleSheet() + ' QWidget#panel{border:1px solid #718096;border-radius:0;} QTabWidget::pane{border:1px solid #718096;top:-1px;} QTabBar::tab{background:#e5ebf3;border:1px solid #718096;padding:6px 10px;margin:0;} QTabBar::tab:selected{background:#f3f6fa;color:#2563eb;} QPushButton#addEntry{font-size:26px;padding:0;}')
        self.setStyleSheet(self.styleSheet() + '''
            QWidget {color:#1d304d;}
            QWidget#panel {border-color:#526f96;}
            QTabWidget::pane {border-color:#526f96;}
            QTabBar::tab {background:#d5e1f0;border-color:#526f96;color:#314c70;}
            QTabBar::tab:selected {background:#f3f6fa;color:#174f9f;}
            QLineEdit {border-color:#9fb4cf;selection-background-color:#b0c9eb;selection-color:#142e52;}
            QLineEdit:focus {border-color:#4777b3;}
            QComboBox,QDoubleSpinBox {background:#f8fbff;border:1px solid #9fb4cf;border-radius:4px;padding:4px;}
            QPushButton {background:#dbe7f5;border:1px solid #a6bdd9;color:#203b60;}
            QPushButton:hover {background:#b0c9eb;border-color:#678ebf;}
            QPushButton:pressed {background:#91b3e0;border-color:#4777b3;}
            QPushButton:disabled {background:#e4eaf2;border-color:#c3cfdf;color:#8b9bb1;}
            QListWidget::item {border-bottom-color:#bbcbe0;}
            QListWidget::item:selected {background:#bfd3ee;}
            QListWidget::item:hover {background:#d3e2f5;}
        ''')
        self.setStyleSheet(self.styleSheet() + '''
            QTabWidget::pane {border:0;top:0;}
            QTabBar {font-size:13px;font-weight:700;}
            QTabBar::tab {
                border:0;
                border-right:1px solid #526f96;
                border-bottom:1px solid #526f96;
            }
            QTabBar::tab:last {border-right:0;}
            QTabBar::tab:selected {border-bottom:1px solid #f3f6fa;}
        ''')
        # Apply one dropdown-button style to all pages and owned dialogs.
        arrow_path = (ROOT / 'assets' / 'combo-down.svg').as_posix()
        self.setStyleSheet(self.styleSheet() + """
            QComboBox {padding-right:28px;}
            QComboBox::drop-down {
                subcontrol-origin:border; subcontrol-position:top right;
                width:24px; margin:1px;
                background:#dbe7f5; border:0; border-left:1px solid #a6bdd9;
                border-top-right-radius:3px; border-bottom-right-radius:3px;
            }
            QComboBox::drop-down:hover {background:#b0c9eb;}
            QComboBox::drop-down:pressed, QComboBox::drop-down:on {background:#91b3e0;}
            QComboBox::drop-down:disabled {background:#e4eaf2;}
            QComboBox::down-arrow {image:url("ARROW_PATH");width:8px;height:7px;}
        """.replace('ARROW_PATH', arrow_path))
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1); layout.setSpacing(0)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.tabBar().setExpanding(True)
        self.tabs.tabBar().setDrawBase(False)
        page = QtWidgets.QWidget(); body = QtWidgets.QVBoxLayout(page)
        body.setContentsMargins(6, 6, 6, 6); body.setSpacing(4)
        self.search = QtWidgets.QLineEdit(); self.search.setPlaceholderText('搜索名称、简介或地址…'); self.search.setClearButtonEnabled(True)
        search_row = QtWidgets.QHBoxLayout(); search_row.setSpacing(5)
        self.search_symbol = QtWidgets.QLabel()
        self.search_symbol.setFixedSize(25,25)
        search_pixmap = QtGui.QPixmap(22,22); search_pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(search_pixmap); painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor('#536981'), 1.8))
        painter.drawEllipse(QtCore.QRectF(3,3,10,10)); painter.drawLine(QtCore.QPointF(12,12),QtCore.QPointF(18,18)); painter.end()
        self.search_symbol.setPixmap(search_pixmap); self.search_symbol.setAlignment(QtCore.Qt.AlignCenter)
        search_row.addWidget(self.search_symbol)
        search_row.addWidget(self.search, 1)
        body.addLayout(search_row)
        self.list = QtWidgets.QListWidget(); self.list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        body.addWidget(self.list)
        add = QtWidgets.QPushButton('＋'); add.setObjectName('addEntry'); add.setFixedHeight(40)
        self.add_button = add
        add.setToolTip('也可以拖入文件、文件夹、软件快捷方式或网页')
        add.clicked.connect(lambda: self.edit_entry())
        body.addWidget(add)
        self.tabs.addTab(page, '快捷入口')
        self.mouse_page = AutomaticMousePage(self)
        self.tabs.addTab(scroll_page(self.mouse_page), '自动鼠标')
        self.pin_page = ScreenPinsPage(self)
        self.tabs.addTab(scroll_page(self.pin_page), '截图贴图')
        self.long_capture_page = LongCapturePage(self)
        self.tabs.addTab(scroll_page(self.long_capture_page), '长截图')
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.long_capture_page.shutdown)
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.pin_page.shutdown)
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.mouse_page.shutdown)
        layout.addWidget(self.tabs)
        self.search.textChanged.connect(self.rank_search)
        self.search.returnPressed.connect(self.open_selected)
        self.search.installEventFilter(self)
        self.list.itemDoubleClicked.connect(lambda item: self.open_entry(item.data(QtCore.Qt.UserRole)))
        self._escape_pending = False
        self.mini = Mini(self)
        self.anchor_windows()
        self.menu = QtWidgets.QMenu()
        self.show_mini = self.menu.addAction('显示桌面小窗'); self.show_mini.setCheckable(True)
        self.show_mini.setChecked(self.store.data['settings'].get('mini_visible', True))
        self.show_mini.toggled.connect(self.set_mini_visible)
        self.menu.addAction('设置…', self.open_settings)
        self.menu.addAction('使用说明', self.open_help)
        self.menu.addSeparator(); self.menu.addAction('退出软件', self.quit)
        icon = QtGui.QIcon(str(ROOT / 'assets' / 'app-icon.ico'))
        if icon.isNull(): icon = self.style().standardIcon(QtWidgets.QStyle.SP_DirLinkIcon)
        self.setWindowIcon(icon)
        self.tray = QtWidgets.QSystemTrayIcon(icon, self); self.tray.setToolTip('快捷入口'); self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda reason: self.toggle() if reason == QtWidgets.QSystemTrayIcon.DoubleClick else None)
        self.tray.show(); self.mini.setVisible(self.show_mini.isChecked())
        self.launcher_hotkey = LauncherHotkey(self.activate_launcher)
        app = QtWidgets.QApplication.instance()
        app.installNativeEventFilter(self.launcher_hotkey)
        app.installEventFilter(self)
        app.aboutToQuit.connect(self.launcher_hotkey.close)
        self.apply_launcher_hotkey()
        self.apply_ui_scale(self.ui_scale)
        self.screen_watcher = ScreenWatcher(self, self.fit_to_screen)
        self.data_watcher = QtCore.QFileSystemWatcher([str(self.store.root)],self)
        self.data_watcher.directoryChanged.connect(self.reload_entries)
    def ui_px(self, value):
        return max(1, round(value * self.ui_scale))
    def apply_ui_scale(self, scale):
        self.ui_scale = max(0.75, min(1.5, float(scale)))
        scale_tree(self, self.ui_scale, skip_root_size=True)
        self.fit_to_screen()
        self.refresh()
    def fit_to_screen(self, *_):
        area = available_area(self)
        width = max(1, min(self.ui_px(420), area.width()))
        height = max(1, min(self.ui_px(640), area.height()-self.mini.height()))
        self.setMinimumSize(0,0)
        self.setMaximumSize(area.width(), max(1,area.height()-self.mini.height()))
        self.resize(width, height)
        self.layout().activate()
        self.sync_tab_width()
        self.anchor_windows()
    def reload_entries(self, *_):
        try:
            if self.store.sync(): self.refresh()
        except (OSError,ValueError,KeyError):
            # Keep the current view if an external writer is mid-write or invalid.
            pass
    def save(self):
        try:
            previous=copy.deepcopy(self.store.data['items'])
            self.store.save()
            if previous!=self.store.data['items']: self.refresh()
            return True
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, '保存失败', str(e)); return False
    def persist_position(self):
        self.store.data['settings'].pop('position', None); self.save()
    def anchor_windows(self, *_):
        area = available_area(self)
        self.mini.move(area.right()-self.mini.width()+1, area.top())
        self.move(self.mini.x()+self.mini.width()-self.width(), self.mini.y()+self.mini.height())
    def sync_tab_width(self):
        margins = self.layout().contentsMargins()
        self.tabs.tabBar().setFixedWidth(max(1, self.width()-margins.left()-margins.right()))
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'tabs'): self.sync_tab_width()
        if hasattr(self, 'mini'): self.anchor_windows()
    def set_mini_visible(self, visible):
        self.mini.setVisible(visible)
        if not visible:
            self.hide()
        self.store.data['settings']['mini_visible'] = visible; self.save()
    def quit(self):
        self.long_capture_page.shutdown()
        self.pin_page.shutdown()
        self.mouse_page.shutdown()
        self.persist_position(); QtWidgets.QApplication.quit()
    def closeEvent(self, event):
        event.ignore(); self.hide()
    def toggle(self):
        self.hide() if self.isVisible() else self.expand()
    def focus_search(self):
        self.tabs.setCurrentIndex(0)
        self.search.setFocus(QtCore.Qt.ShortcutFocusReason)
    def activate_launcher(self):
        modal = QtWidgets.QApplication.activeModalWidget()
        if modal is not None:
            modal.raise_(); modal.activateWindow(); foreground_window(modal); return
        if self.pin_page.capturing or self.long_capture_page.capturing: return
        if self.isVisible():
            self.hide(); return
        self.expand()
        foreground_window(self)
        self.focus_search()
        self.search.selectAll()
    def apply_launcher_hotkey(self):
        title = self.store.data['settings'].get('launcher_hotkey', 'Ctrl + Alt + Q')
        choice = next((x for x in HOTKEYS if x[0] == title), HOTKEYS[0])
        success = self.launcher_hotkey.register(choice[1], choice[2])
        self.mini.setToolTip('快捷入口 · ' + title + ('（被占用，请右键更改）' if choice[2] and not success else '') + '\n右键打开菜单 → 设置')
        return success
    def open_settings(self):
        SettingsDialog(self).exec()
    def open_help(self):
        HelpDialog(self).exec()
    def expand(self):
        self.reload_entries()
        self.fit_to_screen()
        self.show(); self.raise_(); self.activateWindow()
        self.focus_search()
    def entry_icon(self, item):
        if item.get('icon'):
            icon = QtGui.QIcon(str(self.store.root / item['icon']))
            if not icon.isNull(): return icon
        target = resolve_local(item.get('target', ''),self.store.root,command=True)
        if Path(target).exists(): return self.provider.icon(QtCore.QFileInfo(target))
        return builtin_icon('globe') if target.startswith(('http:', 'https:')) else self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
    def rank_search(self, _text=None):
        query = self.search.text().strip()
        before = []
        for index in range(self.list.count()):
            item = self.list.item(index)
            entry = item.data(QtCore.Qt.UserRole)
            before.append(entry['id'])
            item.sort_key = (-score(entry['name'], entry.get('description',''), entry['target'], query), entry['name'].casefold(), entry['id'])
        # Sorting preserves the row widgets, their icons and action callbacks.
        expected = sorted((self.list.item(i) for i in range(self.list.count())), key=lambda item: item.sort_key)
        self.list.setUpdatesEnabled(False)
        blocker = QtCore.QSignalBlocker(self.list)
        if before != [item.data(QtCore.Qt.UserRole)['id'] for item in expected]:
            self.list.sortItems(QtCore.Qt.AscendingOrder)
        if self.list.count(): self.list.setCurrentRow(0)
        self.list.doItemsLayout()
        self.list.scrollToTop()
        del blocker
        self.list.setUpdatesEnabled(True)
    def refresh(self, *, reset_to_top=False):
        scroll_position = self.list.verticalScrollBar().value()
        selected_row = self.list.currentRow()
        selected = self.list.currentItem()
        selected_id = selected.data(QtCore.Qt.UserRole)['id'] if selected else None
        self.list.setUpdatesEnabled(False)
        self.list.clear()
        query = self.search.text().strip()
        items = sorted(self.store.data['items'], key=lambda x: (-score(x['name'], x.get('description',''), x['target'], query), x['name'].casefold()))
        for entry in items:
            aliases(entry['name'])  # Prepare cached pinyin before the first keystroke.
            item = RankedEntryItem(); item.sort_key = (-score(entry['name'], entry.get('description',''), entry['target'], query), entry['name'].casefold(), entry['id']); item.setData(QtCore.Qt.UserRole, entry); item.setSizeHint(QtCore.QSize(0, self.ui_px(24)))
            row = QtWidgets.QWidget(self.list.viewport()); line = QtWidgets.QHBoxLayout(row)
            line.setContentsMargins(*(self.ui_px(v) for v in (4,1,4,1))); line.setSpacing(self.ui_px(4))
            picture = QtWidgets.QLabel(); picture.setFixedSize(self.ui_px(18),self.ui_px(18)); picture.setPixmap(self.entry_icon(entry).pixmap(self.ui_px(16),self.ui_px(16))); line.addWidget(picture)
            name = QtWidgets.QLabel(entry['name']); name.setTextFormat(QtCore.Qt.PlainText)
            name.setMinimumWidth(0); name.setSizePolicy(QtWidgets.QSizePolicy.Ignored,QtWidgets.QSizePolicy.Preferred)
            line.addWidget(name,1)
            for label, callback in [('打开', self.open_entry), ('编辑', self.edit_entry), ('删除', self.delete_entry)]:
                button = QtWidgets.QPushButton(label, row)
                # Resolve the inherited scaled font before measuring the text.
                button.ensurePolished()
                metrics = button.fontMetrics()
                width = max(self.ui_px(36), metrics.horizontalAdvance(label)+self.ui_px(16)+2)
                height = max(self.ui_px(20), metrics.height()+self.ui_px(6)+2)
                button.setFixedSize(width, height)
                item.setSizeHint(QtCore.QSize(0, max(item.sizeHint().height(), height+self.ui_px(2))))
                button.clicked.connect(lambda checked=False, e=entry, c=callback: c(e))
                line.addWidget(button)
            row.setToolTip(entry['name']+'\n'+entry.get('description','')+'\n'+entry['target']); self.list.addItem(item); self.list.setItemWidget(item,row)
            if entry['id'] == selected_id: self.list.setCurrentItem(item)
        if reset_to_top:
            if items: self.list.setCurrentRow(0)
        elif self.list.currentRow() < 0 and items:
            # If the selected entry was deleted, select its nearest neighbour.
            self.list.setCurrentRow(max(0, min(selected_row, len(items)-1)))
        # Rebuilding or changing selection can move Qt's scroll bar. Restore it
        # only after the new rows have their final layout and scroll range.
        self.list.doItemsLayout()
        self.list.verticalScrollBar().setValue(0 if reset_to_top else scroll_position)
        self.list.setUpdatesEnabled(True)
    def eventFilter(self, obj, event):
        # Keep focus until Escape is released so the underlying app never
        # receives the release/repeat part of the same key stroke.
        owned = isinstance(obj, QtWidgets.QWidget) and obj.window() is self
        if (owned and QtWidgets.QApplication.activeModalWidget() is None
                and QtWidgets.QApplication.activePopupWidget() is None
                and event.type() in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease)
                and event.key() == QtCore.Qt.Key_Escape):
            if event.type() == QtCore.QEvent.ShortcutOverride:
                event.accept(); return True
            if event.type() == QtCore.QEvent.KeyPress:
                self._escape_pending = True
                event.accept(); return True
            if event.isAutoRepeat():
                event.accept(); return True
            if self._escape_pending:
                self._escape_pending = False
                event.accept()
                self.hide()
                return True
        if (event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Tab
                and event.modifiers() == QtCore.Qt.NoModifier
                and isinstance(obj, QtWidgets.QWidget) and obj.window() is self
                and QtWidgets.QApplication.activeModalWidget() is None):
            self.focus_search(); return True
        if obj is self.search and event.type() == QtCore.QEvent.KeyPress:
            if event.key() in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Up):
                delta = 1 if event.key() == QtCore.Qt.Key_Down else -1
                self.list.setCurrentRow(max(0, min(self.list.count()-1, self.list.currentRow()+delta))); return True
        return super().eventFilter(obj,event)
    def open_selected(self):
        if self.list.currentItem(): self.open_entry(self.list.currentItem().data(QtCore.Qt.UserRole))
    def open_entry(self, entry):
        try:
            target = resolve_local(entry['target'],self.store.root,command=True)
            if target.startswith(('https://','http://')):
                if not QtGui.QDesktopServices.openUrl(QtCore.QUrl(target)): raise OSError('浏览器未能打开网址')
            elif target.lower().startswith('shell:'):
                import subprocess
                explorer=str(Path(os.environ.get('WINDIR',r'C:\Windows'))/'explorer.exe')
                subprocess.Popen([explorer,target],cwd=str(self.store.root))
            elif entry.get('arguments') or entry.get('cwd'):
                import subprocess
                cwd=resolve_local(entry['cwd'],self.store.root) if entry.get('cwd') else str(self.store.root)
                subprocess.Popen('"' + target + '" ' + entry.get('arguments',''), cwd=cwd)
            else: os.startfile(target)
            self.hide()
        except Exception as e: QtWidgets.QMessageBox.warning(self,'打开失败',str(e))
    def edit_entry(self, entry=None, target=''):
        editor = Editor(self, entry, target)
        if editor.exec() != QtWidgets.QDialog.Accepted: return
        previous = list(self.store.data['items'])
        items = self.store.data['items']
        if entry: items[items.index(entry)] = editor.item
        else: items.append(editor.item)
        if not self.save(): self.store.data['items'] = previous; return
        saved_entry=next(x for x in self.store.data['items'] if x['id']==editor.item['id'])
        self.cache_icon(saved_entry); self.refresh()
    def cache_icon(self, entry):
        if entry.get('icon'): return
        if entry['target'].startswith(('https://','http://')):
            url = urllib.parse.urljoin(entry['target'], '/favicon.ico')
            request = QNetworkRequest(QtCore.QUrl(url)); request.setTransferTimeout(5000)
            reply = self.network.get(request)
            reply.finished.connect(lambda: self.finish_icon(reply, entry['id']))
        else:
            destination = self.store.icons / (entry['id'] + '.png')
            if self.entry_icon(entry).pixmap(48,48).save(str(destination),'PNG'):
                entry['icon'] = 'icons/' + destination.name; self.save()
    def finish_icon(self, reply, identifier):
        try:
            payload = bytes(reply.readAll()) if reply.error() == reply.NoError else b''
            pixmap = QtGui.QPixmap()
            if len(payload) <= 2_000_000 and pixmap.loadFromData(payload):
                entry = next((x for x in self.store.data['items'] if x['id'] == identifier and not x.get('icon')), None)
                if entry:
                    path = self.store.icons / (identifier+'.png'); pixmap.scaled(64,64,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation).save(str(path),'PNG')
                    entry['icon'] = 'icons/'+path.name; self.save(); self.refresh()
        finally: reply.deleteLater()
    def delete_entry(self, entry):
        if QtWidgets.QMessageBox.question(self,'删除快捷入口',f'确定移除“{entry["name"]}”？\n只移除本软件中的入口，不删除原文件。',QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,QtWidgets.QMessageBox.No) == QtWidgets.QMessageBox.Yes:
            previous = list(self.store.data['items']); self.store.data['items'].remove(entry)
            if not self.save(): self.store.data['items'] = previous
            self.refresh()
    def dragEnterEvent(self, event):
        if hasattr(self,'pin_page') and self.tabs.currentIndex()==2:
            self.pin_page.dragEnterEvent(event);return
        if event.mimeData().hasUrls() or event.mimeData().hasText(): event.acceptProposedAction()
    def dropEvent(self, event):
        if hasattr(self,'pin_page') and self.tabs.currentIndex()==2:
            self.pin_page.dropEvent(event);return
        mime = event.mimeData()
        targets = [u.toLocalFile() if u.isLocalFile() else u.toString() for u in mime.urls()] if mime.hasUrls() else [mime.text().strip()]
        for target in targets:
            if target: self.edit_entry(target=target)
        event.acceptProposedAction()

def main():
    app = QtWidgets.QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QtGui.QIcon(str(ROOT / 'assets' / 'app-icon.ico')))
    instance = SingleInstance()
    try:
        if not instance.acquire(): return
        # Compatibility with an already-running older version in this folder.
        lock = QtCore.QLockFile(str(ROOT / '.instance.lock'))
        lock.setStaleLockTime(0)
        if not lock.tryLock(100):
            instance.close()
            QtWidgets.QMessageBox.information(None,'快捷入口','旧版快捷入口仍在运行，请先从托盘退出旧版，再打开新版。'); return
        dock = Dock(Store())
    except Exception as e:
        QtWidgets.QMessageBox.critical(None,'无法启动',f'启动失败，原数据文件未被覆盖。\n{e}'); return
    def activate_existing():
        dock.show_mini.setChecked(True)
        dock.expand()
    instance.activated.connect(activate_existing)
    app.exec()
    instance.close()

if __name__ == '__main__': main()
