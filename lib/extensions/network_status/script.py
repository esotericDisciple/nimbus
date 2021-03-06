mainWindow = browser.activeWindow()
try: network.networkStatusDisplay
except:
    network.networkStatusDisplay = custom_widgets.ReadOnlyTextEdit(None)
    network.networkStatusDisplay.closeAction = QAction(network.networkStatusDisplay)
    network.networkStatusDisplay.closeAction.setShortcuts(["Ctrl+W", "Esc"])
    network.networkStatusDisplay.closeAction.triggered.connect(network.networkStatusDisplay.close)
    network.networkStatusDisplay.addAction(network.networkStatusDisplay.closeAction)
    network.networkStatusDisplay.setWindowTitle(tr("Network status"))
    network.networkStatusDisplay.resize(QSize(480, 320))
currentWidget = mainWindow.tabWidget().currentWidget()
stdout_handle = os.popen("nm-tool")
status = stdout_handle.read()
network.networkStatusDisplay.setPlainText(status)
network.networkStatusDisplay.show()
