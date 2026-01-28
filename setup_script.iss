; Inno Setup Script for ProAutomation Studio
; To use:
; 1. First, build your app with PyInstaller: pyinstaller main_window.spec
; 2. Open this file in the Inno Setup Compiler.
; 3. Go to Build -> Compile.
; 4. The final installer will be in the 'Output' sub-directory.

[Setup]
; NOTE: The value of AppName is used in copyrights and other places.
AppName=ProAutomation Studio
AppVersion=1.0
; AppId is used to identify the app. Don't change this once you have released your app.
AppId=0c82f26c-055e-471d-bbd9-784bf3d68507
DefaultDirName={autopf}\ProAutomation Studio
DefaultGroupName=ProAutomation Studio
DisableProgramGroupPage=yes
; The final installer executable will be named 'ProAutomation_Studio_Setup.exe'
OutputBaseFilename=ProAutomation_Studio_Setup
; Where the installer will be created.
OutputDir=.\InstallerOutput
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; This is the crucial line.
; It takes everything from the folder created by PyInstaller...
Source: "dist\ProAutomationApp\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ProAutomation Studio"; Filename: "{app}\ProAutomation Studio.exe"
Name: "{group}\{cm:UninstallProgram,ProAutomation Studio}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ProAutomation Studio"; Filename: "{app}\ProAutomation Studio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ProAutomation Studio.exe"; Description: "{cm:LaunchProgram,ProAutomation Studio}"; Flags: nowait postinstall skipifsilent
