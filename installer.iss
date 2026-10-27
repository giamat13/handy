; Inno Setup script -> installer_output\Handy2Setup.exe
; Build:  ISCC.exe installer.iss   (after: pyinstaller Handy2.spec)
; Updates install OVER the existing app (never uninstall-then-install). Per-user install (no admin).
; Settings live in %APPDATA%\Handy (since 2.1.0; 2.0.x used %APPDATA%\Handy2, and the app moves those files over once on its
; first start) and are NOT touched by install or uninstall. This installer must never delete %APPDATA%\Handy or %APPDATA%\Handy2.

; the version comes from version.py (the release workflow passes /DMyAppVersion=...)
#ifndef MyAppVersion
  #define MyAppVersion "2.1.0"
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

var
  ExistingPage: TInputOptionWizardPage;
  RepairChosen: Boolean;
  UninstallDone: Boolean;

// the uninstaller of the copy that is already installed ('' when Handy 2 is not installed); same AppId as above
function ExistingUninstaller: String;
var
  Key, S: String;
begin
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B3A91C52-7D4E-4F68-A1C0-2E9D5F7A8B14}_is1';
  S := '';
  if not RegQueryStringValue(HKCU, Key, 'UninstallString', S) then
    RegQueryStringValue(HKLM, Key, 'UninstallString', S);
  Result := RemoveQuotes(S);
end;

// already installed: ask whether to update, repair or uninstall. Silent runs and the in-app updater skip the question and update.
procedure InitializeWizard;
begin
  if ExistingUninstaller = '' then
    Exit;
  ExistingPage := CreateInputOptionPage(wpWelcome, 'Handy 2 is already installed', 'What do you want to do?',
    'Choose an action:', True, False);
  ExistingPage.Add('Update to version {#MyAppVersion}');
  ExistingPage.Add('Repair (install all the program files again; your settings are kept)');
  ExistingPage.Add('Uninstall (your settings are kept)');
  ExistingPage.SelectedValueIndex := 0;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if ExistingPage <> nil then
    if PageID = ExistingPage.ID then
      Result := WizardSilent or IsUpdateRun;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Code: Integer;
begin
  Result := True;
  if ExistingPage = nil then
    Exit;
  if CurPageID <> ExistingPage.ID then
    Exit;
  RepairChosen := ExistingPage.SelectedValueIndex = 1;
  if ExistingPage.SelectedValueIndex = 2 then
  begin
    Exec(ExistingUninstaller, '', '', SW_SHOW, ewWaitUntilTerminated, Code);
    UninstallDone := True;
    Result := False;
    WizardForm.Close;   // nothing is left to install
  end;
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if UninstallDone then
    Confirm := False;
end;

// The in-app updater saves a copy of the running program before it starts this installer. When all files are in place
// we write done.flag; if it is missing afterwards (power loss, killed installer) the app puts the saved copy back.
procedure CurStepChanged(CurStep: TSetupStep);
var
  D: String;
begin
  if (CurStep = ssInstall) and RepairChosen then
  begin
    // repair also drops the MediaPipe copy that mp_path.py makes for non-ASCII user names (it is made again at the next start)
    DelTree(ExpandConstant('{commonappdata}\Handy2'), True, True, True);
    DelTree(ExpandConstant('{commonpub}\Handy2'), True, True, True);
    DelTree('C:\Handy2', True, True, True);
  end;
  if CurStep = ssPostInstall then
  begin
    D := ExpandConstant('{localappdata}\Handy2\update');
    ForceDirectories(D);
    SaveStringToFile(D + '\done.flag', '{#MyAppVersion}', False);
  end;
end;
