# lts_gui 详细设计（100% 对标 LightTools 9.1.0）

> 日期：2026-08-24  
> 程序：`C:\Program Files\Optical Research Associates\LightTools 9.1.0\lt.exe`  
> 资源：`lt_en_US.dll`（菜单 / 工具栏 IDB_*）、`ltmain.tlb`  
> 手册：Core Module User’s Guide 9.1（Dec 2020）Ch.1–4 + Appendix F  
> 截图：LightTools(64) 9.1.0 `[rearlighting]` 主界面  
> 对象图：`rearlighting.lts` → `output/structure.json`

---

## 0. 关键结论（先纠正路线）

LightTools **9.1 没有 Office Ribbon**。它是 **MFC/Stingray 经典主窗体**：

| 用户口中的“Ribbon” | LightTools 真实控件 |
|--------------------|---------------------|
| 顶部分页命令带 | **菜单栏 + 主工具栏** |
| 视口上方一排图标 | **3D Design view toolbar**（视图内工具条） |
| 视口右侧竖条图标 | **Command Palette 第一层**（三级命令面板） |
| 左侧树 | **System / Preferences / Window Navigator + Configuration** |
| 底栏 | **Prompt + Command Line + Output Window（多 Tab）** |

当前 `lts_gui.py` 是 cabdecoding 的 **STpre 四窗格**（Tree/List + Control | Draw + Message）。这与 LightTools **结构不同**，要对标必须改布局，而不是继续加 STpre 的 Control Window。

实现策略与 cabdecoding 相同：**全量菜单/工具栏骨架 + 分级启用**；未实现项走 `_nyi(name)` 写 Output。

---

## 1. 设计目标与边界

### 1.1 目标

把 `lts_gui` 升级为 **LightTools 9.1 主界面同构** 的 `.lts` 查看/轻量编辑器：

| 能力 | 对标 |
|------|------|
| 打开 / 保存 `.lts` | File → Open / Save / Save As，Ctrl+O/S |
| 模型浏览 | System Navigator：Components → 实体 → Primitive → Surface |
| 3D 设计视口 | 3D Design View：白底、着色/线框、1/4 pane、Fit/正交视图 |
| 选择联动 | 树 ↔ 视口拾取 ↔ Properties 对话框 |
| 坐标 / 命令 | Prompt Bar + Command Line + UCS 坐标 |
| 日志 | Output Window：Message / Simulation / Data Exchange / Macro / Optimization / Photoreal |
| 插入几何 | Insert 菜单 + Command Palette（已实现的走 OCC/SAT，其余 NYI） |

### 1.2 明确不做（菜单保留，标记 NYI）

完整光学仿真、优化、公差、Photoreal 渲染、CODE V 往返、SOLIDWORKS Link、集群光线追迹、宏解释器全量。  
触发后写入 Output：`[name] not available in ltsdecoding (LightTools-only / not yet mapped).`

---

## 2. 主窗体布局（截图 + Core UG Fig.4）

窗口标题：`LightTools(64) 9.1.0 [<stem>]`（未保存加 `*`）。默认 `1600×900`。

