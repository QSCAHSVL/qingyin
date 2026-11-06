; 卿音 安装包
; 只装框架本身：RVC / UVR 复用本机已有环境，torch 等大依赖由 app 内「环境配置」按需安装。
; 编译：scripts\build-installer.ps1（需要 Inno Setup 6）

#define AppName "卿音"
#define AppVersion "0.4.4"
#define AppExe "启动.bat"
; 源目录跟着版本号走，别再手改（0.4.1 时这里写死过一次，导致 0.4.2 差点打旧包）
#define AppSource "..\dist\卿音-" + AppVersion + "-portable"

[Setup]
AppId={{6C1F8A22-7B3D-4E59-9A41-2E7B5F0C3D18}
AppName={#AppName}
AppVersion=0.4.4
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
; 安装包 / 卸载器自己的图标（不写这两条，Setup.exe 和 unins000.exe 用的都是 Inno 默认图标，
; 开始菜单里「卸载 卿音」那个快捷方式就会显示不出来）
SetupIconFile={#AppSource}\assets\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico
; 核心本体不到 1MB；大依赖（torch / 模型）不进安装包，由程序内「环境配置」按机器情况装

[Languages]
; 简体中文语言包随仓库一起带（installer\Languages\），不依赖编译器装没装中文
; —— CI 上 choco 装的 Inno Setup 只有默认语言，用 "compiler:Languages\ChineseSimplified.isl" 会直接编译失败
Name: "chinesesimplified"; MessagesFile: "Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 快捷方式指向的是 .bat，.bat 自己不带图标；不显式给 IconFilename 的话 Windows 只能画个白板图标
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; IconIndex: 0; Comment: "打开卿音"
Name: "{group}\{#AppName} 环境自检"; Filename: "{app}\setup-deps.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; IconIndex: 0
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"; IconFilename: "{app}\assets\icon.ico"; IconIndex: 0
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; IconIndex: 0; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "现在打开卿音"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; 只删 [Files] 装进去的文件不够：跑过之后会多出 work / output / logs / models / plugins 里的运行时文件
; 和各种 __pycache__，装目录就会剩一堆残渣。0.4.3 实测：装进去 214 个文件，卸载后目录还在，
; 剩 logs、work、output、plugins\providers\__pycache__ 等。直接干掉整个 {app}
; （卸载器运行前会把自己复制到临时目录，删 {app} 不会把它自己弄没）。
Type: filesandordirs; Name: "{app}"
; filesandordirs 会把 {app} 里的东西清空，但根目录本身不一定会跟着消失（0.4.4 实测：内容没了，
; 目录还在）。那条 dirifempty 是兜底；如果资源管理器正开在这个目录里，连它也会失败——
; 这是 Windows 的句柄占用，不是安装包的问题。
Type: dirifempty; Name: "{app}"
