#! /usr/bin/env python3

###############
## webkit.py ##
###############

# Description:
# This is the core module that contains all the very specific components
# related to loading Nimbus.

# Import everything we need.
import sys
import os
import re
import subprocess
import traceback
import hashlib
import common
import geolocation
import filtering
import translate
from translate import tr
import settings
import settings_dialog
import data
import network

# Extremely specific imports from PyQt4/PySide.
# We give PyQt4 priority because it supports Qt5.
try:
    from PyQt4.QtCore import Qt, QObject, QCoreApplication, pyqtSignal, pyqtSlot, QUrl, QFile, QIODevice, QTimer
    from PyQt4.QtGui import QListWidget, QSpinBox, QListWidgetItem, QMessageBox, QIcon, QAction, QToolBar, QLineEdit, QPrinter, QPrintDialog, QPrintPreviewDialog, QInputDialog, QFileDialog, QProgressBar, QLabel, QCalendarWidget, QSlider, QFontComboBox, QLCDNumber, QImage, QDateTimeEdit, QDial, QSystemTrayIcon
    from PyQt4.QtNetwork import QNetworkProxy, QNetworkRequest
    from PyQt4.QtWebKit import QWebView, QWebPage
    Signal = pyqtSignal
    Slot = pyqtSlot
except:
    from PySide.QtCore import Qt, QObject, QCoreApplication, Signal, Slot, QUrl, QFile, QIODevice, QTimer
    from PySide.QtGui import QListWidget, QSpinBox, QListWidgetItem, QMessageBox, QIcon, QAction, QToolBar, QLineEdit, QPrinter, QPrintDialog, QPrintPreviewDialog, QInputDialog, QFileDialog, QProgressBar, QLabel, QCalendarWidget, QSlider, QFontComboBox, QLCDNumber, QImage, QDateTimeEdit, QDial, QSystemTrayIcon
    from PySide.QtNetwork import QNetworkProxy, QNetworkRequest
    from PySide.QtWebKit import QWebView, QWebPage

# Add an item to the browser history.
def addHistoryItem(url):
    if not url in data.history and settings.setting_to_bool("data/RememberHistory"):
        data.history.append(url)

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
            f.write(data)
            f.flush()
            f.close()
            self.progress = [0, 0]
            if sys.platform.startswith("linux"):
                subprocess.Popen(["notify-send", "--icon=emblem-downloads", tr("Download complete: %s") % (os.path.split(self.destination)[1],)])
            else:
                common.trayIcon.showMessage(tr("Download complete"), os.path.split(self.destination)[1])

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
        self.setStyleSheet(common.blank_toolbar)
        label = QLabel(self)
        self.addWidget(label)
        self.progressBar = DownloadProgressBar(reply, destination, self)
        self.progressBar.networkReply.finished.connect(self.close)
        self.progressBar.networkReply.finished.connect(self.deleteLater)
        self.addWidget(self.progressBar)
        label.setText(os.path.split(self.progressBar.destination)[1])
        abortAction = QAction(QIcon().fromTheme("process-stop", QIcon(common.icon("process-stop.png"))), tr("Abort"), self)
        abortAction.triggered.connect(self.progressBar.abort)
        abortAction.triggered.connect(self.deleteLater)
        self.addAction(abortAction)

# Class for exposing fullscreen API to DOM.
class FullScreenRequester(QObject):
    fullScreenRequested = Signal(bool)
    @Slot(bool)
    def setFullScreen(self, fullscreen=False):
        self.fullScreenRequested.emit(fullscreen)