```
┌─ Menu: File Edit View Imaging Insert Ray Trace Analysis Optimization Tolerancing Photoreal Tools Window Help ─┐
├─ Main Toolbar（New/Open/Save | Undo/Redo/Delete | Select/Move | Fit/Zoom | 1Pane/4Pane | Begin Sim | …） ──┤
├──────────────────────┬──────────────────────────────────────────────────────────────────┬──────────────────┤
│ System Navigator     │  Tabs: [Console] [3D_<model>_2] …                                │ Command Palette  │
│  Components          │  ┌─ 3D Design view toolbar ─────────────────────────────────┐    │  Tier-1 竖条     │
│   Bulb1157Shell_45   │  │ Select Move Depth Properties Delete | Zoom Fit | Render  │    │  Tier-2          │
│    CubePrimitive_…   │  ├──────────────────────────────────────────────────────────┤    │  Tier-3 命令按钮 │
│     LeftSurface      │  │                                                          │    │                  │
│  Illumination Mgr    │  │              Layout Pane（白底 3D）                       │    │                  │
│  Source List         │  │              + RGB 变换 Gizmo（选中时）                    │    │                  │
│  Receiver List       │  │              点击处红字 X:[x y z] 当前点                   │    │                  │
├──────────────────────┤  │                                                          │    │                  │
│ Configuration        │  └──────────────────────────────────────────────────────────┘    │                  │
│  1: Configuration 1  │  Prompt: Indicate entity to select.          (mm) X: … Y: … Z: … │                  │
├──────────────────────┤  > Default=Select |  ________________________________            │                  │
│ Preferences Nav.     ├──────────────────────────────────────────────────────────────────┴──────────────────┤
│  General / Defaults  │ Output Window  [Message log] [Simulations] [Data exchange] [Macro] [Optimization] … │
│  View Preferences    │  22:42:24  Start of Session                                                          │
├──────────────────────┤                                                                                      │
│ Window Navigator     │                                                                                      │
│  Console             │                                                                                      │
│  3D_rearlighting_2   │                                                                                      │
└──────────────────────┴──────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 分割与停靠规则

- **左列**：垂直 `QSplitter` / 可折叠 `QDockWidget`（LightTools 支持 Auto-hide）  
  顺序固定：System Navigator → Configuration → Preferences Navigator → Window Navigator  
  默认宽 ~240–280 px。
- **中央**：`QTabWidget`（Tabbed Views，默认；`Window → Floating Views` 可拆出独立窗口）。
- **3D 页内部**：水平 splitter = Layout Pane | Command Palette（默认 Palette 宽 ~72–96 px，展开第三层时 ~160 px）。
- **3D 页底部**：Prompt（单行）+ Command Line（单行输入）。
- **主窗底部**：Output Window，默认高 ~120–160 px。
- **禁止**再使用 STpre 的「Tree/List + Control | Draw + Message」四窗格作为主骨架。

### 2.2 视觉规格（对齐截图）

| 项 | LightTools 9.1 | 实现 |
|----|----------------|------|
| 总底 | 浅灰 `#e8e8e8` / `#d4d0c8` 系统灰 | QSS |
| 3D 背景 | **白** `#ffffff`（非渐变灰） | `vtkRenderer.SetBackground(1,1,1)` |
| Navigator 标题条 | 灰底 + 图钉 / 关闭 | `PaneFrame` 加 pin |
| 选中树节点 | 蓝高亮 | 标准 `QTreeWidget` |
| 活动 3D Tab | 浅蓝底 | QSS `#c5d8f0` |
| 图标 | 16×16 / 24×24 专业线稿 | `lts_icons` 扩展；优先从 `lt_en_US.dll` 抽 IDB_* |
| 3D 引擎 | HOOPS/HPS + OpenGL | 我们用 VTK；交互要对齐，不换内核 |

---

## 3. 菜单栏（13 项，与截图 / `lt_en_US.dll` 一致）

图例：✅ 已有　◐ 部分　⬜ NYI（记日志，菜单保留）

快捷键：Alt 后显示下划线（`&File` → Alt+F）。

### 3.1 File(&F)

| 项 | 快捷键 | 状态 | 行为 |
|----|--------|------|------|
| New Model | Ctrl+N | ◐ | 空模型 + 新 3D Design |
| Open… | Ctrl+O | ✅ | `*.lts` |
| Recent Models | | ◐ | `QSettings` 最近 8 个 |
| Close Model | | ◐ | 关当前模型 |
| Close View | | ◐ | 关当前 Tab |
| Save | Ctrl+S | ✅ | 外科式回写 |
| Save As… | | ✅ | |
| Save With Ray Data… | | ⬜ | Illumination 模块 |
| Save Library… | | ⬜ | |
| Load Library Element… | | ⬜ | |
| Load Library Element with Options… | | ⬜ | |
| Import ▸ CODE V / IGES / STEP / Plain SAT / Parasolid / STL / DXF / CATIA V4/V5 | | ◐ | SAT/STEP 可接 OCC |
| Export ▸ LightTools / CODE V / STEP / SAT / Parasolid / STL | | ◐ | |
| Print… / Print Setup… | | ⬜ | 3D 截图打印可后补 |
| Run… | | ⬜ | 第三方程序 |
| Restore Environment / Save Environment | | ⬜ | |
| Exit | | ✅ | |

