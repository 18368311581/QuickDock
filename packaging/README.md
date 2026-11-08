# QuickDock Windows 打包

实际源代码来自此目录的上一级桌面 QuickDock，禁止从历史目录覆盖。
构建过程只复制源文件到 stage，不复制 shortcuts.json、icons、doc、files 或其他个人目录。
程序使用 PyInstaller onedir、contents-directory=.，让资源和可写数据保持在安装目录。
安装器为 NSIS 3.12，按当前用户安装，不要求管理员权限。

构建环境：Python 3.12.2、PySide6-Essentials 6.11.2、Shiboken6 6.11.2、PyInstaller 6.22.3。
`.venv` 只用于此项目，复用本机 PySide6；打包工具未全局安装。

在 PowerShell 7 中运行：

```powershell
& .\.venv\Scripts\python.exe .\build_release.py
& .\.venv\Scripts\python.exe .\verify_release.py
```

stage/main.pyw 仅增加显式 `--smoke-test REPORT.json` 自检入口；原始 main.pyw 保持不变。
自检只使用临时数据、独立 IPC 名称和模拟启动，不触发自动鼠标或电源操作。
NSIS `/TESTMODE` 将快捷方式创建在隔离安装目录，不写桌面、开始菜单和卸载注册项。
测试覆盖真实安装文件、快捷方式目标、重新安装不覆盖数据，以及卸载保留用户数据。

注意 DLL 搜索污染：构建子进程使用精简 PATH，且不携带第三方或操作系统的 icu*.dll。
Qt 6.11 使用 Windows 的无版本后缀 ICU API；本机 Poppler 的 ICU 78 同名库不兼容。
安装器清单精确列举程序文件，卸载不用递归删除安装目录，以免删除用户数据。

工具下载来源：
- https://pyinstaller.org/
- https://nsis.sourceforge.io/Download
- https://downloads.sourceforge.net/project/nsis/NSIS%203/3.12/nsis-3.12.zip
- Qt 许可证正文来自 https://github.com/qt/qtbase/tree/v6.11.2/LICENSES

发布后仍需在另一台无 Python 环境的 Windows 10/11 电脑完成实际使用验收。
