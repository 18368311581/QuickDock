"""Build from the live source without changing personal data or source files."""
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VERSION = '1.0.0'
STAGE = HERE/'stage'
DIST = HERE/'dist'
RELEASE = ROOT/'releases'


def main():
    STAGE.mkdir(exist_ok=True)
    RELEASE.mkdir(exist_ok=True)
    files = [*ROOT.glob('*.py'), ROOT/'main.pyw', ROOT/'使用说明.html']
    manifest = {}
    for source in files:
        shutil.copy2(source, STAGE/source.name)
        manifest[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    for folder in ('assets', 'vendor'):
        shutil.copytree(ROOT/folder, STAGE/folder, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(HERE/'release_smoke.py', STAGE/'release_smoke.py')
    entry = STAGE/'main.pyw'
    text = entry.read_text(encoding='utf-8')
    original = "if __name__ == '__main__': main()"
    assert original in text
    text = text.replace(original, """if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        import release_smoke
        sys.exit(release_smoke.run(globals(), sys.argv[2]))
    main()
""")
    entry.write_text(text, encoding='utf-8')
    licenses = STAGE/'licenses'
    licenses.mkdir(exist_ok=True)
    shutil.copytree(HERE/'license-texts', licenses/'Qt', dirs_exist_ok=True)
    for package in ('PySide6-Essentials', 'shiboken6'):
        distribution = importlib.metadata.distribution(package)
        for item in distribution.files or []:
            if '/licenses/' in str(item).replace('\\', '/'):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    dest = licenses/package/str(item).replace('\\', '/').split('/licenses/', 1)[1]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
    python_license = Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists(): shutil.copy2(python_license, licenses/'Python-LICENSE.txt')
    (STAGE/'THIRD_PARTY_NOTICES.txt').write_text('QuickDock 1.0.0\n\nIncludes CPython 3.12, PySide6 / Qt 6 (LGPLv3), Shiboken6 and pypinyin 0.55.0 (MIT).\nQt shared libraries are shipped as replaceable files. No Qt library modifications.\nQt sources and license information: https://code.qt.io/ and https://www.qt.io/licensing/\nPySide sources: https://code.qt.io/pyside/pyside-setup.git/\npypinyin: https://github.com/mozillazg/python-pinyin\nSee licenses/ and vendor/pypinyin-0.55.0.dist-info/ for license texts.\nPyInstaller bootloader uses its GPL license with distribution exception: https://pyinstaller.org/en/stable/license.html\n', encoding='utf-8')
    build_env = os.environ.copy()
    # Other tools (such as Poppler) can expose incompatible DLLs on PATH.
    build_env['PATH'] = os.pathsep.join([str(Path(sys.base_prefix)), str(Path(sys.base_prefix)/'DLLs'), str(Path(os.environ['WINDIR'])/'System32'), os.environ['WINDIR']])
    build_env['PYTHONPATH'] = str(STAGE/'vendor')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--disable-windowed-traceback', '--onedir', '--contents-directory', '.', '--name', 'QuickDock', '--icon', str(STAGE/'assets/app-icon.ico'), '--paths', str(STAGE/'vendor'), '--collect-all', 'pypinyin', '--add-data', f'{STAGE / "assets"};assets', '--add-data', f'{STAGE / "使用说明.html"};.', '--add-data', f'{licenses};licenses', '--add-data', f'{STAGE / "THIRD_PARTY_NOTICES.txt"};.', '--distpath', str(DIST), '--workpath', str(HERE/'build'), '--specpath', str(HERE), str(entry)], check=True, env=build_env)
    app = DIST/'QuickDock'
    # Qt 6.11 imports the unversioned ICU API supplied by Windows 10+, not
    # third-party version-suffixed ICU builds. Do not redistribute OS ICU DLLs.
    for binary in app.glob('icu*.dll'):
        binary.unlink()
    import PySide6
    for binary in Path(PySide6.__file__).parent.glob('*140*.dll'):
        shutil.copy2(binary, app/binary.name)
    # Include pypinyin's upstream license metadata, without personal shortcuts/icons/files.
    shutil.copytree(STAGE/'vendor/pypinyin-0.55.0.dist-info', app/'vendor/pypinyin-0.55.0.dist-info', dirs_exist_ok=True)
    paths = sorted((p for p in app.rglob('*') if p.is_file()), key=lambda p: str(p).lower())
    (HERE/'install-files.nsh').write_text('\n'.join('SetOutPath "$INSTDIR'+('\\'+str(p.parent.relative_to(app)) if p.parent != app else '')+'"\nFile "'+str(p)+'"' for p in paths)+'\n', encoding='utf-8-sig')
    # Delete only the exact shipped files; all user-created data remains on uninstall.
    lines = ['Delete "$INSTDIR\\'+str(p.relative_to(app))+'"' for p in paths]
    directories = set()
    for path in paths:
        directory = path.parent
        while directory != app:
            directories.add(directory)
            directory = directory.parent
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        lines.append('RMDir "$INSTDIR\\'+str(directory.relative_to(app))+'"')
    (HERE/'uninstall-files.nsh').write_text('\n'.join(lines)+'\n', encoding='utf-8-sig')
    tools = HERE/'tools/nsis-3.12/makensis.exe'
    subprocess.run([str(tools), '/INPUTCHARSET', 'UTF8', '/V2', str(HERE/'installer.nsi')], check=True)
    manifest['build_versions'] = {p: importlib.metadata.version(p) for p in ('PyInstaller', 'PySide6-Essentials', 'shiboken6')}
    manifest['source'] = str(ROOT)
    manifest['personal_data_included'] = False
    manifest['files'] = {str(p.relative_to(app)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (RELEASE/'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    setup = RELEASE/f'QuickDock-{VERSION}-Windows-x64-Setup.exe'
    (RELEASE/(setup.name+'.sha256')).write_text(hashlib.sha256(setup.read_bytes()).hexdigest()+'  '+setup.name+'\n', encoding='utf-8')
    print(setup)


if __name__ == '__main__': main()