### 3.2 Edit(&E)

| 项 | 快捷键 | 状态 |
|----|--------|------|
| Undo / Redo | Ctrl+Z / Ctrl+Y | ⬜ 快照栈可后补 |
| Cut / Copy / Paste | | ⬜ |
| Copy Geometry / Copy to Clipboard | | ⬜ |
| Delete / Undelete | Del | ◐ Delete 已标删除 |
| Select All / Invert Selection | | ⬜ |
| Properties… | | ◐ Control Property → 改为独立 Properties 对话框 |
| Edit All Selected / Edit All Descendants | | ⬜ |
| Hide / Show / Show All / Show All Descendants / Swap Hidden/Visible | | ◐ 树勾选可映射 Hide |
| Preferences… | | ⬜ 打开 Preferences 对话框 |
| Immersion Manager… | | ⬜ |
| User Materials… / User Coatings… | | ⬜ |
| Optical Properties… | | ⬜ |

### 3.3 View(&V)

| 项 | 状态 | 映射 |
|----|------|------|
| 2D Design / 3D Design / Imaging Path | ◐ | 仅 3D 实现；2D/Imaging Path NYI |
| Table View | ⬜ | |
| Pane Layout ▸ 1 Pane / 4 Pane | ⬜ | VTK 四分屏可后补 |
| Fit / Fit All / Fit All Same | ✅ Fit | FitSelObject / FitSelSurf NYI |
| Fit View to Selected Object / Surface | ⬜ | |
| Zoom In / Out / Window | ⬜ | 滚轮已有 |
| Front / Side / Top / Back / Bottom / Other Side / Isometric | ◐ | 现有 XY/XZ/YZ |
| View UCS / Normal To | ⬜ | |
| Set Current Point | ⬜ | |
| Render Mode ▸ Wireframe / Solid / Translucent | ◐ | Line/Shading/Translucent |
| Automatic Rendering | ⬜ | |
| Show Through Objects | ⬜ | |
| View Preferences… | ⬜ | Visibility / Colors / Axes / UCS |
| UCS Preferences… | ⬜ | |
| Configuration Control Panel | ◐ | 左列 Configuration |
| System / Preferences / Window Navigator | ✅ 显示开关 | |
| Output | ✅ | |

### 3.4 Imaging(&I)

Imaging Path 模块。全部 ⬜：Imaging Paths、Field Specification、Ray Aberration Plot、Spot Diagram、Pupil Specification、EPD / OSNA / Vignetting。

### 3.5 Insert(&I)  （对应 Command Palette）

完整三级与 Palette 同步，见 §5。菜单选中后 **高亮对应 Palette 按钮**（Core UG p.47）。

### 3.6 Ray Trace(&R)

| 项 | 状态 |
|----|------|
| Aim NS Ray / Fan / Grid / Point Grid / Virtual Grid | ⬜ |
| Begin Forward Simulation / Backward / All | ⬜ |
| Continue Simulation | ⬜ |
| Quick Ray Preview | ⬜ |
| Ray Display options | ⬜ |
| Reset All Random Seeds | ⬜ |
| Precision / Accelerated Ray Trace | ⬜ |

### 3.7 Analysis(&A)

Illuminance / Intensity / Spatial Luminance / Angular Luminance 网格与图表、LumViewer、Encircled Energy、CIE / CCT / Color Difference、Region Analysis。全部 ⬜。

### 3.8 Optimization(&O)

Optimize!、Variables/Constraints/Merit Function、Results、Clear Results、Backlight Pattern Optimization。全部 ⬜。

### 3.9 Tolerancing(&T)

