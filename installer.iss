; Inno Setup script -> installer_output\Handy2Setup.exe
; Build:  ISCC.exe installer.iss   (after: pyinstaller Handy2.spec)
; Updates install OVER the existing app (never uninstall-then-install). Per-user install (no admin).
; Settings live in %APPDATA%\Handy2 and are NOT touched by install or uninstall.

; the version comes from version.py (the release workflow passes /DMyAppVersion=...)
#ifndef MyAppVersion
  #define MyAppVersion "2.0.0"
#endif

[Setup]
AppId={{B3A91C52-7D4E-4F68-A1C0-2E9D5F7A8B14}
AppName=Handy 2
AppVersion={#MyAppVersion}
AppPublisher=Handy 2
DefaultDirName={autopf}\Handy2
DefaultGroupName=Handy 2
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=Handy2Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icon.ico
LicenseFile=LICENSE
UninstallDisplayName=Handy 2
UninstallDisplayIcon={app}\Handy2.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\Handy2\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; an update replaces the program's own files completely (no stale libraries from older versions); settings live elsewhere
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Handy 2"; Filename: "{app}\Handy2.exe"
Name: "{autodesktop}\Handy 2"; Filename: "{app}\Handy2.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Handy2.exe"; Description: "Start Handy 2"; Flags: nowait postinstall skipifsilent
; started by the in-app updater (Handy2Setup.exe /SILENT /update=1): relaunch the app when the update is done
Filename: "{app}\Handy2.exe"; Flags: nowait; Check: IsUpdateRun

[Code]
function IsUpdateRun: Boolean;
begin
  Result := ExpandConstant('{param:update|0}') = '1';
end;

// The in-app updater saves a copy of the running program before it starts this installer. When all files are in place
// we write done.flag; if it is missing afterwards (power loss, killed installer) the app puts the saved copy back.
procedure CurStepChanged(CurStep: TSetupStep);
var
  D: String;
begin
  if CurStep = ssPostInstall then
  begin
    D := ExpandConstant('{localappdata}\Handy2\update');
    ForceDirectories(D);
    SaveStringToFile(D + '\done.flag', '{#MyAppVersion}', False);
  end;
end;
