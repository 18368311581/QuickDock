"""Screen-aware window bounds and scrolling dialog contents."""
from PySide6 import QtCore, QtGui, QtWidgets


def available_area(widget=None):
    # QuickDock and its dialogs belong to the primary-screen desktop corner.
    screen = QtGui.QGuiApplication.primaryScreen()
    return QtCore.QRect(screen.availableGeometry())


class ScreenWatcher(QtCore.QObject):
    def __init__(self, owner, callback):
        super().__init__(owner)
        self.screens = []
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(callback)
        app = QtGui.QGuiApplication.instance()
        app.screenAdded.connect(self.bind)
        app.screenRemoved.connect(self.bind)
        app.primaryScreenChanged.connect(self.queue)
        self.bind()
    def queue(self, *_):
        self.timer.start(0)
    def bind(self, *_):
        for screen in QtGui.QGuiApplication.screens():
            if screen not in self.screens:
                for signal in (screen.availableGeometryChanged, screen.geometryChanged, screen.logicalDotsPerInchChanged):
                    signal.connect(self.queue)
                self.screens.append(screen)
        self.screens = [s for s in self.screens if s in QtGui.QGuiApplication.screens()]
        self.queue()


class AdaptiveDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.preferred_size = None
        self.footer = None
        self.screen_watcher = ScreenWatcher(self, self.fit_to_screen)
    def make_scrollable(self, footer, preferred):
        self.footer = footer
        old = self.layout()
        old.removeWidget(footer)
        content = QtWidgets.QWidget()
        content.setLayout(old)
        # The original content keeps its natural minimum size. On a narrow
        # screen, scrolling makes every field reachable without shrinking text.
        old.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
        self.content_scroll = QtWidgets.QScrollArea(self)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.content_scroll.setWidget(content)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        outer.addWidget(self.content_scroll, 1)
        outer.addWidget(footer)
        self.setMinimumSize(0,0)
        self.setMaximumSize(16777215,16777215)
        self.preferred_size = QtCore.QSize(preferred)
        self.fit_to_screen()
    def use_existing_scroll(self, preferred):
        self.layout().setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self.preferred_size = QtCore.QSize(preferred)
        self.fit_to_screen()
    def fit_to_screen(self, *_):
        if self.preferred_size is None: return
        area = available_area(self)
        # Leave room for the native title bar and resize borders, including
        # before the window has been shown and frameGeometry is available.
        extra_w = max(16, self.frameGeometry().width()-self.width())
        extra_h = max(40, self.frameGeometry().height()-self.height())
        width = max(1, min(self.preferred_size.width(), area.width()-extra_w-16))
        height = max(1, min(self.preferred_size.height(), area.height()-extra_h-16))
        if isinstance(self.footer, QtWidgets.QDialogButtonBox):
            self.footer.setOrientation(QtCore.Qt.Horizontal)
            if self.footer.minimumSizeHint().width() > width-24:
                self.footer.setOrientation(QtCore.Qt.Vertical)
        self.setMinimumSize(0,0)
        self.resize(width,height)
        if self.layout(): self.layout().activate()
        # Center inside the available area; all native decoration stays inside.
        self.move(area.left()+(area.width()-width-extra_w)//2,
                  area.top()+(area.height()-height-extra_h)//2)
    def showEvent(self, event):
        super().showEvent(event)
        self.fit_to_screen()


def scroll_page(page):
    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
    scroll.setWidget(page)
    return scroll