Tolerancing Manager、Sensitivities、Add/Remove Tolerance。全部 ⬜。

### 3.10 Photoreal(&P)

New Photoreal View、Camera、Point/Spot/Distant Light、Start Lit Simulation、Render After Lit。全部 ⬜。

### 3.11 Tools(&T)

| 项 | 状态 |
|----|------|
| Options…（Graphics / Folders） | ⬜ |
| Run Macro… | ⬜ |
| AddIns… | ⬜ |
| Glass Catalogs… | ⬜ |
| Display Film / Example Model / LED / Source / Utility Library | ⬜ |
| SOLIDWORKS Link | ⬜ |
| Parameter Analyzer | ⬜ |

### 3.12 Window(&W)

Tabbed Views ✅ / Floating Views ⬜、Cascade / Tile、Save / Restore / Clear View Layout、Windows…。

### 3.13 Help(&H)

Contents and Index、What's This?、Document Library、Release Notes、各 UG/Tutorial、Synopsys OSG Web、About LightTools ◐。

---

## 4. 工具栏

### 4.1 主工具栏（菜单下，整窗）

对应 `IDB_*QUICK*`：

`New | Open | Save | Undo Redo | Select | Move | Depth | Properties | Delete | ZoomIn ZoomOut ZoomWindow Fit FitSelSurf FitSelObj | 1Pane 4Pane | Aim NS Ray | Begin All Sim | Continue Sim | Begin Lit Sim`

实现：第一期做 New/Open/Save/Select/Delete/Fit/正交视图；其余 NYI 图标保留。

### 4.2 3D Design view toolbar（视口**内部**顶）

Core UG Fig.6 + 截图：

| 组 | 按钮 |
|----|------|
| 选择/编辑 | Select, Move, Set Depth, Properties, Delete |
| 显示 | Wireframe / Shaded / Hidden-line / Translucent |
| 视图 | Zoom、Fit、1/4 Pane |
| UCS | Place UCS、Align UCS |
| 光线 | Aim NS Ray、Ray Display（Fwd sim） |
| 仿真 | Begin all simulations、Continue |

### 4.3 视口右侧竖条 = Command Palette Tier-1

资源按钮（第一层类别，见 §5）。截图中的 Top/Front/Side/Iso **同时**出现在 View 菜单、view-toolbar 下拉、以及 Palette「Viewing」类。

---

## 5. Command Palette（三级，Insert 的图形化入口）

Core UG p.46–47：三层按钮；第三层带点数（4 点透镜）或 `n`（需命令行输入）。

从 `lt_en_US.dll` 的 `IDB_ORA*` 归纳第一层：

| Tier-1 | 含义 | 主要 Tier-2 / 命令（资源名） |
|--------|------|------------------------------|
| **Select / Edit** | 选择、移动、旋转、缩放、对齐、布尔 | Select, Move, Rotate, Scale, Align, Union, Subtract, Intersect, Unboolean, Group, Trim, Break, Cement |
| **Optical Element** | 透镜/反射镜/棱镜 | Place Singlet（Sketch3/4/5/6Pt）、Quick Lens、Library Element、Fold Mirror、Prism（Right/Porro/Penta/Dove）、Beamsplitter、LED Lens |
| **3D Objects** | 光学实体 | Block, Block3Pt, Sphere, Cylinder, Toroid, Ellipsoid, Elliptical Fiber, Revolved/Extruded/Swept Sheet&Solid, Skin, Freeform, CPC, CAD File |
| **Mechanical** | 机械体 | Mech Block/Cylinder/Sphere/Toroid/Revolution |
| **Sources** | 光源 | Point, Cylinder/Sphere/Block/Disk/Rect Surface&Volume, Ray Data, Object Source, Virtual |
| **Receivers** | 接收器 | Surface, Primitive, Solid, Far Field, Finite Far Field, Spatial/Angular Lum Meter |
| **NS Rays** | 非序列光线 | Aim NSS, Fan, Grid, Point Grid, Virtual Grid, Ray Path, Footprint |
| **Reference Geometry** | 参考 | Point, CS, Plane, Dummy Plane/Sphere, Polyline, Text |
| **Textures / Patterns** | 纹理 | Rect/Hex/Sphere/Prism/Pyramid/Cone/Cylinder texture, 2D patterns |
| **Photoreal** | 相机/灯 | Camera, Point/Spot/Distant Light |
| **Viewing** | 视图 | Front/Side/Top/Back/Bottom/Iso, Reset Viewpoint, Zoom, Pan, UCS axes |
| **Metrics** | 测量 | Linear, Angular |

