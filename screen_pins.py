import ctypes
from ctypes import wintypes
from PySide6 import QtCore, QtGui, QtWidgets

HOTKEYS=[('无',0,0)]
for prefix,mods in [('Ctrl + Alt + ',3),('Ctrl + Shift + ',6),('Alt + Shift + ',5)]:
    for key in ('S','Q','P'):HOTKEYS.append((prefix+key,mods,ord(key)))
for prefix,mods in [('',0),('Ctrl + ',2),('Alt + ',1),('Shift + ',4),('Ctrl + Alt + ',3)]:
    for number in range(1,13):
        if number!=12:HOTKEYS.append((prefix+f'F{number}',mods,0x6f+number))

def crop_screens(frames, selection):
    relevant=[(rect,pix) for rect,pix in frames if rect.intersects(selection)]
    if not relevant or selection.width()<2 or selection.height()<2: return QtGui.QPixmap()
    ratio=max(p.devicePixelRatioF() for _,p in relevant)
    image=QtGui.QImage(round(selection.width()*ratio),round(selection.height()*ratio),QtGui.QImage.Format_ARGB32)
    image.setDevicePixelRatio(ratio);image.fill(QtCore.Qt.transparent)
    painter=QtGui.QPainter(image)
    for rect,pix in relevant:
        part=rect.intersected(selection);r=pix.devicePixelRatioF()
        source=QtCore.QRectF((part.x()-rect.x())*r,(part.y()-rect.y())*r,part.width()*r,part.height()*r)
        target=QtCore.QRectF(part.x()-selection.x(),part.y()-selection.y(),part.width(),part.height())
        painter.drawPixmap(target,pix,source)
    painter.end();return QtGui.QPixmap.fromImage(image)

class PinWindow(QtWidgets.QWidget):
    removed=QtCore.Signal(object)
    def __init__(self,pixmap,title):
        super().__init__()
        self.original=QtGui.QPixmap(pixmap);self.title=title
        self.setWindowTitle(title)
        self.setWindowFlags(QtCore.Qt.Tool|QtCore.Qt.FramelessWindowHint|QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setMouseTracking(True);self.setMinimumSize(32,32)
        self.drag_edges='';self.drag_origin=None
        self.restore_size()
    def restore_size(self):
        screen=QtGui.QGuiApplication.screenAt(self.pos()) or QtGui.QGuiApplication.primaryScreen()
        area=screen.availableGeometry()
        size=self.original.deviceIndependentSize().toSize()
        size.scale(int(area.width()*.9),int(area.height()*.9),QtCore.Qt.KeepAspectRatio) if size.width()>area.width()*.9 or size.height()>area.height()*.9 else None
        self.resize(size)
    def paintEvent(self,event):
        painter=QtGui.QPainter(self);painter.fillRect(self.rect(),QtGui.QColor('white'))
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(),self.original)
        painter.setPen(QtGui.QColor('#7188a6'));painter.drawRect(self.rect().adjusted(0,0,-1,-1))
    def hit_edges(self,point):
        margin=7
        return ('l' if point.x()<margin else 'r' if point.x()>=self.width()-margin else '')+('t' if point.y()<margin else 'b' if point.y()>=self.height()-margin else '')
    def edge_cursor(self,edges):
        if edges in ('lt','rb'):return QtCore.Qt.SizeFDiagCursor
        if edges in ('rt','lb'):return QtCore.Qt.SizeBDiagCursor
        if edges in ('l','r'):return QtCore.Qt.SizeHorCursor
        if edges in ('t','b'):return QtCore.Qt.SizeVerCursor
        return QtCore.Qt.ArrowCursor
    def resized_geometry(self,rect,edges,delta):
        x,y,w,h=rect.x(),rect.y(),rect.width(),rect.height()
        nw=w+(-delta.x() if 'l' in edges else delta.x() if 'r' in edges else 0)
        nh=h+(-delta.y() if 't' in edges else delta.y() if 'b' in edges else 0)
        if len(edges)==2:
            # Corners preserve the source image ratio, even after an edge stretch.
            ratio=self.original.width()/self.original.height()
            if abs(nw-w)>=abs(nh-h)*ratio:nh=nw/ratio
            else:nw=nh*ratio
            factor=max(32/nw if nw>0 else 100,32/nh if nh>0 else 100,1)
            if nw<=0 or nh<=0:nw,nh=max(32,32*ratio),max(32,32/ratio)
            else:nw*=factor;nh*=factor
            factor=min(1,10000/nw,10000/nh);nw*=factor;nh*=factor
        else:nw=max(32,min(10000,nw));nh=max(32,min(10000,nh))
        nw,nh=round(nw),round(nh)
        if 'l' in edges:x+=w-nw
        if 't' in edges:y+=h-nh
        return QtCore.QRect(x,y,nw,nh)
    def mousePressEvent(self,event):
        if event.button()==QtCore.Qt.LeftButton:
            self.drag_edges=self.hit_edges(event.position());self.drag_origin=event.globalPosition().toPoint();self.drag_rect=self.geometry()
        elif event.button()==QtCore.Qt.RightButton:self.show_menu(event.globalPosition().toPoint())
    def mouseMoveEvent(self,event):
        if event.buttons() & QtCore.Qt.LeftButton and self.drag_origin is not None:
            delta=event.globalPosition().toPoint()-self.drag_origin
            if self.drag_edges:self.setGeometry(self.resized_geometry(self.drag_rect,self.drag_edges,delta))
            else:self.move(self.drag_rect.topLeft()+delta)
        else:self.setCursor(self.edge_cursor(self.hit_edges(event.position())))
    def mouseReleaseEvent(self,event):
        self.drag_origin=None;self.drag_edges=''
    def mouseDoubleClickEvent(self,event):
        if event.button()==QtCore.Qt.LeftButton:self.restore_size()
    def wheelEvent(self,event):
        event.ignore()
    def show_menu(self,position):
        menu=QtWidgets.QMenu(self)
        menu.addAction('复制图片',lambda:QtWidgets.QApplication.clipboard().setPixmap(self.original))
        menu.addAction('另存为…',self.save_image)
        menu.addAction('恢复原始比例',self.restore_size)
        menu.addSeparator();menu.addAction('关闭贴图',self.close);menu.exec(position)
    def save_image(self):
        path,_=QtWidgets.QFileDialog.getSaveFileName(self,'保存图片',self.title+'.png','PNG 图片 (*.png)')
        if path and not self.original.save(path,'PNG'):QtWidgets.QMessageBox.warning(self,'保存失败','无法保存到所选位置。')
    def closeEvent(self,event):self.removed.emit(self);event.accept()

