"""Current-user startup shortcut; no administrator permission required."""
import base64, os, subprocess, sys, uuid, winreg
from pathlib import Path

APPROVAL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder'

class StartupManager:
    def __init__(self, root, startup_dir=None):
        self.root = Path(root).resolve()
        self.shortcut = (Path(startup_dir) if startup_dir is not None else Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup')/'QuickDock.lnk'
    def _read_approval(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVAL_KEY) as key:
                return winreg.QueryValueEx(key, self.shortcut.name)
        except FileNotFoundError: return None
    def _delete_approval(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVAL_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self.shortcut.name)
        except FileNotFoundError: pass
    def _write_approval(self, value):
        if value is None: self._delete_approval()
        else:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, APPROVAL_KEY) as key:
                winreg.SetValueEx(key, self.shortcut.name, 0, value[1], value[0])
    def is_enabled(self):
        if not self.shortcut.is_file(): return False
        approval = self._read_approval()
        if approval and approval[1] == winreg.REG_BINARY and approval[0]:
            return approval[0][0] in (2, 6)
        return True
    def snapshot(self):
        return (self.shortcut.read_bytes() if self.shortcut.exists() else None, self._read_approval())
    def restore(self, snapshot):
        content, approval = snapshot
        if content is None:
            self.shortcut.unlink(missing_ok=True)
        else:
            self.shortcut.parent.mkdir(parents=True, exist_ok=True)
            self.shortcut.write_bytes(content)
        self._write_approval(approval)
    def _create_shortcut(self):
        self.shortcut.parent.mkdir(parents=True, exist_ok=True)
        executable = Path(sys.executable)
        if not getattr(sys, 'frozen', False): executable = executable.with_name('pythonw.exe')
        if not executable.is_file(): raise FileNotFoundError('未找到用于启动 QuickDock 的程序：'+str(executable))
        arguments = '' if getattr(sys, 'frozen', False) else '"'+str(self.root/'main.pyw')+'"'
        temporary = self.shortcut.with_name('QuickDock-'+uuid.uuid4().hex+'.lnk')
        quote = lambda value: "'"+str(value).replace("'", "''")+"'"
        script = "$ErrorActionPreference='Stop'\n$shell=New-Object -ComObject WScript.Shell\n"
        script += '$link=$shell.CreateShortcut('+quote(temporary)+')\n'
        for field,value in [('TargetPath',executable),('Arguments',arguments),('WorkingDirectory',self.root),('IconLocation',str(self.root/'assets/app-icon.ico')+',0'),('Description','QuickDock')]:
            script += '$link.'+field+'='+quote(value)+'\n'
        script += '$link.Save()\n'
        script += '$check=$shell.CreateShortcut('+quote(temporary)+')\n'
        script += 'if ($check.TargetPath -ne '+quote(executable)+' -or $check.Arguments -ne '+quote(arguments)+') { throw "Startup shortcut validation failed" }'
        powershell = Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        try:
            encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
            result = subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=20)
            if result.returncode or not temporary.is_file(): raise OSError('无法创建开机启动快捷方式，请检查启动文件夹的写入权限。')
            os.replace(temporary,self.shortcut)
        finally: temporary.unlink(missing_ok=True)
    def set_enabled(self, enabled):
        before = self.snapshot()
        try:
            if enabled:
                self._create_shortcut()
                # Clear only this shortcut's old Task Manager disable override.
                self._delete_approval()
            else:
                self.shortcut.unlink(missing_ok=True)
            if self.is_enabled() != bool(enabled): raise OSError('Windows 启动项状态未能更新。')
        except Exception:
            self.restore(before)
            raise
