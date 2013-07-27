#! /usr/bin/env python3

# Import everything we need.
import sys
import os
import copy
import common
import extension_server

# Try importing Filter from Adblock module.
# If it isn't available, create a dummy class to avoid problems.
try:
    from abpy import Filter
except:
    class Filter(object):
        def __init__(self, rules):
            super(Filter, self).__init__()
        def match(self, url):
            return None

# Extremely specific imports from PyQt4.
from PyQt4.QtCore import Qt, QSettings, QCoreApplication, pyqtSignal, QUrl, QByteArray, QFile, QIODevice, QTimer
from PyQt4.QtGui import QApplication, QIcon, QMenu, QAction, QMainWindow, QToolBar, QToolButton, QComboBox, QLineEdit, QTabWidget, QPrinter, QPrintDialog, QPrintPreviewDialog, QInputDialog, QFileDialog, QProgressBar, QLabel
from PyQt4.QtNetwork import QNetworkCookieJar, QNetworkCookie, QNetworkAccessManager, QNetworkRequest
from PyQt4.QtWebKit import QWebView, QWebPage

# chdir to the app folder.
os.chdir(common.app_folder)

# Create a global settings manager.
settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "nimbus", "config", QCoreApplication.instance())

# This is a convenient variable that gets the settings folder on any platform.
settings_folder = os.path.dirname(settings.fileName())

# Adblock-related stuff.
adblock_folder = os.path.join(settings_folder, "adblock")
easylist = os.path.join(common.app_folder, "easylist.txt")
adblock_rules = []

# If we don't want to use Adblock, there's a command-line argument for that.
no_adblock = "--no-adblock" in sys.argv

# Load Adblock filters if Adblock is not disabled via command-line.
if not no_adblock:
    # Load easylist.
    if os.path.exists(easylist):
        f = open(easylist)
        try: adblock_rules += [rule.rstrip("\n") for rule in f.readlines()]
        except: pass
        f.close()

    # Load additional filters.
    if os.path.exists(adblock_folder):
        for fname in os.listdir(adblock_folder):
            f = open(os.path.join(adblock_folder, fname))
            try: adblock_rules += [rule.rstrip("\n") for rule in f.readlines()]
            except: pass
            f.close()

# Create instance of Adblock Filter.
adblock_filter = Filter(adblock_rules)

# Create extension server.
server_thread = extension_server.ExtensionServerThread()

# List of file extensions supported by Google Docs.
gdocs_extensions = (".doc", ".pdf", ".ppt", ".pptx", ".docx", ".xls", ".xlsx", ".pages", ".ai", ".psd", ".tiff", ".dxf", ".svg", ".eps", ".ps", ".ttf", ".xps", ".zip", ".rar")

# Global cookiejar to store cookies.
# All WebView instances use this.
cookieJar = QNetworkCookieJar(QCoreApplication.instance())

# All incognito WebView instances use this one instead.
incognitoCookieJar = QNetworkCookieJar(QCoreApplication.instance())

# Global list to store browser history.
history = []

# Add an item to the browser history.
def addHistoryItem(url):
    global history
    if not url in history and len(url) < 84:
        history.append(url)

# This function saves the browser's settings.
def saveSettings():
    # Save history.
    global history
    history.sort()
    settings.setValue("history", history)

    # Save cookies.
    cookies = [cookie.toRawForm().data() for cookie in cookieJar.allCookies()]
    settings.setValue("cookies", cookies)

    # Sync any unsaved settings.
    settings.sync()

# This function loads the browser's settings.
def loadSettings():
    # Load history.
    global history
    raw_history = settings.value("history")
    if type(raw_history) is list:
        history = settings.value("history")

    # Load cookies.
    raw_cookies = settings.value("cookies")
    if type(raw_cookies) is list:
        cookies = [QNetworkCookie().parseCookies(QByteArray(cookie))[0] for cookie in raw_cookies]
        cookieJar.setAllCookies(cookies)

