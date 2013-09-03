#! /usr/bin/env python3

#######################
## custom_widgets.py ##
#######################

# Description:
# Custom widgets used by Nimbus.

import os
from common import app_folder
from translate import tr

try:
    from PyQt4.QtCore import Qt, pyqtSignal, QPoint, QUrl
    Signal = pyqtSignal
    from PyQt4.QtGui import QAction, QToolButton, QIcon, QWidget, QComboBox, QHBoxLayout, QTabWidget, QTextEdit, QVBoxLayout, QLabel, QSizePolicy, QLineEdit, QSpinBox, QToolBar, QStyle, QStylePainter, QStyleOptionToolBar, QMenu
except:
    from PySide.QtCore import Qt, Signal, QPoint, QUrl
    from PySide.QtGui import QAction, QToolButton, QIcon, QWidget, QComboBox, QHBoxLayout, QTabWidget, QTextEdit, QVBoxLayout, QLabel, QSizePolicy, QLineEdit, QSpinBox, QToolBar, QStyle, QStylePainter, QStyleOptionToolBar, QMenu

# Blank widget to take up space.
class Expander(QLabel):
    def __init__(self, parent=None):
        super(Expander, self).__init__(parent)
        self.setText("")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

class HorizontalExpander(QLabel):
    def __init__(self, parent=None):
        super(HorizontalExpander, self).__init__(parent)
        self.setText("")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

# Row widget.
class Row(QWidget):
    def __init__(self, parent=None):
        super(Row, self).__init__(parent)
        newLayout = QHBoxLayout()
        self.setLayout(newLayout)
        self.layout().setContentsMargins(0,0,0,0)
    def addWidget(self, widget):
        self.layout().addWidget(widget)

# This is a row with a label and a QLineEdit.
class LineEditRow(Row):
    def __init__(self, text="Enter something here:", parent=None):
        super(LineEditRow, self).__init__(parent)
        self.label = QLabel(text, self)
        self.addWidget(self.label)
        self.lineEdit = QLineEdit(self)
        self.addWidget(self.lineEdit)

# This is a row with a label and a QSpinBox.
class SpinBoxRow(Row):
    def __init__(self, text="Enter something here:", parent=None):
        super(SpinBoxRow, self).__init__(parent)
        self.label = QLabel(text, self)
        self.addWidget(self.label)
        self.spinBox = QSpinBox(self)
        self.addWidget(self.spinBox)
        self.expander = HorizontalExpander()
        self.addWidget(self.expander)

# Column widget.
class Column(QWidget):
    def __init__(self, parent=None):
        super(Column, self).__init__(parent)
        newLayout = QVBoxLayout()
        self.setLayout(newLayout)
        self.layout().setContentsMargins(0,0,0,0)
    def addWidget(self, widget):
        self.layout().addWidget(widget)

# Invisible menu.
class InvisibleMenu(QMenu):
    def setVisible(self, visible):
        QMenu.setVisible(self, False)

# Toolbar that looks like a menubar.
class MenuToolBar(QToolBar):
    def __init__(self, *args, **kwargs):
        super(MenuToolBar, self).__init__(*args, **kwargs)
    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionToolBar()
        self.initStyleOption(option)
        style = self.style()
        style.drawControl(QStyle.CE_MenuBarEmptyArea, option, painter, self)