**已可接线（第一期实现）：** 3D Objects 中 Block/Sphere/Cylinder/Toroid（`lts_geom` 已有参数体 + OCC 布尔）、Select、Fit、Render Mode。其余 Palette 按钮全部画出并 `_nyi`。

---

## 6. 3D 显示设计（对标 3D Design View）

### 6.1 视口行为（Core UG Ch.1 鼠标）

| 操作 | LightTools | VTK 映射 |
|------|------------|----------|
| 左键 | 选择 / 指定点 | CellPicker → 选实体 |
| 右键单击 | 快捷菜单 | 自定义 context menu |
| 右键拖 / 中键拖 | 绕全局原点旋转 | Trackball（改为绕世界原点） |
| Shift+右键 或 Ctrl+中键 | 平移 | Pan |
| Ctrl+右键 | 相对视图中心缩放 | Dolly |
| Shift+中键 | 相对光标缩放 | |
| Alt+中键 | Roll | |
| 滚轮 | 缩放（可反向，View Preferences） | MouseWheel |
| 3Dconnexion | 六自由度 | 可选，后期 |

默认 **透视** 由 View Preferences 控制；手册 3D 默认 YZ 平面（Side）。截图为透视着色。  
**对标：默认透视 + 白底 + Gouraud 着色**；正交作为 View UCS / 平面视图选项。

### 6.2 显示模式

- Wireframe / Solid（Shaded）/ Hidden line / Translucent（`&Wireframe` `&Solid` `&Translucent`）
- Show Through Objects
- 隐藏实体：树图标变灰；选中时可画线框（General Preferences → Draw Wireframe for Selected Hidden Entities）
- Disable：图标红斜线 + 名称加括号
- Not ray-traceable：红禁止圈（Appendix F overlay）

### 6.3 当前点与 Gizmo

- 点击布局：红 **X** + `X: [x y z]`（截图红字坐标）
- 选中实体：RGB 平移/旋转 Gizmo（截图粉球上的变换轴）
- Prompt 右侧：`(Millimeters) X: … Y: … Z: …`（UCS，鼠标跟踪）

### 6.4 1 Pane / 4 Pane

4 Pane：Iso + Right(YZ) + Front(XY) + Top(XZ)，活动 pane 高亮边框。VTK 用 4 个 viewport 或 4 renderer。

### 6.5 几何来源（已有管线，不改内核）

`lts_parser` → `lts_geom`（SAT + CSG + OCC 布尔）→ `lts_vtk`。  
3D 只负责 actor / 拾取 / 相机；**不要**把几何重建塞回 GUI。

---

## 7. 导航面板

### 7.1 System Navigator（主树）

数据来自 `.lts` 对象图，**不要**再用「Solids/Sources/Materials/Others」扁平分组作为主视图。

对标 `rearlighting.lts` 根边 + IllumManager：

```
<model>
├─ Components          ← ORAPartDBObj / getGeometryManager
│   ├─ Bulb1157Shell_45     (entity: ORASphereObj / ORACylinderObj / ORAGenericSolidObj …)
│   │   └─ <Primitive>      (ORACSG*Primitive)
│   │       ├─ FrontSurface / LeftSurface / …   (ORASurfaceInfoObj)
│   │       │   └─ BareSurface / zone           (ORAPropertyZoneObj)
│   │       └─ …
│   ├─ Cube_94
│   └─ Generic_354
├─ Materials           ← ORAUserMaterialManagerObj
├─ Spectral Regions    ← ORASpectralRegionManagerObj
├─ NS Rays             ← ORANSRayManagerObj
├─ Illumination Manager
│   ├─ Source List     ← ORASourceDBObj
│   ├─ Receiver List   ← ORAReceiverDBObj
│   └─ Forward Simulation
├─ Optimization Manager
└─ (Photoreal Studio Manager — 若模型有)
```