# This function clears out the browsing history and cookies.
# Changes are written to the disk upon application quit.
def clearHistory():
    global history
    history = []
    cookieJar.setAllCookies([])

# Custom NetworkAccessManager class with support for ad-blocking.
class NetworkAccessManager(QNetworkAccessManager):
    def __init__(self, *args, **kwargs):
        super(NetworkAccessManager, self).__init__(*args, **kwargs)
    def createRequest(self, op, request, device=None):
        url = request.url().toString()
        x = adblock_filter.match(url)
        if x != None:
            return QNetworkAccessManager.createRequest(self, QNetworkAccessManager.GetOperation, QNetworkRequest(QUrl()))
        else:
            return QNetworkAccessManager.createRequest(self, op, request, device)

# Progress bar used for downloads.
# This was ripped off of Ryouko.
class DownloadProgressBar(QProgressBar):

    # Initialize class.
    def __init__(self, reply=False, destination=os.path.expanduser("~"), parent=None):
        super(DownloadProgressBar, self).__init__(parent)
        self.setWindowTitle(reply.request().url().toString().split("/")[-1])
        self.networkReply = reply
        self.destination = destination
        self.progress = [0, 0]
        if self.networkReply:
            self.networkReply.downloadProgress.connect(self.updateProgress)
            self.networkReply.finished.connect(self.finishDownload)

    # Writes downloaded file to the disk.
    def finishDownload(self):
        if self.networkReply.isFinished():
            data = self.networkReply.readAll()
            f = QFile(self.destination)
            f.open(QIODevice.WriteOnly)
            f.writeData(data)
            f.flush()
            f.close()
            self.progress = [0, 0]

    # Updates the progress bar.
    def updateProgress(self, received, total):
        self.setMaximum(total)
        self.setValue(received)
        self.progress[0] = received
        self.progress[1] = total
        self.show()

    # Abort download.
    def abort(self):
        self.networkReply.abort()

