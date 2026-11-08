"""Safe frozen-build validation. Runs only with --smoke-test REPORT.json."""
import json
import os
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch


def run(namespace, report_path):
    # Exercise the real Windows Qt platform and font engine, while keeping test
    # windows and tray icons hidden so the user's desktop stays undisturbed.
    os.environ['QT_QPA_PLATFORM'] = 'windows'
    report_path = Path(report_path).resolve()
    report = {'passed': False, 'checks': []}
    dock = None
    try:
        QtCore, QtGui, QtWidgets = (namespace[n] for n in ('QtCore', 'QtGui', 'QtWidgets'))
        app = QtWidgets.QApplication([])
        app.setQuitOnLastWindowClosed(False)
        root = namespace['ROOT']
        assert (root/'QuickDock.exe').is_file(), str(root)
        assert not QtGui.QIcon(str(root/'assets/app-icon.ico')).isNull()
        assert not QtGui.QPixmap(str(root/'assets/combo-down.svg')).isNull()
        report['checks'].append('frozen executable, ICO and SVG resources')
        assert namespace['aliases']('快捷入口') == ('kuaijierukou', 'kjrk')
        report['checks'].append('offline pinyin dictionaries')
        with tempfile.TemporaryDirectory(prefix='QuickDock-smoke-') as temp:
            data = Path(temp)/'用户数据'
            store = namespace['Store'](data)
            assert store.data['items'] == []
            store.data['items'] = [dict(id='demo', name='测试入口', target='https://example.com', description='', icon='', arguments='', cwd='')]
            store.save()
            other = namespace['Store'](data)
            other.data['settings']['external'] = 1
            other.save()
            store.data['settings']['local'] = 2
            store.save()
            assert namespace['Store'](data).data['settings'] == {'external': 1, 'local': 2}
            assert store.path.with_suffix('.json.bak').is_file()
            report['checks'].append('temporary data, atomic save, backup and concurrent merge')
            with patch.object(namespace['LauncherHotkey'], 'register', return_value=False), \
                 patch.object(namespace['Mini'], 'setVisible'), \
                 patch.object(QtWidgets.QSystemTrayIcon, 'show'):
                dock = namespace['Dock'](store)
            dock.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
            assert dock.tabs.count() == 3
            assert not dock.mouse_page.feature_enabled and not dock.mouse_page.active
            assert not dock.pin_page.enabled
            dock.search.setText('csrk')
            app.processEvents()
            assert dock.list.currentItem().data(QtCore.Qt.UserRole)['id'] == 'demo'
            assert dock.list.currentRow() == 0
            report['checks'].append('three pages, pinyin search and disabled auxiliary features')
            with patch.object(QtGui.QDesktopServices, 'openUrl', return_value=True) as launch:
                dock.open_entry(store.data['items'][0])
                launch.assert_called_once()
            local = data/'样例.txt'
            local.write_text('sample', encoding='utf-8')
            with patch('os.startfile') as launch:
                dock.open_entry(dict(target='样例.txt'))
                launch.assert_called_once_with(str(local))
            report['checks'].append('web and relative file launch using mocked execution')
            from startup import StartupManager
            startup = StartupManager(root, startup_dir=Path(temp)/'Startup')
            startup._create_shortcut()
            assert startup.shortcut.is_file()
            report['checks'].append('startup shortcut points to frozen EXE; no registry changes')
            from settings_dialog import SettingsDialog, HelpDialog
            # The guide belongs to the application resources, while test data stays temporary.
            (data/'使用说明.html').write_bytes((root/'使用说明.html').read_bytes())
            settings, help_dialog = SettingsDialog(dock), HelpDialog(dock)
            assert '使用说明' in help_dialog.guide_label.text()
            editor = namespace['Editor'](dock)
            for scale in (0.75, 1.0, 1.5):
                dock.apply_ui_scale(scale)
                app.processEvents()
                assert dock.width() > 0 and dock.height() > 0
            dock.apply_ui_scale(1.0)
            dock.show()
            app.processEvents()
            dock.grab().save(str(report_path.with_suffix('.png')))
            editor.hide(); settings.hide(); help_dialog.hide()
            report['checks'].append('settings, guide, editor and 75/100/150 percent layout')
            from single_instance import SingleInstance
            first = SingleInstance(Path(temp)/'ipc', name='QuickDock.Smoke.'+os.urandom(8).hex())
            assert first.acquire()
            second = SingleInstance(Path(temp)/'ipc', name=first.name)
            assert not second.acquire()
            app.processEvents()
            first.close()
            report['checks'].append('isolated single-instance lock and activation IPC')
            dock.mouse_page.shutdown(); dock.pin_page.shutdown()
            dock.launcher_hotkey.close(); dock.tray.hide(); dock.mini.hide(); dock.hide()
            dock.data_watcher.blockSignals(True)
            dock.deleteLater(); app.processEvents()
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['passed'] else 1
