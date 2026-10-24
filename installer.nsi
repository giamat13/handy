; NSIS script -> installer_output\Handy2-NSIS-Setup-<version>.exe
; Build:  makensis /DVERSION=2.1.0 installer.nsi   (after: pyinstaller Handy2.spec)
; The same per-user install as installer.iss (no admin). The file name does NOT start with "Handy2Setup", on purpose: the in-app
; updater only downloads and runs Handy2Setup*.exe (the Inno Setup installer), so this one is for people who prefer NSIS.
; Settings live in %APPDATA%\Handy and are NOT touched by install or uninstall.

!ifndef VERSION
  !define VERSION "2.1.0"
!endif

Unicode true
!include "MUI2.nsh"

Name "Handy 2"
OutFile "installer_output\Handy2-NSIS-Setup-${VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\Handy2"
InstallDirRegKey HKCU "Software\Handy2-NSIS" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_ICON "icon.ico"
!define MUI_UNICON "icon.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\Handy2.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Start Handy 2"

!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Handy2-NSIS"

Section "Handy 2" SecMain
  SetOutPath "$INSTDIR"
  ; an update replaces the program's own files completely (no stale libraries from older versions)
  RMDir /r "$INSTDIR\_internal"
  File /r "dist\Handy2\*.*"
  File "LICENSE"
  File "THIRD_PARTY_NOTICES.md"

  CreateDirectory "$SMPROGRAMS\Handy 2"
  CreateShortcut "$SMPROGRAMS\Handy 2\Handy 2.lnk" "$INSTDIR\Handy2.exe"
  CreateShortcut "$DESKTOP\Handy 2.lnk" "$INSTDIR\Handy2.exe"

  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Handy2-NSIS" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "Handy 2"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\Handy2.exe"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\Handy 2.lnk"
  RMDir /r "$SMPROGRAMS\Handy 2"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "Software\Handy2-NSIS"
SectionEnd