# File download toolbar.
# These are displayed at the bottom of a MainWindow.
class DownloadBar(QToolBar):
    def __init__(self, reply, destination, parent=None):
        super(DownloadBar, self).__init__(parent)
        self.setMovable(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setStyleSheet("QToolBar { border: 0; background: palette(window); }")
        label = QLabel(self)
        self.addWidget(label)
        self.progressBar = DownloadProgressBar(reply, destination, self)
        self.progressBar.networkReply.finished.connect(self.close)
        self.progressBar.networkReply.finished.connect(self.deleteLater)
        self.addWidget(self.progressBar)
        label.setText(os.path.split(self.progressBar.destination)[1])
        abortAction = QAction(QIcon().fromTheme("process-stop"), "Abort", self)
        abortAction.triggered.connect(self.progressBar.abort)
        abortAction.triggered.connect(self.deleteLater)
        self.addAction(abortAction)

# Custom WebView class with support for ad-blocking, new tabs, downloads,
# recording history, and more.
class WebView(QWebView):

    # This is used to store references to webViews so that they don't
    # automatically get cleaned up.
    webViews = []

    # Downloads
    downloads = []

    # This is a signal used to inform everyone a new window was created.
    windowCreated = pyqtSignal(QWebView)

    # This is a signal used to tell everyone a download has started.
    downloadStarted = pyqtSignal(QToolBar)

    # Initialize class.
    def __init__(self, *args, incognito=False, **kwargs):
        super(WebView, self).__init__(*args, **kwargs)

        # Private browsing.
        self.incognito = incognito

        # This is used to store the text entered in using WebView.find(),
        # so that WebView.findNext() and WebView.findPrevious() work.
        self._findText = False

        # Create a NetworkAccessmanager that supports ad-blocking and set it.
        self.nAM = NetworkAccessManager()
        self.page().setNetworkAccessManager(self.nAM)

        # Enable Web Inspector
        self.settings().setAttribute(self.settings().DeveloperExtrasEnabled, True)

        # What to do if private browsing is not enabled.
        if not self.incognito:
            # Set persistent storage path to settings_folder.
            self.settings().enablePersistentStorage(settings_folder)

            # Set the CookieJar.
            self.page().networkAccessManager().setCookieJar(cookieJar)

            # Do this so that cookieJar doesn't get deleted along with WebView.
            cookieJar.setParent(QCoreApplication.instance())

            # Forward unsupported content.
            # Since this uses Google's servers, it is disabled in
            # private browsing mode.
            self.page().setForwardUnsupportedContent(True)
            self.page().unsupportedContent.connect(self.handleUnsupportedContent)

            # Recording history should only be done in normal browsing mode.
            self.urlChanged.connect(self.addHistoryItem)

        # What to do if private browsing is enabled.
        else:
            # Global incognito cookie jar, so that logins are preserved
            # between incognito tabs.
            self.page().networkAccessManager().setCookieJar(incognitoCookieJar)
            incognitoCookieJar.setParent(QCoreApplication.instance())

            # Enable private browsing for QWebSettings.
            self.settings().setAttribute(self.settings().PrivateBrowsingEnabled, True)

        # Enable Netscape plugins.
        self.settings().setAttribute(self.settings().PluginsEnabled, True)

        # This is what Nimbus should do when faced with a file to download.
        self.page().downloadRequested.connect(self.downloadFile)

        # Connect signals.
        self.titleChanged.connect(self.setWindowTitle)
        self.setWindowTitle("")

    def setWindowTitle(self, title):
        if len(title) == 0:
            title = "New Tab"
        QWebView.setWindowTitle(self, title)

    def icon(self):
        if self.incognito:
            return QIcon().fromTheme("face-devilish")
        return QWebView.icon(self)

    # Handler for unsupported content.
    def handleUnsupportedContent(self, reply):
        url = reply.url().toString()

        if not "file://" in url: # Make sure the file isn't local.
            
            # Check to see if the file can be loaded in Google Docs viewer.
            for extension in gdocs_extensions:
                if url.lower().endswith(extension):
                    self.load(QUrl("https://docs.google.com/viewer?embedded=true&url=" + url))
                    return
        
        self.downloadFile(reply.request())

    # Download file.
    def downloadFile(self, request):

        # Get file name for destination.
        fname = QFileDialog.getSaveFileName(None, "Save As...", os.path.join(os.path.expanduser("~"), request.url().toString().split("/")[-1]), "All files (*)")
        if fname:
            reply = self.page().networkAccessManager().get(request)
            
            # Create a DownloadBar instance and append it to list of
            # downloads.
            downloadDialog = DownloadBar(reply, fname, None)
            self.downloads.append(downloadDialog)

            # Emit signal.
            self.downloadStarted.emit(downloadDialog)

    # Add history item to the browser history.
    def addHistoryItem(self, url):
        addHistoryItem(url.toString())

    # Redefine createWindow. Emits windowCreated signal so that others
    # can utilize the newly-created WebView instance.
    def createWindow(self, type):
        webview = WebView(incognito=self.incognito, parent=self.parent())
        self.webViews.append(webview)
        self.windowCreated.emit(webview)
        return webview

    # Opens a very simple find text dialog.
    def find(self):
        if type(self._findText) is not str:
            self._findText = ""
        find = QInputDialog.getText(None, "Find", "Search for:", QLineEdit.Normal, self._findText)
        if find:
            self._findText = find[0]
        else:
            self._findText = ""
        self.findText(self._findText, QWebPage.FindWrapsAroundDocument)

    # Find next instance of text.
    def findNext(self):
        if not self._findText:
            self.find()
        else:
            self.findText(self._findText, QWebPage.FindWrapsAroundDocument)

    # Find previous instance of text.
    def findPrevious(self):
        if not self._findText:
            self.find()
        else:
            self.findText(self._findText, QWebPage.FindWrapsAroundDocument | QWebPage.FindBackward)

    # Open print dialog to print page.
    def printPage(self):
        printer = QPrinter()
        self.page().mainFrame().render(printer.paintEngine().painter())
        printDialog = QPrintDialog(printer)
        printDialog.open()
        printDialog.accepted.connect(lambda: self.print(printer))
        printDialog.exec_()

    # Open print preview dialog.
    def printPreview(self):
        printer = QPrinter()
        self.page().mainFrame().render(printer.paintEngine().painter())
        printDialog = QPrintPreviewDialog(printer, self)
        printDialog.paintRequested.connect(lambda: self.print(printer))
        printDialog.exec_()
        printDialog.deleteLater()

# Extension button class.
class ExtensionButton(QToolButton):
    def __init__(self, script="", parent=None):
        super(ExtensionButton, self).__init__(parent)
        self._parent = parent
        self.script = script
    def loadScript(self):
        self._parent.currentWidget().page().mainFrame().evaluateJavaScript(self.script)

# Custom MainWindow class.
# This contains basic navigation controls, a location bar, and a menu.
class MainWindow(QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        # List of closed tabs.
        self.closedTabs = []

        # Main toolbar.
        self.toolBar = QToolBar(movable=False, contextMenuPolicy=Qt.CustomContextMenu, parent=self)
        self.addToolBar(self.toolBar)

        # Tab widget for tabbed browsing.
        self.tabs = QTabWidget(self)

        # Remove border around tabs.
        self.tabs.setDocumentMode(True)

        # Allow rearranging of tabs.
        self.tabs.setMovable(True)

        # Update tab titles and icons when the current tab is changed.
        self.tabs.currentChanged.connect(self.updateTabTitles)
        self.tabs.currentChanged.connect(self.updateTabIcons)

        # Hacky way of updating the location bar text when the tab is changed.
        self.tabs.currentChanged.connect(lambda: self.updateLocationText(self.tabs.currentWidget().url()))

        # Allow closing of tabs.
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.removeTab)

        # Set tabs as central widget.
        self.setCentralWidget(self.tabs)

        # New tab action.
        newTabAction = QAction(QIcon().fromTheme("list-add"), "New &Tab", self)
        newTabAction.setShortcut("Ctrl+T")
        newTabAction.triggered.connect(lambda: self.addTab())

        # New private browsing tab action.
        newIncognitoTabAction = QAction(QIcon().fromTheme("face-devilish"), "New &Incognito Tab", self)
        newIncognitoTabAction.setShortcut("Ctrl+Shift+N")
        newIncognitoTabAction.triggered.connect(lambda: self.addTab(incognito=True))

        # This is used so that the new tab button looks halfway decent,
        # and can actually be inserted into the corner of the tab widget.
        newTabToolBar = QToolBar(movable=False, contextMenuPolicy=Qt.CustomContextMenu, parent=self)

        # We don't want this widget to have any decorations.
        newTabToolBar.setStyleSheet("QToolBar { border: 0; background: transparent; }")

        newTabToolBar.addAction(newIncognitoTabAction)
        newTabToolBar.addAction(newTabAction)
        self.tabs.setCornerWidget(newTabToolBar, Qt.TopRightCorner)

        # These are hidden actions used for the Ctrl[+Shift]+Tab feature
        # you see in most browsers.
        nextTabAction = QAction(self)
        nextTabAction.setShortcut("Ctrl+Tab")
        nextTabAction.triggered.connect(self.nextTab)
        self.addAction(nextTabAction)

        previousTabAction = QAction(self)
        previousTabAction.setShortcut("Ctrl+Shift+Tab")
        previousTabAction.triggered.connect(self.previousTab)
        self.addAction(previousTabAction)

        # This is the Ctrl+W (Close Tab) shortcut.
        removeTabAction = QAction(self)
        removeTabAction.setShortcut("Ctrl+W")
        removeTabAction.triggered.connect(lambda: self.removeTab(self.tabs.currentIndex()))
        self.addAction(removeTabAction)

        # Dummy webpage used to provide navigation actions that conform to
        # the system's icon theme.
        self.actionsPage = QWebPage(self)

        # Regularly toggle navigation actions every few milliseconds.
        self.toggleActionsTimer = QTimer(self)
        self.toggleActionsTimer.timeout.connect(self.toggleActions)

        # Set up navigation actions.
        self.backAction = self.actionsPage.action(QWebPage.Back)
        self.backAction.setShortcut("Alt+Left")
        self.backAction.triggered.connect(self.back)
        self.toolBar.addAction(self.backAction)

        self.forwardAction = self.actionsPage.action(QWebPage.Forward)
        self.forwardAction.setShortcut("Alt+Right")
        self.forwardAction.triggered.connect(self.forward)
        self.toolBar.addAction(self.forwardAction)

        self.stopAction = self.actionsPage.action(QWebPage.Stop)
        self.stopAction.setShortcut("Esc")
        self.stopAction.triggered.connect(self.stop)
        self.toolBar.addAction(self.stopAction)

        self.reloadAction = self.actionsPage.action(QWebPage.Reload)
        self.reloadAction.setShortcuts(["F5", "Ctrl+R"])
        self.reloadAction.triggered.connect(self.reload)
        self.toolBar.addAction(self.reloadAction)

        # Start timer.
        self.toggleActionsTimer.start(8)

        # Location bar. Note that this is a combo box.
        self.locationBar = QComboBox(self)

        # Load stored browser history.
        for url in history:
            self.locationBar.addItem(url)

        # Combo boxes are not normally editable by default.
        self.locationBar.setEditable(True)

        # We want the location bar to stretch to fit the toolbar,
        # so we set its size policy to that of a QLineEdit.
        self.locationBar.setSizePolicy(QLineEdit().sizePolicy())

        # Load a page when Enter is pressed.
        self.locationBar.activated.connect(lambda: self.load(self.locationBar.currentText()))

        self.toolBar.addWidget(self.locationBar)

        # Ctrl+L/Alt+D focuses the location bar.
        locationAction = QAction(self)
        locationAction.setShortcuts(["Ctrl+L", "Alt+D"])
        locationAction.triggered.connect(self.locationBar.setFocus)
        locationAction.triggered.connect(self.locationBar.lineEdit().selectAll)
        self.addAction(locationAction)

        # Extensions toolbar.
        self.extensionBar = QToolBar(self)
        self.extensionBar.setMovable(False)
        self.extensionBar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.extensionBar.setStyleSheet("QToolBar { border: 0; background: transparent; }")
        self.toolBar.addWidget(self.extensionBar)
        self.extensionBar.hide()

        # Main menu.
        mainMenu = QMenu(self)

        # Add new tab actions to menu.
        mainMenu.addAction(newTabAction)
        mainMenu.addAction(newIncognitoTabAction)

        # Add reopen tab action.
        reopenTabAction = QAction("&Reopen Tab", self)
        reopenTabAction.setShortcut("Ctrl+Shift+T")
        reopenTabAction.triggered.connect(self.reopenTab)
        self.addAction(reopenTabAction)
        mainMenu.addAction(reopenTabAction)

        mainMenu.addSeparator()

        # Add find text action.
        findAction = QAction("&Find...", self)
        findAction.setShortcut("Ctrl+F")
        findAction.triggered.connect(self.find)
        mainMenu.addAction(findAction)

        # Add find next action.
        findNextAction = QAction("Find Ne&xt", self)
        findNextAction.setShortcut("Ctrl+G")
        findNextAction.triggered.connect(self.findNext)
        mainMenu.addAction(findNextAction)

        # Add find previous action.
        findPreviousAction = QAction("Find Pre&vious", self)
        findPreviousAction.setShortcut("Ctrl+Shift+G")
        findPreviousAction.triggered.connect(self.findPrevious)
        mainMenu.addAction(findPreviousAction)

        mainMenu.addSeparator()

        # Add print preview action.
        printPreviewAction = QAction("Print Previe&w", self)
        printPreviewAction.setShortcut("Ctrl+Shift+P")
        printPreviewAction.triggered.connect(self.printPreview)
        mainMenu.addAction(printPreviewAction)

        # Add print page action.
        printAction = QAction("&Print...", self)
        printAction.setShortcut("Ctrl+P")
        printAction.triggered.connect(self.printPage)
        mainMenu.addAction(printAction)

        # Add separator.
        mainMenu.addSeparator()

        # Add clear history action.
        clearHistoryAction = QAction("&Clear Recent History...", self)
        clearHistoryAction.setShortcut("Ctrl+Shift+Del")
        clearHistoryAction.triggered.connect(clearHistory)
        mainMenu.addAction(clearHistoryAction)

        # Add main menu action/button.
        self.mainMenuAction = QAction(QIcon().fromTheme("preferences-system"), "&Menu", self)
        self.mainMenuAction.setShortcuts(["Alt+M", "Alt+F", "Alt+E"])
        self.mainMenuAction.setMenu(mainMenu)
        self.toolBar.addAction(self.mainMenuAction)
        self.toolBar.widgetForAction(self.mainMenuAction).setPopupMode(QToolButton.InstantPopup)
        self.mainMenuAction.triggered.connect(lambda: self.toolBar.widgetForAction(self.mainMenuAction).showMenu())

        # Load browser extensions.
        # Ripped off of Ricotta.
        if os.path.isdir(common.extensions_folder):
            extensions = sorted(os.listdir(common.extensions_folder))
            for extension in extensions:
                extension_path = os.path.join(common.extensions_folder, extension)
                if os.path.isdir(extension_path):
                    script_path = os.path.join(extension_path, "script.js")
                    icon_path = os.path.join(extension_path, "icon.png")
                    if os.path.isfile(script_path):
                        f = open(script_path, "r")
                        script = copy.copy(f.read())
                        f.close()
                        newExtension = ExtensionButton(script, self)
                        newExtension.clicked.connect(newExtension.loadScript)
                        self.extensionBar.show()
                        self.extensionBar.addWidget(newExtension)
                        if os.path.isfile(icon_path):
                            newExtension.setIcon(QIcon(icon_path))
                        else:
                            newExtension.setText(extension)
            self.extensionBar.addSeparator()

    # Toggle all the navigation buttons.
    def toggleActions(self):
        self.backAction.setEnabled(self.tabs.currentWidget().pageAction(QWebPage.Back).isEnabled())
        self.forwardAction.setEnabled(self.tabs.currentWidget().pageAction(QWebPage.Forward).isEnabled())

        # This is a workaround so that hitting Esc will reset the location
        # bar text.
        self.stopAction.setEnabled(True)

        self.reloadAction.setEnabled(self.tabs.currentWidget().pageAction(QWebPage.Reload).isEnabled())

    # Navigation methods.
    def back(self):
        self.tabs.currentWidget().back()

    def forward(self):
        self.tabs.currentWidget().forward()

    def reload(self):
        self.tabs.currentWidget().reload()

    def stop(self):
        self.tabs.currentWidget().stop()
        self.locationBar.setEditText(self.tabs.currentWidget().url().toString())

    # Find text/Text search methods.
    def find(self):
        self.tabs.currentWidget().find()

    def findNext(self):
        self.tabs.currentWidget().findNext()

    def findPrevious(self):
        self.tabs.currentWidget().findPrevious()

    # Page printing methods.
    def printPage(self):
        self.tabs.currentWidget().printPage()

    def printPreview(self):
        self.tabs.currentWidget().printPreview()

    # Method to load a URL.
    def load(self, url=False):
        if not url:
            url = self.locationBar.currentText()
        if "." in url or ":" in url:
            self.tabs.currentWidget().load(QUrl.fromUserInput(url))
        else:
            self.tabs.currentWidget().load(QUrl("https://duckduckgo.com/?q=" + url))

    # Tab-related methods.
    def currentWidget(self):
        return self.tabs.currentWidget()

    def addTab(self, webView=None, **kwargs):
        # If a URL is specified, load it.
        if "incognito" in kwargs:
            webview = WebView(incognito=True, parent=self)
            if "url" in kwargs:
                webview.load(QUrl.fromUserInput(kwargs["url"]))

        elif "url" in kwargs:
            url = kwargs["url"]
            webview = WebView(self)
            webview.load(QUrl.fromUserInput(url))

        # If a WebView object is specified, use it.
        elif webView != None:
            webview = webView

        # If nothing is specified, use a blank WebView.
        else:
            webview = WebView(self)

        # Connect signals
        webview.titleChanged.connect(self.updateTabTitles)
        webview.urlChanged.connect(self.updateLocationText)
        webview.iconChanged.connect(self.updateTabIcons)
        webview.windowCreated.connect(self.addTab)
        webview.downloadStarted.connect(self.addDownloadToolBar)

        # Add tab
        self.tabs.addTab(webview, "New Tab")

        # Switch to new tab
        self.tabs.setCurrentIndex(self.tabs.count()-1)

        # Update icons so we see the globe icon on new tabs.
        self.updateTabIcons()

    def nextTab(self):
        if self.tabs.currentIndex() == self.tabs.count() - 1:
            self.tabs.setCurrentIndex(0)
        else:
            self.tabs.setCurrentIndex(self.tabs.currentIndex() + 1)

    def previousTab(self):
        if self.tabs.currentIndex() == 0:
            self.tabs.setCurrentIndex(self.tabs.count() - 1)
        else:
            self.tabs.setCurrentIndex(self.tabs.currentIndex() - 1)

    def updateTabTitles(self):
        for index in range(0, self.tabs.count()):
            title = self.tabs.widget(index).windowTitle()
            self.tabs.setTabText(index, title[:24] + '...' if len(title) > 24 else title)
            if index == self.tabs.currentIndex():
                self.setWindowTitle(title + " - Nimbus")

    def updateTabIcons(self):
        for index in range(0, self.tabs.count()):
            icon = self.tabs.widget(index).icon()
            self.tabs.setTabIcon(index, icon)
            if index == self.tabs.currentIndex():
                self.setWindowIcon(self.tabs.widget(index).icon())

    def removeTab(self, index):
        if self.tabs.widget(index).history().canGoBack() or self.tabs.widget(index).history().canGoForward() or self.tabs.widget(index).url().toString() not in ("about:blank", ""):
            self.closedTabs.append(self.tabs.widget(index))
        self.tabs.widget(index).load(QUrl("about:blank"))
        self.tabs.removeTab(index)
        if self.tabs.count() == 0:
            self.addTab(url="about:blank")

    def reopenTab(self):
        if len(self.closedTabs) > 0:
            self.addTab(self.closedTabs.pop())
            self.tabs.widget(self.tabs.count() - 1).back()

    # This method is used to add a DownloadBar to the window.
    def addDownloadToolBar(self, toolbar):
        self.addToolBar(Qt.BottomToolBarArea, toolbar)

    # Method to update the location bar text.
    def updateLocationText(self, url):
        currentUrl = self.tabs.currentWidget().url()
        if url == currentUrl:
            self.locationBar.setEditText(currentUrl.toString())

# Main function to load everything.
def main():

    # Create app.
    app = QApplication(sys.argv)

    # Start extension server.
    server_thread.start()

    # On quit, save settings.
    app.aboutToQuit.connect(saveSettings)

    # Load settings.
    loadSettings()

    # Create instance of MainWindow.
    win = MainWindow()

    # Open URLs from command line.
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if "." in arg or ":" in arg:
                win.addTab(url=arg)

    # If there aren't any tabs, open a blank one.
    if win.tabs.count() == 0:
        win.addTab(url="about:blank")

    # Show window.
    win.show()

    # Start app.
    app.exec_()

# Start program
if __name__ == "__main__":
    main()