class SelectionOverlay(QtWidgets.QWidget):
    def __init__(self,page,rect,pixmap):
        super().__init__();self.page=page;self.frame=pixmap
        self.setWindowFlags(QtCore.Qt.Tool|QtCore.Qt.FramelessWindowHint|QtCore.Qt.WindowStaysOnTopHint)
        self.setGeometry(rect);self.setCursor(QtCore.Qt.CrossCursor)
        QtGui.QShortcut(QtGui.QKeySequence('Escape'),self,activated=lambda:page.finish_capture())
    def paintEvent(self,event):
        p=QtGui.QPainter(self);p.drawPixmap(self.rect(),self.frame)
        p.fillRect(self.rect(),QtGui.QColor(0,0,0,95))
        if self.page.selection is not None:
            selected=self.page.selection.translated(-self.x(),-self.y())
            p.save();p.setClipRect(selected);p.drawPixmap(self.rect(),self.frame);p.restore()
            p.setPen(QtGui.QPen(QtGui.QColor('#65b6ff'),2));p.drawRect(selected)
        p.setPen(QtCore.Qt.white);p.drawText(20,30,'拖动选择区域 · Esc / 右键取消')
    def mousePressEvent(self,event):
        if event.button()==QtCore.Qt.RightButton:self.page.finish_capture();return
        if event.button()==QtCore.Qt.LeftButton:
            self.page.selection_start=event.globalPosition().toPoint();self.grabMouse()
    def mouseMoveEvent(self,event):
        if event.buttons() & QtCore.Qt.LeftButton and self.page.selection_start is not None:
            self.page.selection=QtCore.QRect(self.page.selection_start,event.globalPosition().toPoint()).normalized()
            for overlay in self.page.overlays:overlay.update()
    def mouseReleaseEvent(self,event):
        if event.button()==QtCore.Qt.LeftButton:
            self.releaseMouse()
            if self.page.selection_start is not None:
                selection=QtCore.QRect(self.page.selection_start,event.globalPosition().toPoint()).normalized()
                self.page.finish_capture(crop_screens(self.page.frames,selection))

class CaptureHotkey(QtCore.QAbstractNativeEventFilter):
    def __init__(self,page):
        super().__init__();self.page=page;self.identifier=0x5144
        self.registered=False
    def register(self,mods,key):
        self.close()
        if key:self.registered=bool(ctypes.windll.user32.RegisterHotKey(None,self.identifier,0x4000|mods,key))
        return self.registered
    def nativeEventFilter(self,kind,message):
        msg=wintypes.MSG.from_address(int(message))
        if msg.message==0x0312 and msg.wParam==self.identifier:
            QtCore.QTimer.singleShot(0,self.page.begin_capture);return True,0
        return False,0
    def close(self):
        if self.registered:ctypes.windll.user32.UnregisterHotKey(None,self.identifier);self.registered=False