# Custom WebPage class with support for filesystem.
class WebPage(QWebPage):
    plugins = (("qcalendarwidget", QCalendarWidget),
               ("qslider", QSlider),
               ("qprogressbar", QProgressBar),
               ("qfontcombobox", QFontComboBox),
               ("qlcdnumber", QLCDNumber),
               ("qimage", QImage),
               ("qdatetimeedit", QDateTimeEdit),
               ("qdial", QDial),
               ("qspinbox", QSpinBox))
    
    # This is used to fire JavaScript events related to navigator.onLine.
    isOnlineTimer = QTimer()

    fullScreenRequested = Signal(bool)
    def __init__(self, *args, **kwargs):
        super(WebPage, self).__init__(*args, **kwargs)

        # Load userContent.css
        if os.path.exists(filtering.adblock_css):
            self.settings().setUserStyleSheetUrl(QUrl(filtering.adblock_css))

        # Connect this so that permissions for geolocation and stuff work.
        self.featurePermissionRequested.connect(self.permissionRequested)

        # This object is exposed to the DOM to allow geolocation.
        self.geolocation = geolocation.Geolocation(self)

        # This object is exposed to the DOM to allow full screen mode.
        self.fullScreenRequester = FullScreenRequester(self)
        self.fullScreenRequester.fullScreenRequested.connect(self.toggleFullScreen)

        self._userScriptsLoaded = False
        self.mainFrame().javaScriptWindowObjectCleared.connect(lambda: self.setUserScriptsLoaded(False))

        # Connect to self.tweakDOM, which carries out some hacks to
        # improve HTML5 support.
        self.mainFrame().javaScriptWindowObjectCleared.connect(self.tweakDOM)

        # Connect loadFinished to checkForNavigatorGeolocation and loadUserScripts.
        self.loadFinished.connect(self.checkForNavigatorGeolocation)
        self.loadFinished.connect(self.loadUserScripts)

        # This stores the user agent.
        self._userAgent = ""
        self._fullScreen = False

        # Start self.isOnlineTimer.
        if not self.isOnlineTimer.isActive():
            self.isOnlineTimer.timeout.connect(self.setNavigatorOnline)
            self.isOnlineTimer.start(1000)

        # Set user agent to default value.
        self.setUserAgent()

    # Sends a request to become fullscreen.
    def toggleFullScreen(self):
        if self._fullScreen:
            self.fullScreenRequested.emit(False)
            self._fullScreen = False
        else:
            self.fullScreenRequested.emit(True)
            self._fullScreen = True

    def setUserScriptsLoaded(self, loaded=False):
        self._userScriptsLoaded = loaded

    # Load userscripts.
    def loadUserScripts(self):
        if not self._userScriptsLoaded:
            self._userScriptsLoaded = True
            for userscript in settings.userscripts:
                for match in userscript["match"]:
                    try:
                        if match == "*":
                            r = True
                        else:
                            r = re.match(match, self.mainFrame().url().toString())
                        if r:
                            self.mainFrame().evaluateJavaScript(userscript["content"])
                            break
                    except:
                        traceback.print_exc()

    # Returns user agent string.
    def userAgentForUrl(self, url):

        if not "github" in url.authority():
            return self._userAgent
        # This is a workaround for GitHub not loading properly
        # with the default Nimbus user agent.
        else:
            return QWebPage.userAgentForUrl(self, url)

    # Convenience function.
    def setUserAgent(self, ua=None):
        if type(ua) is str:
            self._userAgent = ua
        else:
            self._userAgent = common.defaultUserAgent

    # This is a hacky way of checking whether a website wants to use
    # geolocation. It checks the page source for navigator.geolocation,
    # and if it is present, it assumes that the website wants to use it.
    def checkForNavigatorGeolocation(self):
        if "navigator.geolocation" in self.mainFrame().toHtml() and not self.mainFrame().url().authority() in data.geolocation_whitelist:
            self.allowGeolocation()

    # Prompts the user to enable or block geolocation, and reloads the page if the
    # user said yes.
    def allowGeolocation(self):
        reload_ = self.permissionRequested(self.mainFrame(), self.Geolocation)
        if reload_:
            self.action(self.Reload).trigger()

    # Sets permissions for features.
    # Currently supports geolocation.
    def permissionRequested(self, frame, feature):
        authority = frame.url().authority()
        if feature == self.Geolocation and frame == self.mainFrame() and settings.setting_to_bool("network/GeolocationEnabled") and not authority in data.geolocation_blacklist:
            confirm = True
            if not authority in data.geolocation_whitelist:
                confirm = QMessageBox.question(None, tr("Nimbus"), tr("This website would like to track your location."), QMessageBox.Ok | QMessageBox.No | QMessageBox.NoToAll, QMessageBox.Ok)
            if confirm == QMessageBox.Ok:
                if not authority in data.geolocation_whitelist:
                    data.geolocation_whitelist.append(authority)
                    data.saveData()
                self.setFeaturePermission(frame, feature, self.PermissionGrantedByUser)
            elif confirm == QMessageBox.NoToAll:
                if not authority in data.geolocation_blacklist:
                    data.geolocation_blacklist.append(authority)
                    data.saveData()
                self.setFeaturePermission(frame, feature, self.PermissionDeniedByUser)
            return confirm == QMessageBox.Ok
        return False

    # Fires JavaScript events pertaining to online/offline mode.
    def setNavigatorOnline(self):
        script = "window.navigator.onLine = " + str(network.isConnectedToNetwork()).lower() + ";"
        self.mainFrame().evaluateJavaScript(script)
        self.mainFrame().evaluateJavaScript("if (window.onLine) {\n" + \
                                            "   document.dispatchEvent(window.nimbus.onLineEvent);\n" + \
                                            "}")
        self.mainFrame().evaluateJavaScript("if (!window.onLine) {\n" + \
                                            "   document.dispatchEvent(window.nimbus.offLineEvent);\n" + \
                                            "}")

    # This loads a bunch of hacks to improve HTML5 support.
    def tweakDOM(self):
        authority = self.mainFrame().url().authority()
        self.mainFrame().addToJavaScriptWindowObject("nimbusFullScreenRequester", self.fullScreenRequester)
        self.mainFrame().evaluateJavaScript("window.nimbus = new Object();")
        self.mainFrame().evaluateJavaScript("window.nimbus.fullScreenRequester = nimbusFullScreenRequester; delete nimbusFullScreenRequester;")
        if settings.setting_to_bool("network/GeolocationEnabled") and authority in data.geolocation_whitelist:
            self.mainFrame().addToJavaScriptWindowObject("nimbusGeolocation", self.geolocation)
            script = "window.nimbus.geolocation = nimbusGeolocation;\n" + \
                     "delete nimbusGeolocation;\n" + \
                     "window.navigator.geolocation = {};\n" + \
                     "window.navigator.geolocation.getCurrentPosition = function(success, error, options) { var getCurrentPosition = eval('(' + window.nimbus.geolocation.getCurrentPosition() + ')'); success(getCurrentPosition); return getCurrentPosition; };"
            self.mainFrame().evaluateJavaScript(script)
        self.mainFrame().evaluateJavaScript("HTMLElement.prototype.requestFullScreen = function() { window.nimbus.fullScreenRequester.setFullScreen(true); var style = ''; if (this.hasAttribute('style')) { style = this.getAttribute('style'); }; this.setAttribute('oldstyle', style); this.setAttribute('style', style + ' position: fixed; top: 0; left: 0; padding: 0; margin: 0; width: 100%; height: 100%;'); document.fullScreen = true; }")
        self.mainFrame().evaluateJavaScript("HTMLElement.prototype.requestFullscreen = HTMLElement.prototype.requestFullScreen")
        self.mainFrame().evaluateJavaScript("HTMLElement.prototype.webkitRequestFullScreen = HTMLElement.prototype.requestFullScreen")
        self.mainFrame().evaluateJavaScript("document.cancelFullScreen = function() { window.nimbus.fullScreenRequester.setFullScreen(false); document.fullScreen = false; var allElements = document.getElementsByTagName('*'); for (var i=0;i<allElements.length;i++) { var element = allElements[i]; if (element.hasAttribute('oldstyle')) { element.setAttribute('style', element.getAttribute('oldstyle')); } } }")
        self.mainFrame().evaluateJavaScript("document.webkitCancelFullScreen = document.cancelFullScreen")
        self.mainFrame().evaluateJavaScript("document.fullScreen = false;")
        self.mainFrame().evaluateJavaScript("document.exitFullscreen = document.cancelFullScreen")
        self.mainFrame().evaluateJavaScript("window.nimbus.onLineEvent = document.createEvent('Event');\n" + \
                                            "window.nimbus.onLineEvent.initEvent('online',true,false);")
        self.mainFrame().evaluateJavaScript("window.nimbus.offLineEvent = document.createEvent('Event');\n" + \
                                            "window.nimbus.offLineEvent.initEvent('offline',true,false);")

    # Creates Qt-based plugins.
    # One plugin pertains to the settings dialog,
    # while another pertains to local directory views.
    def createPlugin(self, classid, url, paramNames, paramValues):
        if classid.lower() == "settingsdialog":
            sdialog = settings_dialog.SettingsDialog(self.view())
            return sdialog
        elif classid.lower() == "directoryview":
            directoryview = QListWidget(self.view())
            try:
                if 1:
                    u = url.path()
                    u2 = QUrl(u).path()
                    directoryview.addItem(os.path.dirname(u2))
                    if os.path.isdir(u2):
                        l = os.listdir(u2)
                        l.sort()
                        for fname in l:
                            directoryview.addItem(os.path.join(u2, fname))
                    directoryview.itemDoubleClicked.connect(lambda item: self.mainFrame().load(QUrl(item.text())))
                    directoryview.itemActivated.connect(lambda item: self.mainFrame().load(QUrl(item.text())))
            except: pass
            else: return directoryview
        else:
            for name, widgetclass in self.plugins:
                if classid.lower() == name:
                    widget = widgetclass(self.view())
                    widgetid = classid
                    pnames = [name.lower() for name in paramNames]
                    if "id" in pnames:
                        widgetid = paramValues[pnames.index("id")]
                    self.mainFrame().addToJavaScriptWindowObject(widgetid, widget)
                    return widget
        return