交互（手册 + 截图）：

- 单击：选中并在 3D 高亮  
- 双击：打开 **Properties 对话框**（多 Tab，可停靠）  
- 右键：Properties / Hide / Show / Show All Descendants / Fit View to Selected / Delete / Rename / Disable / Enable / Sort Alphabetically  
- 拖放：调整同级顺序  
- 展开 >500 项：分批加载（手册：500 → 1000 → 2000）  
- 图标：Appendix F 全套（实体/图元/表面/光源/接收器/组/仿真…）+ overlay

### 7.2 Configuration Control Panel

`Current Configuration` 列表（如 `1: Configuration 1`）。无配置的模型显示一项 Default。切换 NYI，面板要在。

### 7.3 Preferences Navigator

```
General Preferences
  System / Ray Trace / Colors / …
Defaults
  Spectral Region / Optical Contact / Materials / …
View Preferences
  3D_<model>_n     → Visibility, View Options, UCS, Axes
```

双击打开对应 Preferences 对话框（第一期只做只读/空壳 + NYI）。

### 7.4 Window Navigator

列出打开的视图：`Console`、`3D_rearlighting_2`、图表、停靠的 Properties。单击激活 Tab。

---

## 8. Prompt、命令行、Output

### 8.1 Prompt Bar

布局 pane 正下方一行：当前命令提示。默认 `Indicate entity to select.`  
选择工具时随命令变化（Move → `Indicate position to move entity to.` 等，字符串已在 `lt_en_US.dll`）。

### 8.2 Command Line

`> Default=Select |` + 输入框。  
解析子集（第一期）：`Fit`、`XYZ x,y,z`、对象名选择、已实现的 Insert 命令。  
未知命令写入 Output WARN。  
Ctrl+Backspace：回退一个输入（Command Line Backup）。

### 8.3 Output Window（底栏，多 Tab）

| Tab | 内容 |
|-----|------|
| Message log | 会话、文件、选择、NYI |
| Simulations | 光线报告（NYI） |
| Data exchange | 导入/导出 |
| Macro | 宏输出 |
| Optimization | 优化 |
| Photoreal | 渲染 |

右键：Save text As / Clear All Text。时间戳格式 `HH:MM:SS`。

---

## 9. Properties 对话框（取代当前 Control.Property 表）

LightTools：双击实体 → 停靠/浮动对话框，按类型分 Tab。

| 对象 | 典型 Tab |
|------|----------|
| Solid / Entity | Coordinates, Material, Ray Trace, Color/Layer, CSG |
| Primitive | Geometry (R/L/W/H…), Position/Orientation |
| Surface | Surface number/name, Optical Properties, Zones |
| Source | Emittance, Aim, Spectrum |
| Receiver | Mesh, Filters, Analysis |

第一期：Coordinates + 现有属性表只读/可改 `setName`/`setMaterialName`/`setPosition`，Apply 写回 `LTSModel`。

---

## 10. Console 与其它视图

启动时 **Console** 为默认 Tab 之一（手册：3D 在其后）。Console 有自己的命令行（New3DDesign、Exit…）。  
2D Design / Imaging Path / Table / Chart：菜单入口保留，打开时 NYI 页。

---

## 11. 与现状差距

| LightTools | 当前 lts_gui | 动作 |
|------------|--------------|------|
| 13 项菜单 | File/Edit/View/Help | 补全骨架 |
| 左四 Navigator + Configuration | 一个 Tree/List（Layout/SAT/Objects） | 重做 System Navigator 层级 |
| 无 STpre Control | Show/Select + Property + SAT + Stats | Property→对话框；Show/Select→View Preferences / 视口工具条 |
| 3D 在 Tab 内 + Palette + Prompt + Cmd | Draw Window 占满右上 | 拆 3D Design 页结构 |
| Output 多 Tab | 单 Message | 多 Tab |
| 白底 3D + Gizmo + 当前点 | 灰渐变 + 无 Gizmo | 改渲染与交互 |
| Command Palette | 无 | 新建 `lts_palette.py` |

