; Inno Setup script for FlowBooks (Windows installer).
; Built in CI: iscc /DAppVersion=<x.y.z> FlowBooks.iss
; Paths are relative to this .iss file (packaging/windows).
;
; All user data (.env, company databases, uploads, backups, logs) lives in
; %LOCALAPPDATA%\SlowBooksPro — this installer never writes there, upgrades
; replace only {app}, and the uninstaller leaves the data intact.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{d5ad9469-4632-56da-a9dd-81e1f18dc85d}
AppName=FlowBooks
AppVersion={#AppVersion}
AppPublisher=FlowBooks distribution
AppPublisherURL=https://github.com/ceember/FlowBooks
DefaultDirName={autopf}\FlowBooks
DefaultGroupName=FlowBooks
UninstallDisplayIcon={app}\FlowBooks.exe
OutputDir=.
OutputBaseFilename=FlowBooks-Setup-x64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
; LICENSE section 13: the installer shows the license and requires acceptance.
LicenseFile=..\..\LICENSE
DisableProgramGroupPage=yes
; Close FlowBooks before upgrade/uninstall. Standard files-in-use handling
; may ask to close an app; never force-stop unrelated company instances.
CloseApplications=yes

; An upgrade must not layer today's bundle over last month's. Inno Setup
; only overwrites files it ships; everything else under {app} survives, so
; every upgrade left the previous build's *.dist-info trees (and any module
; the new build dropped) in _internal\. importlib.metadata then reported
; whichever version it found first — cryptography 48.0.1 while the 50.0.1
; extension was the code running (2.9.0 gate, skytech). User data is never
; under {app} (see the header), so clearing it is safe.
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\FlowBooks\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
; The license the wizard showed, kept beside the program.
Source: "..\..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"
; Microsoft's Evergreen WebView2 bootstrapper (~2 MB), downloaded by CI.
; Only executed when the runtime is missing (see [Run] Check) — Windows 11
; and most Windows 10 machines already have it.
Source: "MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\FlowBooks"; Filename: "{app}\FlowBooks.exe"
Name: "{group}\Uninstall FlowBooks"; Filename: "{uninstallexe}"
Name: "{autodesktop}\FlowBooks"; Filename: "{app}\FlowBooks.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; \
  StatusMsg: "Installing the Microsoft WebView2 runtime (app window component)..."; \
  Check: not IsWebView2Installed; Flags: waituntilterminated
Filename: "{app}\FlowBooks.exe"; Description: "Launch FlowBooks"; Flags: nowait postinstall skipifsilent

[Code]
// WebView2 Evergreen runtime detection — same registry keys Microsoft
// documents (and desktop_launcher.py checks at runtime as the fallback).
function IsWebView2Installed(): Boolean;
var
  Version: String;
begin
  Result :=
    (RegQueryStringValue(HKLM,
      'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKCU,
      'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

