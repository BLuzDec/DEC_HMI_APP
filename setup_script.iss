; ==========================================================================
; Inno Setup Script for DecAutomation Studio
; ==========================================================================
;
; This script is called by build_installer.bat with:
;   ISCC /DMyAppVersion=X.Y.Z setup_script.iss
;
; The resulting installer is fully self-contained: no Python, TwinCAT,
; or any other runtime is required on the target machine.
; ==========================================================================

; Version passed from build_installer.bat via /D flag; fallback to 1.0.0
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppName=DecAutomation Studio
AppVersion={#MyAppVersion}
AppPublisher=DEC Group
AppId=0c82f26c-055e-471d-bbd9-784bf3d68507
DefaultDirName={autopf}\DecAutomation Studio
DefaultGroupName=DecAutomation Studio
DisableProgramGroupPage=yes
; Output filename includes the version number
OutputBaseFilename=DecAutomation_Studio_Setup_v{#MyAppVersion}
OutputDir=.\InstallerOutput
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
MinVersion=10.0
UninstallDisplayName=DecAutomation Studio v{#MyAppVersion}
; App icon (generated from Dec Group logo PNG)
SetupIconFile=Images\app_icon.ico
UninstallDisplayIcon={app}\DecAutomation Studio.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french";  MessagesFile: "compiler:Languages\French.isl"
Name: "german";  MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Bundle everything PyInstaller produced
Source: "dist\DecAutomationApp\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu
Name: "{group}\DecAutomation Studio";                          Filename: "{app}\DecAutomation Studio.exe"; IconFilename: "{app}\_internal\Images\app_icon.ico"
Name: "{group}\{cm:UninstallProgram,DecAutomation Studio}";    Filename: "{uninstallexe}"
; Desktop
Name: "{autodesktop}\DecAutomation Studio"; Filename: "{app}\DecAutomation Studio.exe"; IconFilename: "{app}\_internal\Images\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\DecAutomation Studio.exe"; Description: "{cm:LaunchProgram,DecAutomation Studio}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\external\automation_data.db"
Type: filesandordirs; Name: "{app}\external\DB_OPC_UA.db"
Type: filesandordirs; Name: "{app}\*.log"
