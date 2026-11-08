"""Power shortcuts. Shutdown always requires explicit confirmation."""
import os, sys, subprocess
from pathlib import Path
from PySide6 import QtWidgets, QtGui, QtCore


def run_action(action, ask, run):
    if action == 'shutdown':
        if not ask(): return False
        arguments = ['/s', '/t', '0']
    elif action == 'hibernate':
        arguments = ['/h']
    else:
        raise ValueError('未知电源操作')
    run([str(Path(os.environ.get('WINDIR', r'C:\Windows'))/'System32/shutdown.exe'), *arguments])
    return True


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon(str(Path(__file__).resolve().parents[1]/'assets/app-icon.ico')))
    def confirm():
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Warning, '确认立即关机',
            '确定要立即关闭电脑吗？\n请先保存正在编辑的文件。',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel)
        box.button(QtWidgets.QMessageBox.Yes).setText('立即关机')
        box.button(QtWidgets.QMessageBox.Cancel).setText('取消')
        box.setDefaultButton(QtWidgets.QMessageBox.Cancel)
        box.setEscapeButton(QtWidgets.QMessageBox.Cancel)
        box.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        return box.exec() == QtWidgets.QMessageBox.Yes
    def execute(command):
        result = subprocess.run(command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            import locale
            message = (result.stderr or result.stdout).decode(locale.getpreferredencoding(False), errors='replace').strip()
            raise RuntimeError(message or f'Windows 返回错误 {result.returncode}')
    try: run_action(sys.argv[1] if len(sys.argv)>1 else '', confirm, execute)
    except Exception as exc: QtWidgets.QMessageBox.warning(None, '操作未完成', str(exc))

if __name__ == '__main__': main()
