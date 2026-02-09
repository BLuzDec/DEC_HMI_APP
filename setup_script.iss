; ==========================================================================
; Inno Setup Script for ProAutomation Studio
; ==========================================================================
;
; Build steps:
;   1. Install dependencies:      pip install -r requirements.txt pyinstaller
;   2. Build with PyInstaller:    pyinstaller main_window.spec
;   3. Open this file in Inno Setup Compiler (https://jrsoftware.org/isinfo.php)
;   4. Build -> Compile
;   5. Installer is created in .\InstallerOutput\
;
; The resulting installer is fully self-contained: no Python, TwinCAT,
; or any other runtime is required on the target machine.
; ==========================================================================

[Setup]
AppName=ProAutomation Studio
AppVersion=1.0.0
AppPublisher=DEC Group
AppId=0c82f26c-055e-471d-bbd9-784bf3d68507
DefaultDirName={autopf}\ProAutomation Studio
DefaultGroupName=ProAutomation Studio
DisableProgramGroupPage=yes
OutputBaseFilename=ProAutomation_Studio_Setup
OutputDir=.\InstallerOutput
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
; Minimum Windows 10
MinVersion=10.0
; Uninstall info
UninstallDisplayName=ProAutomation Studio
; If you have a .ico file, uncomment and point to it:
; SetupIconFile=Images\app_icon.ico
; UninstallDisplayIcon={app}\ProAutomation Studio.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french";  MessagesFile: "compiler:Languages\French.isl"
Name: "german";  MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Bundle everything PyInstaller produced
Source: "dist\ProAutomationApp\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; VC++ redistributable (if you include it – optional)
; Source: "redist\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
; Start Menu
Name: "{group}\ProAutomation Studio";                          Filename: "{app}\ProAutomation Studio.exe"
Name: "{group}\{cm:UninstallProgram,ProAutomation Studio}";    Filename: "{uninstallexe}"
; Desktop (user-selectable)
Name: "{autodesktop}\ProAutomation Studio"; Filename: "{app}\ProAutomation Studio.exe"; Tasks: desktopicon

[Run]
; Offer to launch after installation
Filename: "{app}\ProAutomation Studio.exe"; Description: "{cm:LaunchProgram,ProAutomation Studio}"; Flags: nowait postinstall skipifsilent

; Optional: install VC++ runtime silently if bundled
; Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/quiet /norestart"; StatusMsg: "Installing Visual C++ Runtime..."; Flags: waituntilterminated

[UninstallDelete]
; Clean up any database / log files the app may have created at runtime
Type: filesandordirs; Name: "{app}\external\automation_data.db"
Type: filesandordirs; Name: "{app}\external\DB_OPC_UA.db"
Type: filesandordirs; Name: "{app}\*.log"
