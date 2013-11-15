#!/usr/bin/env python3

import sys
import common
import data
from nwebkit import WebView
from PyQt4.QtCore import QUrl
from PyQt4.QtGui import QApplication

def main():
    app = QApplication(sys.argv)
    common.createUserAgent()
    data.loadData()
    view = WebView()
    view.show()
    if len(sys.argv) > 1:
        view.load(QUrl.fromUserInput(sys.argv[-1]))
    else:
        view.load(QUrl("https://www.duckduckgo.com/"))
    app.exec_()

if __name__ == "__main__":
    main()
