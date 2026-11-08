"""Per-user process lock with local activation IPC."""
from pathlib import Path
from PySide6 import QtCore
from PySide6.QtNetwork import QLocalServer, QLocalSocket

class SingleInstance(QtCore.QObject):
    activated = QtCore.Signal()
    def __init__(self, directory=None, name='Inseven.QuickDock.Desktop.v1'):
        super().__init__()
        directory = Path(directory) if directory else Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.GenericDataLocation))/'QuickDock'/'runtime'
        directory.mkdir(parents=True,exist_ok=True)
        self.name = name
        self.lock = QtCore.QLockFile(str(directory/'instance.lock'))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self.receive)
    def notify_existing(self):
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(150): return False
        socket.disconnectFromServer()
        return True
    def acquire(self):
        if self.notify_existing(): return False
        if not self.lock.tryLock(0):
            # The first process may still be starting its local server.
            for _ in range(8):
                if self.notify_existing(): break
                QtCore.QThread.msleep(50)
            return False
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            self.lock.unlock()
            raise RuntimeError('无法创建单实例通信入口：'+self.server.errorString())
        return True
    def receive(self):
        while self.server.hasPendingConnections():
            socket=self.server.nextPendingConnection()
            socket.disconnectFromServer();socket.deleteLater()
            self.activated.emit()
    def close(self):
        self.server.close();self.lock.unlock()
