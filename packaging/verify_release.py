"""Exercise the real installer safely in an isolated folder (no shell integration)."""
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE = ROOT.parent/'releases'
INSTALL = ROOT/'安装验证'/'QuickDock'
SETUP = RELEASE/'QuickDock-1.1.0-Windows-x64-Setup.exe'


def main():
    manifest = json.loads((RELEASE/'build-manifest.json').read_text(encoding='utf-8'))
    checks = []
    def install():
        subprocess.run([str(SETUP), '/S', '/TESTMODE', '/D='+str(INSTALL)], check=True, timeout=60)
    install()
    assert (INSTALL/'QuickDock.exe').is_file()
    assert not (INSTALL/'shortcuts.json').exists()
    for relative, digest in manifest['files'].items():
        assert hashlib.sha256((INSTALL/relative).read_bytes()).hexdigest() == digest, relative
    checks.append('silent install into Unicode path; all installed file hashes match; no personal seed data')
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(INSTALL/'QuickDock.exe'), 0x80000000, 1, None, 3, 0, None)
    assert handle != wintypes.HANDLE(-1).value
    try:
        result = subprocess.run([str(SETUP), '/S', '/TESTMODE', '/D='+str(INSTALL)], timeout=30)
        assert result.returncode != 0, 'Installer must refuse an executable locked against modification'
    finally:
        kernel.CloseHandle(handle)
    checks.append('upgrade refuses a locked executable without terminating any process')
    subprocess.run([str(INSTALL/'QuickDock.exe'), '--smoke-test', str(ROOT/'smoke-installed.json')], check=True, timeout=40)
    smoke = json.loads((ROOT/'smoke-installed.json').read_text(encoding='utf-8'))
    assert smoke['passed'], smoke
    checks.extend(smoke['checks'])
    environment = os.environ.copy()
    environment['QUICKDOCK_TEST_LINK'] = str(INSTALL/'QuickDock-test.lnk')
    powershell = Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', '(New-Object -ComObject WScript.Shell).CreateShortcut($env:QUICKDOCK_TEST_LINK).TargetPath'], env=environment, capture_output=True, check=True)
    assert result.stdout.decode(errors='replace').strip().lower() == str(INSTALL/'QuickDock.exe').lower()
    checks.append('installer shortcut targets the installed executable')
    user_data = {'version':1, 'items':[{'id':'preserved','name':'User entry','target':'doc/example.txt'}], 'settings':{'ui_scale':1.25}}
    payload = json.dumps(user_data).encode('utf-8')
    (INSTALL/'shortcuts.json').write_bytes(payload)
    (INSTALL/'icons').mkdir(exist_ok=True)
    (INSTALL/'icons/user-icon.txt').write_text('preserve', encoding='utf-8')
    (INSTALL/'doc').mkdir(exist_ok=True)
    (INSTALL/'doc/example.txt').write_text('preserve', encoding='utf-8')
    install()
    assert (INSTALL/'shortcuts.json').read_bytes() == payload
    assert (INSTALL/'icons/user-icon.txt').read_text() == 'preserve'
    assert (INSTALL/'doc/example.txt').read_text() == 'preserve'
    checks.append('reinstall preserves entries, settings, icons and documents')
    subprocess.run([str(INSTALL/'Uninstall.exe'), '/S'], check=True, timeout=30)
    for _ in range(200):
        if not (INSTALL/'Uninstall.exe').exists() and not any((INSTALL/p).exists() for p in manifest['files']): break
        time.sleep(0.1)
    assert not (INSTALL/'QuickDock.exe').exists()
    assert not (INSTALL/'PySide6/QtCore.pyd').exists()
    assert not (INSTALL/'QuickDock-test.lnk').exists()
    assert (INSTALL/'shortcuts.json').read_bytes() == payload
    assert (INSTALL/'icons/user-icon.txt').read_text() == 'preserve'
    assert (INSTALL/'doc/example.txt').read_text() == 'preserve'
    checks.append('uninstall removes program and shortcut, preserving all user-created data')
    # Remove only this test's own data after verifying preservation.
    import shutil
    assert INSTALL.resolve().is_relative_to(ROOT.resolve())
    shutil.rmtree(INSTALL)
    assert not INSTALL.exists()
    checks.append('test data cleaned up and absence verified')
    (RELEASE/'验证结果.json').write_text(json.dumps({'passed':True,'checks':checks,'limits':['Tested on this Windows PC; a second clean PC was not available.','Installer test mode skips real desktop/start menu shortcuts and uninstall registration.','Launch execution was mocked; no power actions or automatic clicking were triggered.']}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS:', len(checks), 'checks')


if __name__ == '__main__': main()