---

## 12. 模块拆分

| 文件 | 职责 |
|------|------|
| `lts_gui.py` | `LTMainWindow`：菜单总线、停靠、Tab、文件 I/O |
| `lts_panes.py` | SystemNavigator, ConfigPanel, PrefNavigator, WindowNavigator, OutputWindow, PromptBar, CommandLine, PaneFrame |
| `lts_palette.py` | 三级 Command Palette |
| `lts_view3d.py` | 3D Design 页：VTK、工具条、1/4 pane、Gizmo、当前点 |
| `lts_icons.py` | 扩展图标；可选从 `lt_en_US.dll` 抽 IDB |
| `lts_dialogs.py` | Properties / Preferences / About |
| `lts_commands.py` | 命令名 → slot / NYI（与 Command Reference 对齐） |
| `lts_model.py` / `lts_geom.py` / `lts_vtk.py` | **不改职责**，仅给 Navigator 提供层级 API |

---

## 13. 分阶段实施

| 阶段 | 内容 | 验收 |
|------|------|------|
| **P0 骨架** | 停靠布局、13 菜单骨架、Output 6 Tab、Prompt+Cmd 外观、白底 3D Tab、Window Navigator | 打开即像截图，不要求功能 |
| **P1 Navigator** | Components→Primitive→Surface 真树、选择联动、Hide、双击 Properties | `rearlighting.lts` 树与 LT 一致 |
| **P2 3D 交互** | 鼠标映射、Gizmo、当前点红字、Fit/正交/着色模式、视口工具条 | 截图级操作手感 |
| **P3 Palette** | Tier-1/2/3 全按钮；Block/Sphere/Cylinder/Toroid 可插入 | Insert 与 Palette 高亮同步 |
| **P4 命令行** | Fit / XYZ / Select 子集 | 与 Prompt 联动 |
| **P5 4-pane / Console** | 四分屏、Console Tab | View → Pane Layout |
| **P6** | Preferences 空壳、Recent Files、Undo 快照 | |

每阶段保持：`enable_3d=False` 可测；未实现入口只打 NYI，不删菜单。

---

## 14. 资源对照（逆向产物）

| 源 | 用途 |
|----|------|
| `lt.exe` + `lt_en_US.dll` | 菜单 `&…`、提示语、387 个 `IDB_*` 按钮 |
| Core UG Ch.3 Fig.4–7 | 布局、工具条、命令行、Palette |
| Core UG Appendix F | System Navigator 图标与 overlay |
| `structure.json` 根边 | Navigator 顶层节点与类名映射 |
| 用户截图 | 停靠顺序、白底 3D、Gizmo、Prompt 文案、Output 位置 |

命令全集见 `output/docs_txt/CommandReferenceGuide.txt`（约 1500+ 命令）；`lts_commands.py` 按名注册，默认 NYI。

---

## 15. 验收标准（“100% 对标”的含义）

界面 **信息架构与命名 100%** 对齐 LightTools 9.1；内核仿真不对齐。

打开 `rearlighting.lts` 后，对照官方截图应看到：

1. 标题 `LightTools(64) 9.1.0 [rearlighting]`  
2. 13 个主菜单名称一致  
3. 左侧 System Navigator 以 **Components** 为根，可展开到 Surface  
4. Configuration / Preferences / Window Navigator 四块都在  
5. 中央 Tab：Console + 3D_*  
6. 3D 白底、顶工具条、右 Palette、底 Prompt `Indicate entity to select.` + 命令行  
7. 底栏 Output（Message log 有时间戳）  
8. 状态区毫米坐标  

功能深度按 §13 分期；**视觉与导航在 P0–P1 必须过关**。
