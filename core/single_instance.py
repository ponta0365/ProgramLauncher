from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ERROR_ALREADY_EXISTS = 183

kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


class SingleInstanceGuard(QObject):
    def __init__(self, name: str, activate_callback=None) -> None:
        super().__init__()
        self.name = name
        self.activate_callback = activate_callback
        self.handle = None
        self.server = None
        self.server_name = name.replace("\\", "_")

    def set_activate_callback(self, callback) -> None:
        self.activate_callback = callback

    def acquire(self) -> bool:
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            return False

        last_error = ctypes.get_last_error()
        if last_error == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False

        self.handle = handle
        self._start_server()
        return True

    def signal_existing_instance(self) -> bool:
        socket = QLocalSocket(self)
        socket.connectToServer(self.server_name)
        if not socket.waitForConnected(500):
            return False
        socket.write(b"activate")
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        return True

    def release(self) -> None:
        if self.server is not None:
            self.server.close()
            QLocalServer.removeServer(self.server_name)
            self.server = None
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def _start_server(self) -> None:
        QLocalServer.removeServer(self.server_name)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._handle_new_connection)
        self.server.listen(self.server_name)

    def _handle_new_connection(self) -> None:
        if self.server is None:
            return
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.readyRead.connect(lambda s=socket: self._read_socket(s))
            socket.disconnected.connect(socket.deleteLater)

    def _read_socket(self, socket: QLocalSocket) -> None:
        payload = bytes(socket.readAll()).decode("utf-8", errors="ignore").strip().lower()
        if payload == "activate" and self.activate_callback is not None:
            self.activate_callback()
        socket.disconnectFromServer()
