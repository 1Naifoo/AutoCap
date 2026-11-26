; AutoCap installer (Inno Setup 6)
; Built automatically by .github/workflows/build.yml
; Installs for the current user only, so no admin password is needed.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8F2C6B1E-5A3D-4C7E-9B21-AC0CA9A07CA9}
AppName=AutoCap
AppVersion={#AppVersion}
AppVerName=AutoCap {#AppVersion}
AppPublisher=Naif Omran
DefaultDirName={localappdata}\Programs\AutoCap
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=AutoCap-Setup
SetupIconFile=assets\autocap.ico
UninstallDisplayIcon={app}\AutoCap.exe
UninstallDisplayName=AutoCap
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "startup"; Description: "Start AutoCap automatically when Windows starts (recommended)"; GroupDescription: "Options:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Options:"; Flags: unchecked

[Files]
Source: "dist\AutoCap.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\AutoCap"; Filename: "{app}\AutoCap.exe"
Name: "{autodesktop}\AutoCap"; Filename: "{app}\AutoCap.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AutoCap"; ValueData: """{app}\AutoCap.exe"""; Tasks: startup

[Run]
Filename: "{app}\AutoCap.exe"; Description: "Start AutoCap now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM AutoCap.exe"; Flags: runhidden; RunOnceId: "StopAutoCap"

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\AutoCap"

[Code]
// Close a running copy before installing an update.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM AutoCap.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(300);
  Result := '';
end;

// Remove the "start with Windows" entry on uninstall, even if it was turned on from the tray menu.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'AutoCap');
end;
