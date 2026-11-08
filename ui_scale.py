"""Scale explicit Qt dimensions from their original values, without accumulation."""
import re
from PySide6 import QtCore, QtWidgets

LIMIT = 16777215

def px_style(style, scale):
    return re.sub(r'(?<![\w.])([0-9]+(?:\.[0-9]+)?)px', lambda m: f'{max(1, round(float(m[1])*scale))}px', style)

def scale_tree(root, scale, skip_root_size=False):
    widgets = [root] + root.findChildren(QtWidgets.QWidget)
    for widget in widgets:
        if widget.window() is not root.window(): continue
        if not hasattr(widget, '_ui_base'):
            widget._ui_base = (widget.styleSheet(), QtCore.QSize(widget.minimumSize()), QtCore.QSize(widget.maximumSize()))
        style, minimum, maximum = widget._ui_base
        widget.setProperty('uiScale', scale)
        widget.setStyleSheet(px_style(style, scale))
        # Tab width is controlled by the owning window, not the scale snapshot.
        if not isinstance(widget, QtWidgets.QTabBar) and not (widget is root and skip_root_size):
            widget.setMinimumSize(round(minimum.width()*scale), round(minimum.height()*scale))
            widget.setMaximumSize(*(LIMIT if v == LIMIT else round(v*scale) for v in (maximum.width(), maximum.height())))
    for layout in root.findChildren(QtWidgets.QLayout):
        parent = layout.parentWidget()
        if parent is not None and parent.window() is not root.window(): continue
        if not hasattr(layout, '_ui_base'):
            m = layout.contentsMargins()
            layout._ui_base = ((m.left(),m.top(),m.right(),m.bottom()), layout.spacing())
        margins, spacing = layout._ui_base
        layout.setContentsMargins(*(round(v*scale) for v in margins))
        if spacing >= 0: layout.setSpacing(round(spacing*scale))
    if root.layout(): root.layout().activate()
