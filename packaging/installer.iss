; Installer di BreakFromAeye (Inno Setup 6).
; Build:  ISCC.exe /DAppVersion=1.0.0 packaging\installer.iss      (dopo aver creato dist\BreakFromAeye con PyInstaller)
; Risultato: dist\BreakFromAeye-Setup-<versione>.exe

#define MyAppName "BreakFromAeye"
#define MyAppExe "BreakFromAeye.exe"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{B7C1F2A4-5E3D-4B8A-9C61-2F0A7D9E4C11}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher=BreakFromAeye
AppPublisherURL=https://github.com/lorenzovitale1/BreakFromAeye
AppSupportURL=https://github.com/lorenzovitale1/BreakFromAeye/issues
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=BreakFromAeye-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; installazione per l'utente corrente (nessun permesso di amministratore); con la finestra di dialogo si può scegliere "per tutti"
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; il programma tiene un mutex con questo nome: l'installer capisce se è in esecuzione (anche nascosto nell'area di notifica)
AppMutex=BreakFromAeyeMutex
CloseApplications=yes

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
italian.AutoStart=Avvia BreakFromAeye con Windows (resta nell'area di notifica)
english.AutoStart=Start BreakFromAeye with Windows (stays in the notification area)
italian.RemoveData=Vuoi eliminare anche le impostazioni e la calibrazione salvate?
english.RemoveData=Do you also want to delete your saved settings and calibration?

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "{cm:AutoStart}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\BreakFromAeye\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; \
  ValueData: """{app}\{#MyAppExe}"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if not UninstallSilent then
      if MsgBox(CustomMessage('RemoveData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(ExpandConstant('{userappdata}\BreakFromAeye'), True, True, True);
end;