# Location bar.
class LocationBar(QComboBox):
    def __init__(self, *args, icon=None, **kwargs):
        super(LocationBar, self).__init__(*args, **kwargs)
        self.icon = QToolButton(self)
        if type(icon) is QIcon:
            self.icon.setIcon(icon)
        self.icon.setFixedWidth(16)
        self.icon.setFixedHeight(16)
        self.icon.hide()
        self.icon.setStyleSheet("QToolButton { border: 0; background: transparent; width: 16px; height: 16px; }")
        sz = self.icon
        fw = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        self.s = False
        msz = self.minimumSizeHint()
        self.setMinimumSize(max(msz.width(), self.icon.sizeHint().height() + fw * 2 + 2), max(msz.height(), self.icon.sizeHint().height() + fw * 2 + 2))

    def paintEvent(self, ev):
        sz = self.icon
        fw = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        QComboBox.paintEvent(self, ev)
        self.icon.render(self, QPoint(self.rect().left() + (self.height() + 1 - sz.width())/2, (self.height() + 1 - sz.height())/2))
        if self.s == False:
            self.lineEdit().setStyleSheet("QLineEdit { background: transparent; padding-left: %spx; }" % str(sz.width() + (self.height() + 1 - sz.width())/2))
            self.s = True
            self.redefPaintEvent()

    def redefPaintEvent(self):
        self.paintEvent = self.shortPaintEvent

    def shortPaintEvent(self, ev):
        sz = self.icon
        fw = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        QComboBox.paintEvent(self, ev)
        self.icon.render(self, QPoint(self.rect().left() + (self.height() + 1 - sz.width())/2, (self.height() + 1 - sz.height())/2))

    def setIcon(self, icon):
        self.icon.setIcon(icon)

# Link action for dropdown menus.
class LinkAction(QAction):
    triggered2 = Signal([str], [QUrl])
    def __init__(self, url, *args, **kwargs):
        super(LinkAction, self).__init__(*args, **kwargs)
        self.url = url
        self.triggered.connect(lambda: self.triggered2.emit(self.url))

# Web history action for dropdown menus.
class WebHistoryAction(QAction):
    triggered2 = Signal(int)
    def __init__(self, index, *args, **kwargs):
        super(WebHistoryAction, self).__init__(*args, **kwargs)
        self.setData(index)
        self.triggered.connect(lambda: self.triggered2.emit(self.data()))

# License view class.
class ReadOnlyTextEdit(QTextEdit):
    def __init__(self, *args, **kwargs):
        super(ReadOnlyTextEdit, self).__init__(*args, **kwargs)
        self.setReadOnly(True)

# Licensing dialog.
class LicenseDialog(QTabWidget):
    def __init__(self, parent=None):
        super(LicenseDialog, self).__init__(parent)
        self.resize(420, 320)
        self.setWindowTitle(tr("Credits & Licensing"))
        self.setWindowFlags(Qt.Dialog)
        self.readme = ""
        self.license = ""
        self.thanks = ""
        self.authors = ""
        for fname in os.listdir(app_folder):
            if fname.startswith("LICENSE"):
                try: f = open(os.path.join(app_folder, fname), "r")
                except: pass
                else:
                    self.license = f.read()
                    f.close()
            elif fname.startswith("THANKS"):
                try: f = open(os.path.join(app_folder, fname), "r")
                except: pass
                else:
                    self.thanks = f.read()
                    f.close()
            elif fname.startswith("AUTHORS"):
                try: f = open(os.path.join(app_folder, fname), "r")
                except: pass
                else:
                    self.authors = f.read()
                    f.close()
            elif fname.startswith("README"):
                try: f = open(os.path.join(app_folder, fname), "r")
                except: pass
                else:
                    self.readme = f.read()
                    f.close()
        self.readmeView = ReadOnlyTextEdit(self)
        self.readmeView.setText(self.readme)
        self.addTab(self.readmeView, tr("&README"))
        self.authorsView = ReadOnlyTextEdit(self)
        self.authorsView.setText(self.authors)
        self.addTab(self.authorsView, tr("&Authors"))
        self.thanksView = ReadOnlyTextEdit(self)
        self.thanksView.setText(self.thanks)
        self.addTab(self.thanksView, tr("&Thanks"))
        self.licenseView = ReadOnlyTextEdit(self)
        self.licenseView.setText(self.license)
        self.addTab(self.licenseView, tr("&License"))
        closeAction = QAction(self)
        closeAction.setShortcuts(["Esc", "Ctrl+W"])
        closeAction.triggered.connect(self.hide)
        self.addAction(closeAction)