class ScreenPinsPage(QtWidgets.QWidget):
    def __init__(self,dock,register_hotkey=True):
        super().__init__();self.dock=dock;self.pins=[];self.overlays=[];self.capturing=False;self.selection=None;self.selection_start=None;self.counter=0
        self.setAcceptDrops(True)
        self.enabled=False
        body=QtWidgets.QVBoxLayout(self);body.setContentsMargins(10,12,10,10)
        self.enable_switch=QtWidgets.QCheckBox('启用截图贴图');body.addWidget(self.enable_switch)
        hotkey_row=QtWidgets.QHBoxLayout();hotkey_row.addWidget(QtWidgets.QLabel('截图热键'))
        self.hotkey_choice=QtWidgets.QComboBox()
        for title,mods,key in HOTKEYS:self.hotkey_choice.addItem(title,(mods,key))
        saved=dock.store.data['settings'].get('screen_pins',{})
        index=self.hotkey_choice.findText(saved.get('hotkey','Ctrl + Alt + S'));self.hotkey_choice.setCurrentIndex(max(0,index))
        hotkey_row.addWidget(self.hotkey_choice,1);body.addLayout(hotkey_row)
        row=QtWidgets.QHBoxLayout()
        self.actions=[]
        for title,callback in [('区域截图',self.begin_capture),('粘贴图片',self.paste_image),('选择图片',self.choose_image)]:
            button=QtWidgets.QPushButton(title);button.setMinimumHeight(32);button.clicked.connect(callback);row.addWidget(button);self.actions.append(button)
        body.addLayout(row)
        self.help=QtWidgets.QLabel()
        self.help.setWordWrap(True);body.addWidget(self.help)
        self.list=QtWidgets.QListWidget();body.addWidget(self.list)
        self.hidden=QtWidgets.QCheckBox('暂时隐藏全部贴图');self.hidden.toggled.connect(self.set_hidden);body.addWidget(self.hidden)
        body.addWidget(QtWidgets.QLabel('图片仅暂存在内存；退出后关闭，需要保留请另存为。'))
        QtGui.QShortcut(QtGui.QKeySequence.Paste,self,activated=self.paste_image)
        self.hotkey=CaptureHotkey(self) if register_hotkey else None
        if self.hotkey:
            QtWidgets.QApplication.instance().installNativeEventFilter(self.hotkey)
        self.hotkey_choice.currentIndexChanged.connect(self.change_hotkey)
        self.enable_switch.setChecked(bool(saved.get('enabled',False)))
        self.set_enabled(self.enable_switch.isChecked())
        self.enable_switch.toggled.connect(self.enabled_toggled)
    def change_hotkey(self):
        self.save_settings()
        self.update_hotkey()
    def save_settings(self):
        settings=self.dock.store.data['settings'].setdefault('screen_pins',{})
        settings.update(hotkey=self.hotkey_choice.currentText(),enabled=self.enable_switch.isChecked());self.dock.save()
    def enabled_toggled(self,enabled):
        self.set_enabled(enabled);self.save_settings()
    def update_hotkey(self):
        mods,key=self.hotkey_choice.currentData()
        if self.hotkey:
            self.hotkey.close()
            success=self.hotkey.register(mods,key) if self.enabled and key else False
        else:success=False
        text='未启用 · 开启后可以截图或导入图片。' if not self.enabled else ('截图热键：'+self.hotkey_choice.currentText() if success or not key else '热键被占用或不可用，可改选其他热键或点击截图按钮。')
        self.help.setText(text+'\n内部拖动移动 · 四角等比缩放 · 四边拉伸 · 双击恢复比例')
    def set_enabled(self,enabled):
        self.enabled=enabled
        if not enabled and self.capturing:self.finish_capture()
        for button in self.actions:button.setEnabled(enabled)
        self.hidden.setEnabled(enabled);self.list.setEnabled(enabled)
        for pin in self.pins:pin.setVisible(enabled and not self.hidden.isChecked())
        self.update_hotkey()
    def add_image(self,pixmap,title=None):
        if not self.enabled or pixmap.isNull():return
        self.counter+=1;pin=PinWindow(pixmap,title or f'贴图 {self.counter}')
        pin.removed.connect(self.remove_pin);self.pins.append(pin)
        area=QtGui.QGuiApplication.primaryScreen().availableGeometry()
        pin.move(area.center()-pin.rect().center()+QtCore.QPoint(12*(self.counter%6),12*(self.counter%6)))
        pin.setVisible(not self.hidden.isChecked());self.refresh()
    def refresh(self):
        self.list.clear()
        for pin in self.pins:
            item=QtWidgets.QListWidgetItem();item.setSizeHint(QtCore.QSize(0,52))
            row=QtWidgets.QWidget();line=QtWidgets.QHBoxLayout(row)
            label=QtWidgets.QLabel();label.setPixmap(pin.original.scaled(42,36,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation));line.addWidget(label)
            line.addWidget(QtWidgets.QLabel(pin.title),1)
            for text,callback in [('显示',lambda p=pin:self.locate(p)),('关闭',pin.close)]:
                button=QtWidgets.QPushButton(text);button.clicked.connect(lambda checked=False,c=callback:c());line.addWidget(button)
            self.list.addItem(item);self.list.setItemWidget(item,row)
    def remove_pin(self,pin):
        if pin in self.pins:self.pins.remove(pin);self.refresh()
    def locate(self,pin):
        if not self.enabled:return
        self.hidden.setChecked(False);pin.show();pin.raise_();pin.activateWindow()
    def set_hidden(self,hidden):
        for pin in self.pins:pin.setVisible(self.enabled and not hidden)
    def paste_image(self):
        if not self.enabled:return
        clipboard=QtWidgets.QApplication.clipboard();pix=clipboard.pixmap()
        if not pix.isNull():self.add_image(pix)
        elif clipboard.mimeData().hasUrls():self.import_urls(clipboard.mimeData().urls())
        else:QtWidgets.QMessageBox.information(self,'没有图片','剪贴板里没有可以粘贴的图片。')
    def choose_image(self):
        if not self.enabled:return
        paths,_=QtWidgets.QFileDialog.getOpenFileNames(self,'选择参考图片',str(self.dock.store.root),'图片 (*.png *.jpg *.jpeg *.bmp *.webp *.gif)')
        self.import_urls([QtCore.QUrl.fromLocalFile(p) for p in paths])
    def import_urls(self,urls):
        if not self.enabled:return
        for url in urls:
            if url.isLocalFile():
                reader=QtGui.QImageReader(url.toLocalFile());reader.setAutoTransform(True);image=reader.read()
                if not image.isNull():self.add_image(QtGui.QPixmap.fromImage(image),QtCore.QFileInfo(url.toLocalFile()).fileName())
                else:QtWidgets.QMessageBox.warning(self,'无法读取图片',url.toLocalFile())
    def dragEnterEvent(self,event):
        if self.enabled and (event.mimeData().hasImage() or event.mimeData().hasUrls()):event.acceptProposedAction()
    def dropEvent(self,event):
        if not self.enabled:return
        if event.mimeData().hasImage():self.add_image(QtGui.QPixmap.fromImage(event.mimeData().imageData()))
        elif event.mimeData().hasUrls():self.import_urls(event.mimeData().urls())
        event.acceptProposedAction()
    def begin_capture(self):
        if not self.enabled or self.capturing or (hasattr(self.dock, 'long_capture_page') and self.dock.long_capture_page.capturing) or QtWidgets.QApplication.activeModalWidget() is not None:return
        self.capturing=True;self.selection=None;self.selection_start=None
        self.previous_windows=[w for w in [self.dock,self.dock.mini,*self.pins] if w.isVisible()]
        for window in self.previous_windows:window.hide()
        QtCore.QTimer.singleShot(180,self.show_selection)
    def show_selection(self):
        if not self.capturing:return
        try:
            self.frames=[(screen.geometry(),screen.grabWindow(0)) for screen in QtGui.QGuiApplication.screens()]
            if not self.frames or any(p.isNull() for _,p in self.frames):raise RuntimeError('无法读取屏幕图像')
            self.overlays=[SelectionOverlay(self,rect,pix) for rect,pix in self.frames]
            for overlay in self.overlays:overlay.show();overlay.raise_()
            current=next((o for o in self.overlays if o.geometry().contains(QtGui.QCursor.pos())),self.overlays[0])
            current.activateWindow();current.setFocus()
        except Exception as exc:
            self.finish_capture();QtWidgets.QMessageBox.warning(self,'截图失败',str(exc))
    def finish_capture(self,pixmap=None):
        if not self.capturing:return
        self.capturing=False
        for overlay in self.overlays:overlay.releaseMouse();overlay.hide();overlay.deleteLater()
        self.overlays=[];self.frames=[]
        for window in self.previous_windows:
            if window in self.pins or window in (self.dock,self.dock.mini):window.show()
        if pixmap is not None and not pixmap.isNull():self.add_image(pixmap)
    def shutdown(self):
        if self.hotkey:
            self.hotkey.close();QtWidgets.QApplication.instance().removeNativeEventFilter(self.hotkey)
        if self.capturing:self.finish_capture()
        for pin in list(self.pins):pin.close()
