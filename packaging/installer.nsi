Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
Name "QuickDock"
OutFile "..\releases\QuickDock-1.1.0-Windows-x64-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\QuickDock"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "QuickDock 1.1.0"
Icon "stage\assets\app-icon.ico"
UninstallIcon "stage\assets\app-icon.ico"
VIProductVersion "1.1.0.0"
VIAddVersionKey /LANG=2052 "ProductName" "QuickDock"
VIAddVersionKey /LANG=2052 "FileDescription" "QuickDock 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "1.1.0"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Jiang Peichen / Inseven"
Var TestMode
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\QuickDock.exe"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "此安装包需要 64 位 Windows 10 或 Windows 11。" /SD IDOK
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "此安装包需要 Windows 10 或更新版本。" /SD IDOK
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastBuild} 17763
    MessageBox MB_ICONSTOP "此安装包需要 Windows 10 1809 或更新版本。" /SD IDOK
    Abort
  ${EndIf}
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/TESTMODE" $1
  ${IfNot} ${Errors}
    StrCpy $TestMode "1"
  ${EndIf}
FunctionEnd

Function CheckRunning
  ; Never terminate a running application. Abort upgrades until the user exits it.
  IfFileExists "$INSTDIR\QuickDock.exe" 0 done
  ClearErrors
  FileOpen $0 "$INSTDIR\QuickDock.exe" a
  ${If} ${Errors}
    MessageBox MB_ICONSTOP "请先从托盘退出已安装的 QuickDock，然后重新安装。" /SD IDOK
    Abort
  ${EndIf}
  FileClose $0
done:
FunctionEnd

Section "QuickDock"
  Call CheckRunning
  SetShellVarContext current
  !include "install-files.nsh"
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  ${If} $TestMode == "1"
    FileOpen $0 "$INSTDIR\.quickdock-install-test" w
    FileClose $0
    CreateShortcut "$INSTDIR\QuickDock-test.lnk" "$INSTDIR\QuickDock.exe" "" "$INSTDIR\assets\app-icon.ico"
  ${Else}
    CreateDirectory "$SMPROGRAMS\QuickDock"
    CreateShortcut "$SMPROGRAMS\QuickDock\QuickDock.lnk" "$INSTDIR\QuickDock.exe" "" "$INSTDIR\assets\app-icon.ico"
    CreateShortcut "$SMPROGRAMS\QuickDock\卸载 QuickDock.lnk" "$INSTDIR\Uninstall.exe"
    CreateShortcut "$DESKTOP\QuickDock.lnk" "$INSTDIR\QuickDock.exe" "" "$INSTDIR\assets\app-icon.ico"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Inseven.QuickDock" "DisplayName" "QuickDock"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Inseven.QuickDock" "DisplayVersion" "1.1.0"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Inseven.QuickDock" "Publisher" "Jiang Peichen / Inseven"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Inseven.QuickDock" "DisplayIcon" "$INSTDIR\QuickDock.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Inseven.QuickDock" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Inseven.QuickDock" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Inseven.QuickDock" "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Inseven.QuickDock" "NoRepair" 1
  ${EndIf}
SectionEnd

Function un.onInit
  IfFileExists "$INSTDIR\QuickDock.exe" 0 done
  ClearErrors
  FileOpen $0 "$INSTDIR\QuickDock.exe" a
  ${If} ${Errors}
    MessageBox MB_ICONSTOP "请先从托盘退出 QuickDock，再卸载。入口、图标和文件将保留。" /SD IDOK
    Abort
  ${EndIf}
  FileClose $0
done:
FunctionEnd

Section "Uninstall"
  SetShellVarContext current
  ; Only remove the startup link if it points to this installation.
  ReadRegStr $1 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Inseven.QuickDock" "InstallLocation"
  IfFileExists "$INSTDIR\.quickdock-install-test" test_cleanup
  ${If} $1 == $INSTDIR
    System::Call 'kernel32::SetEnvironmentVariableW(w "QUICKDOCK_UNINSTALL_ROOT", w "$INSTDIR") i .r0'
    nsExec::ExecToStack `"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -Command "$$p=Join-Path ([Environment]::GetFolderPath('Startup')) 'QuickDock.lnk'; if(Test-Path -LiteralPath $$p){$$s=(New-Object -ComObject WScript.Shell).CreateShortcut($$p); if($$s.TargetPath -eq (Join-Path $$env:QUICKDOCK_UNINSTALL_ROOT 'QuickDock.exe')){Remove-Item -LiteralPath $$p}}"`
    Pop $0
    Pop $0
    Delete "$DESKTOP\QuickDock.lnk"
    Delete "$SMPROGRAMS\QuickDock\QuickDock.lnk"
    Delete "$SMPROGRAMS\QuickDock\卸载 QuickDock.lnk"
    RMDir "$SMPROGRAMS\QuickDock"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Inseven.QuickDock"
  ${EndIf}
  Goto remove_program
test_cleanup:
  Delete "$INSTDIR\QuickDock-test.lnk"
  Delete "$INSTDIR\.quickdock-install-test"
remove_program:
  !include "uninstall-files.nsh"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