# Custom WebView class with support for ad-blocking, new tabs, downloads,
# recording history, and more.
class WebView(QWebView):

    # This is used to store references to webViews so that they don't
    # automatically get cleaned up.
    webViews = []

    # Downloads
    downloads = []

    # This is a signal used to inform everyone a new window was created.
    windowCreated = Signal(QWebView)

    # This is a signal used to tell everyone a download has started.
    downloadStarted = Signal(QToolBar)

    # Initialize class.
    def __init__(self, *args, incognito=False, **kwargs):
        super(WebView, self).__init__(*args, **kwargs)

        # Add this webview to the list of webviews.
        common.webviews.append(self)
        self._url = ""

        self._cacheLoaded = False

        # Private browsing.
        self.incognito = incognito

        # Stores the mime type of the current page.
        self._contentType = None

        # This is used to store the text entered in using WebView.find(),
        # so that WebView.findNext() and WebView.findPrevious() work.
        self._findText = False

        # This is used to store the current status message.
        self._statusBarMessage = ""

        # This is used to store the current page loading progress.
        self._loadProgress = 0

        # This stores the link last hovered over.
        self._hoveredLink = ""

        self.setPage(WebPage(self))

        # Create a NetworkAccessmanager that supports ad-blocking and set it.
        if not self.incognito:
            self.nAM = network.networkAccessManager
            self.page().setNetworkAccessManager(self.nAM)
            self.nAM.setParent(QCoreApplication.instance())
        else:
            self.nAM = network.incognitoNetworkAccessManager
            self.page().setNetworkAccessManager(self.nAM)
            self.nAM.setParent(QCoreApplication.instance())

        # Enable Web Inspector
        self.settings().setAttribute(self.settings().DeveloperExtrasEnabled, True)

        self.updateProxy()
        self.updateNetworkSettings()
        self.updateContentSettings()

        # What to do if private browsing is not enabled.
        if not self.incognito:
            # Set persistent storage path to settings_folder.
            self.settings().enablePersistentStorage(settings.settings_folder)

            # Set the CookieJar.
            self.page().networkAccessManager().setCookieJar(network.cookieJar)

            # Do this so that cookieJar doesn't get deleted along with WebView.
            network.cookieJar.setParent(QCoreApplication.instance())

            # Recording history should only be done in normal browsing mode.
            self.urlChanged.connect(self.addHistoryItem)

        # What to do if private browsing is enabled.
        else:
            # Global incognito cookie jar, so that logins are preserved
            # between incognito tabs.
            self.page().networkAccessManager().setCookieJar(network.incognitoCookieJar)
            network.incognitoCookieJar.setParent(QCoreApplication.instance())

            # Enable private browsing for QWebSettings.
            self.settings().setAttribute(self.settings().PrivateBrowsingEnabled, True)

        # Handle unsupported content.
        self.page().setForwardUnsupportedContent(True)
        self.page().unsupportedContent.connect(self.handleUnsupportedContent)

        # This is what Nimbus should do when faced with a file to download.
        self.page().downloadRequested.connect(self.downloadFile)

        # Connect signals.
        self.titleChanged.connect(self.setWindowTitle)
        self.page().linkHovered.connect(self.setStatusBarMessage)
        self.statusBarMessage.connect(self.setStatusBarMessage)
        self.loadProgress.connect(self.setLoadProgress)

        # PyQt4 doesn't support <audio> and <video> tags on Windows.
        # This is a little hack to work around it.
        self.loadStarted.connect(self.resetContentType)
        self.loadFinished.connect(self.replaceAVTags)
        self.loadFinished.connect(self.savePageToCache)

        # Check if content viewer.
        self._isUsingContentViewer = False
        self.loadStarted.connect(self.checkIfUsingContentViewer)
        self.loadFinished.connect(self.finishLoad)

        self.setWindowTitle("")

        if os.path.exists(settings.new_tab_page):
            self.load(QUrl("about:blank"))

    # Calls network.errorPage.
    def errorPage(self, title="Problem loading page", heading="Whoops...", error="Nimbus could not load the requested page.", suggestions=["Try reloading the page.", "Make sure you're connected to the Internet. Once you're connected, try loading this page again.", "Check for misspellings in the URL (e.g. <b>ww.google.com</b> instead of <b>www.google.com</b>).", "The server may be experiencing some downtime. Wait for a while before trying again.", "If your computer or network is protected by a firewall, make sure that Nimbus is permitted ."]):
        return network.errorPage(title, heading, error, suggestions)

    # This is a half-assed implementation of error pages,
    # which doesn't work yet.
    def supportsExtension(self, extension):
        if extension == QWebPage.ErrorPageExtension:
            return True
        return False

    def extension(self, extension, option=None, output=None):
        if extension == QWebPage.ErrorPageExtension and option != NOne:
            option.frame().setHtml(errorPage())
        else:
            QWebPage.extension(self, extension, option, output)

    # Convenience function.
    def setUserAgent(self, ua):
        self.page().setUserAgent(ua)

    # Returns whether the browser has loaded a content viewer.
    def isUsingContentViewer(self):
        return self._isUsingContentViewer

    # Checks whether the browser has loaded a content viewer.
    # This is necessary so that downloading the original file from
    # Google Docs Viewer doesn't loop back to Google Docs Viewer.
    def checkIfUsingContentViewer(self):
        for viewer in common.content_viewers:
            if viewer[0].replace("%s", "") in self.url().toString():
                self._isUsingContentViewer = True
                return
        self._isUsingContentViewer = False

    # Resets recorded content type.
    def resetContentType(self):
        self._contentType = None

    # Custom implementation of deleteLater that also removes
    # the WebView from common.webviews.
    def deleteLater(self):
        try: common.webviews.remove(self)
        except: pass
        QWebView.deleteLater(self)

    # If a request has finished and the request's URL is the current URL,
    # then set self._contentType.
    def ready(self, response):
        if self._contentType == None and response.url() == self.url():
            try: contentType = response.header(QNetworkRequest.ContentTypeHeader)
            except: contentType = None
            if contentType != None:
                self._contentType = contentType

    # This is a custom implementation of mousePressEvent.
    # It allows the user to Ctrl-click or middle-click links to open them in
    # new tabs.
    def mousePressEvent(self, ev):
        if self._statusBarMessage != "" and (((QCoreApplication.instance().keyboardModifiers() == Qt.ControlModifier) and not ev.button() == Qt.RightButton) or ev.button() == Qt.MidButton or ev.button() == Qt.MiddleButton):
            url = self._statusBarMessage
            ev.ignore()
            newWindow = self.createWindow(QWebPage.WebBrowserWindow)
            newWindow.load(QUrl(url))
        else:
            return QWebView.mousePressEvent(self, ev)

    # Creates an error page.
    def errorPage(self, *args, **kwargs):
        self.setHtml(network.errorPage(*args, **kwargs))

    # This loads a page from the cache if certain network errors occur.
    # If that can't be done either, it produces an error page.
    def finishLoad(self, ok=False):
        if not ok:
            success = False
            if not network.isConnectedToNetwork():
                success = self.loadPageFromCache(self._url)
            if not success:
                if not network.isConnectedToNetwork():
                    self.errorPage("Problem loading page", "No Internet connection", "Your computer is not connected to the Internet. You may want to try the following:", ["<b>Windows 7 or Vista:</b> Click the <i>Start</i> button, then click <i>Control Panel</i>. Type <b>network</b> into the search box, click <i>Network and Sharing Center</i>, click <i>Set up a new connection or network</i>, and then double-click <i>Connect to the Internet</i>. From there, follow the instructions. If the network is password-protected, you will have to enter the password.", "<b>Windows 8:</b> Open the <i>Settings charm</i> and tap or click the Network icon (shaped like either five bars or a computer screen with a cable). Select the network you want to join, then tap or click <i>Connect</i>.", "<b>Mac OS X:</b> Click the AirPort icon (the icon shaped like a slice of pie near the top right of your screen). From there, select the network you want to join. If the network is password-protected, enter the password.", "<b>Ubuntu (Unity and Xfce):</b> Click the Network Indicator (the icon with two arrows near the upper right of your screen). From there, select the network you want to join. If the network is password-protected, enter the password.", "<b>Other Linux:</b> Oh, come on. I shouldn't have to be telling you this.", "Alternatively, if you have access to a wired Ethernet connection, you can simply plug the cable into your computer."])
                #else:
                    #self.errorPage()
            else:
                self._cacheLoaded = True

    # Hacky custom implementation of QWebView.load(),
    # which can load a saved new tab page as well as
    # the settings dialog.
    def load(self, url):
        if type(url) is QListWidgetItem:
            url = QUrl.fromUserInput(url.text())
        self._cacheLoaded = False
        dirname = url.path()
        self._url = url.toString()
        if url.scheme() == "nimbus":
            x = common.htmlToBase64("<!DOCTYPE html><html><head><title>" + tr("Settings") + "</title></head><body><object type=\"application/x-qt-plugin\" classid=\"settingsDialog\" style=\"position: fixed; top: 0; left: 0; width: 100%; height: 100%;\"></object></body></html>")
            QWebView.load(self, QUrl(x))
            return
        if url.toString() == "about:blank":
            if os.path.exists(settings.new_tab_page):
                loadwin = QWebView.load(self, QUrl.fromUserInput(settings.new_tab_page))
            else:
                loadwin = QWebView.load(self, url)
        else:
            loadwin = QWebView.load(self, url)

    # Method to replace all <audio> and <video> tags with <embed> tags.
    # This is mainly a hack for Windows, where <audio> and <video> tags are not
    # properly supported under PyQt4.
    def replaceAVTags(self):
        if not settings.setting_to_bool("content/ReplaceHTML5MediaTagsWithEmbedTags"):
            return
        audioVideo = self.page().mainFrame().findAllElements("audio, video")
        for element in audioVideo:
            attributes = []
            if not "width" in element.attributeNames():
                attributes.append("width=352")
            if not "height" in element.attributeNames():
                attributes.append("height=240")
            if not "autostart" in element.attributeNames():
                attributes.append("autostart=false")
            attributes += ["%s=\"%s\"" % (attribute, element.attribute(attribute),) for attribute in element.attributeNames()]
            if element.firstChild() != None:
                attributes += ["%s=\"%s\"" % (attribute, element.firstChild().attribute(attribute),) for attribute in element.firstChild().attributeNames()]
            embed = "<embed %s></embed>" % (" ".join(attributes),)
            element.replace(embed)

    # Set status bar message.
    def setStatusBarMessage(self, link="", title="", content=""):
        self._statusBarMessage = link

    # Set load progress.
    def setLoadProgress(self, progress):
        self._loadProgress = progress

    # Set the window title. If the title is an empty string,
    # set it to "New Tab".
    def setWindowTitle(self, title):
        if len(title) == 0:
            title = tr("New Tab")
        QWebView.setWindowTitle(self, title)

    # Returns a devilish face if in incognito mode;
    # else page icon.
    def icon(self):
        if self.incognito:
            return common.complete_icon("face-devilish")
        return QWebView.icon(self)

    # Function to update proxy list.
    def updateProxy(self):
        proxyType = str(settings.settings.value("proxy/Type"))
        if proxyType == "None":
            proxyType = "No"
        port = settings.settings.value("proxy/Port")
        if port == None:
            port = common.default_port
        user = str(settings.settings.value("proxy/User"))
        if user == "":
            user = None
        password = str(settings.settings.value("proxy/Password"))
        if password == "":
            password = None
        self.page().networkAccessManager().setProxy(QNetworkProxy(eval("QNetworkProxy." + proxyType + "Proxy"), str(settings.settings.value("proxy/Hostname")), int(port), user, password))

    # Updates content settings based on settings.settings.
    def updateContentSettings(self):
        self.settings().setAttribute(self.settings().AutoLoadImages, settings.setting_to_bool("content/AutoLoadImages"))
        self.settings().setAttribute(self.settings().JavascriptEnabled, settings.setting_to_bool("content/JavascriptEnabled"))
        self.settings().setAttribute(self.settings().JavaEnabled, settings.setting_to_bool("content/JavaEnabled"))
        self.settings().setAttribute(self.settings().PrintElementBackgrounds, settings.setting_to_bool("content/PrintElementBackgrounds"))
        self.settings().setAttribute(self.settings().FrameFlatteningEnabled, settings.setting_to_bool("content/FrameFlatteningEnabled"))
        self.settings().setAttribute(self.settings().PluginsEnabled, settings.setting_to_bool("content/PluginsEnabled"))
        self.settings().setAttribute(self.settings().TiledBackingStoreEnabled, settings.setting_to_bool("content/TiledBackingStoreEnabled"))
        self.settings().setAttribute(self.settings().SiteSpecificQuirksEnabled, settings.setting_to_bool("content/SiteSpecificQuirksEnabled"))

    # Updates network settings based on settings.settings.
    def updateNetworkSettings(self):
        self.settings().setAttribute(self.settings().XSSAuditingEnabled, settings.setting_to_bool("network/XSSAuditingEnabled"))
        self.settings().setAttribute(self.settings().DnsPrefetchEnabled, settings.setting_to_bool("network/DnsPrefetchEnabled"))

    # Handler for unsupported content.
    # This is where the content viewers are loaded.
    def handleUnsupportedContent(self, reply):
        url2 = reply.url()
        url = url2.toString()

        # Make sure the file isn't local, that content viewers are
        # enabled, and private browsing isn't enabled.
        if not url2.scheme() == "file" and settings.setting_to_bool("content/UseOnlineContentViewers") and not self.incognito and not self.isUsingContentViewer():
            for viewer in common.content_viewers:
                try:
                    for extension in viewer[1]:
                        if url.lower().endswith(extension):
                            QWebView.load(self, QUrl(viewer[0] % (url,)))
                            return
                except:
                    pass

        self.downloadFile(reply.request())

    # Downloads a file.
    def downloadFile(self, request):

        if request.url() == self.url():

            # If the file type can be converted to plain text, use savePage
            # method instead.
            for mimeType in ("text", "svg", "html", "xml", "xhtml",):
                if mimeType in str(self._contentType):
                    self.savePage()
                    return

        # Get file name for destination.
        fname = QFileDialog.getSaveFileName(None, tr("Save As..."), os.path.join(os.path.expanduser("~"), request.url().toString().split("/")[-1]), tr("All files (*)"))
        if type(fname) is tuple:
            fname = fname[0]
        if fname:
            reply = self.page().networkAccessManager().get(request)
            
            # Create a DownloadBar instance and append it to list of
            # downloads.
            downloadDialog = DownloadBar(reply, fname, None)
            self.downloads.append(downloadDialog)

            # Emit signal.
            self.downloadStarted.emit(downloadDialog)

    # Loads a page from the offline cache.
    def loadPageFromCache(self, url):
        m = hashlib.md5()
        m.update(common.shortenURL(url).encode('utf-8'))
        h = m.hexdigest()
        try: f = open(os.path.join(settings.offline_cache_folder, h), "r")
        except: traceback.print_exc()
        else:
            try: self.setHtml(f.read())
            except: traceback.print_exc()
            f.close()
            return True
        return False

    # Saves a page to the offline cache.
    def savePageToCache(self):
        if not self.incognito:
            if not os.path.exists(settings.offline_cache_folder):
                try: os.mkdir(settings.offline_cache_folder)
                except: return
            content = self.page().mainFrame().toHtml()
            m = hashlib.md5()
            m.update(common.shortenURL(self.url().toString()).encode('utf-8'))
            h = m.hexdigest()
            try: f = open(os.path.join(settings.offline_cache_folder, h), "w")
            except: traceback.print_exc()
            else:
                try: f.write(content)
                except: traceback.print_exc()
                f.close()

    # Saves the current page.
    # It partially supports saving edits to a page,
    # but this is pretty hacky and doesn't work all the time.
    def savePage(self):
        content = self.page().mainFrame().toHtml()
        if self.url().toString() in ("about:blank", "", QUrl.fromUserInput(settings.new_tab_page).toString(),) and not self._cacheLoaded:
            fname = settings.new_tab_page
            content = content.replace("&lt;", "<").replace("&gt;", ">").replace("<body contenteditable=\"true\">", "<body>")
        else:
            fname = QFileDialog.getSaveFileName(None, tr("Save As..."), os.path.join(os.path.expanduser("~"), self.url().toString().split("/")[-1]), tr("All files (*)"))
        if type(fname) is tuple:
            fname = fname[0]
        if fname:
            try: f = open(fname, "w")
            except: pass
            else:
                try: f.write(content)
                except: pass
                f.close()
                if sys.platform.startswith("linux"):
                    subprocess.Popen(["notify-send", "--icon=emblem-downloads", tr("Download complete: %s") % (os.path.split(fname)[1],)])
                else:
                    common.trayIcon.showMessage(tr("Download complete"), os.path.split(fname)[1])

    # Adds a QUrl to the browser history.
    def addHistoryItem(self, url):
        addHistoryItem(url.toString())

    # Redefine createWindow. Emits windowCreated signal so that others
    # can utilize the newly-created WebView instance.
    def createWindow(self, type):
        webview = WebView(incognito=self.incognito, parent=self.parent())
        self.webViews.append(webview)
        self.windowCreated.emit(webview)
        return webview

    # Convenience function.
    # Sets the zoom factor.
    def zoom(self):
        zoom = QInputDialog.getDouble(self, tr("Zoom"), tr("Set zoom factor:"), self.zoomFactor())
        if zoom[1]:
            self.setZoomFactor(zoom[0])

    # Convenience function.
    # Opens a very simple find text dialog.
    def find(self):
        if type(self._findText) is not str:
            self._findText = ""
        find = QInputDialog.getText(self, tr("Find"), tr("Search for:"), QLineEdit.Normal, self._findText)
        if find:
            self._findText = find[0]
        else:
            self._findText = ""
        self.findText(self._findText, QWebPage.FindWrapsAroundDocument)

    # Convenience function.
    # Find next instance of text.
    def findNext(self):
        if not self._findText:
            self.find()
        else:
            self.findText(self._findText, QWebPage.FindWrapsAroundDocument)

    # Convenience function.
    # Find previous instance of text.
    def findPrevious(self):
        if not self._findText:
            self.find()
        else:
            self.findText(self._findText, QWebPage.FindWrapsAroundDocument | QWebPage.FindBackward)

    # Opens a print dialog to print page.
    def printPage(self):
        printer = QPrinter()
        self.page().mainFrame().render(printer.paintEngine().painter())
        printDialog = QPrintDialog(printer)
        printDialog.open()
        printDialog.accepted.connect(lambda: self.print(printer))
        printDialog.exec_()

    # Opens a print preview dialog.
    def printPreview(self):
        printer = QPrinter()
        self.page().mainFrame().render(printer.paintEngine().painter())
        printDialog = QPrintPreviewDialog(printer, self)
        printDialog.paintRequested.connect(lambda: self.print(printer))
        printDialog.exec_()
        printDialog.deleteLater()