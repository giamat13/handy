#ifndef MyAppName
  #define MyAppName "Handy"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "Handy"
#endif
#ifndef MyAppExeName
  #define MyAppExeName "Handy.exe"
#endif
#ifndef MyReleaseDir
  #define MyReleaseDir "..\\release"
#endif
#ifndef MyOutputDir
  #define MyOutputDir MyReleaseDir
#endif
#ifndef MyOutputBaseFilename
  #define MyOutputBaseFilename MyAppName + "-Setup"
#endif
#ifndef MySetupIconFile
  #define MySetupIconFile "..\\build\\icon.ico"
#endif

[Setup]
AppId={{F343D84C-7A27-44E0-99A7-25D746E21064}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputBaseFilename}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
CloseApplications=yes
RestartApplications=no
SetupIconFile={#MySetupIconFile}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#MyReleaseDir}\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  IsUpgradeInstall: Boolean;

function InstalledVersionKey: String;
begin
  Result := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{F343D84C-7A27-44E0-99A7-25D746E21064}_is1';
end;

function TryGetInstalledValue(const ValueName: String; var Value: String): Boolean;
begin
  Result :=
    RegQueryStringValue(HKLM64, InstalledVersionKey(), ValueName, Value) or
    RegQueryStringValue(HKLM, InstalledVersionKey(), ValueName, Value);
end;

function IsExistingInstallDetected: Boolean;
var
  InstallLocation: String;
begin
  Result := TryGetInstalledValue('Inno Setup: App Path', InstallLocation) or
            TryGetInstalledValue('InstallLocation', InstallLocation);
end;

procedure InitializeWizard();
var
  InstalledVersion: String;
begin
  IsUpgradeInstall := IsExistingInstallDetected();

  if IsUpgradeInstall then
  begin
    WizardForm.WelcomeLabel1.Caption := 'Handy is already installed on this computer.';

    if TryGetInstalledValue('DisplayVersion', InstalledVersion) then
      WizardForm.WelcomeLabel2.Caption :=
        'Setup will update your existing Handy installation from version ' +
        InstalledVersion + ' to version {#MyAppVersion}.'
    else
      WizardForm.WelcomeLabel2.Caption :=
        'Setup will update your existing Handy installation to version {#MyAppVersion}.';

    WizardForm.NextButton.Caption := '&Update';
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if IsUpgradeInstall and (CurPageID = wpReady) then
    WizardForm.NextButton.Caption := '&Update';
end;
