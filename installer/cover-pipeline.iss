; 卿音 安装包
; 只装框架本身：RVC / UVR 复用本机已有环境，torch 等大依赖由 app 内「环境配置」按需安装。
; 编译：scripts\build-installer.ps1（需要 Inno Setup 6）

#define AppName "卿音"
#define AppVersion "0.4.3"
#define AppExe "启动.bat"
; 源目录跟着版本号走，别再手改（0.4.1 时这里写死过一次，导致 0.4.2 差点打旧包）
#define AppSource "..\dist\卿音-" + AppVersion + "-portable"

[Setup]
AppId={{6C1F8A22-7B3D-4E59-9A41-2E7B5F0C3D18}
AppName={#AppName}
AppVersion=0.4.3
AppPublisher=卿音项目
AppPublisherURL=https://github.com/
DefaultDirName={autopf}\QingYin
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=卿音-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
UninstallDisplayName={#AppName}
; 核心本体不到 1MB；大依赖（torch / 模型）不进安装包，由程序内「环境配置」按机器情况装

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "打开卿音"
Name: "{group}\{#AppName} 环境自检"; Filename: "{app}\setup-deps.bat"; WorkingDir: "{app}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "现在打开卿音"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\src\**\__pycache__"
