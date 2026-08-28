# LightTools 9.1 UI 100% 对标规划

> 目标：按 **LightTools 9.1.0**（lt.exe 位于 `C:\Program Files\Optical Research Associates\LightTools 9.1.0\lt.exe`）
> 的界面面貌（菜单、工具栏、命令调色板、3D/2D/成像视图、导航/配置/输出面板、命令行与消息栏）
> 建立完整 UI 对照清单，并逐项落在 `lts_gui.py` 生态（PyQt5 + VTK + matplotlib）。
> 制定日期：2026-08-25。依据来源：lt_en_US.dll 资源字符串（偏移标注）、CoreUG.pdf 第 3/4/5 章、
> CommandReferenceGuide（命令→调色板路径）、lighttools.chm、现有 `lts_gui.py` 实现。

## 0. 对标数据来源（已逆向核实的锚点）

| 来源 | 内容 | 用途 |
|---|---|---|
| `Doc/CoreUG.pdf` 第 3 章 | 主窗口布局图（Menu bar/Toolbar/Layout pane/Command palette/Cursor Location/Command Line/Navigators/Output）；工具栏图（Figure 6）；Insert 菜单↔命令调色板关系；三大导航窗+输出窗说明 | 主窗口框架标准 |
| `Doc/CoreUG.pdf` 第 4 章 | 3D/2D/Imaging Path 三视图能力对比表；表视图/专用视图 | 视图对标 |
| `Doc/CoreUG.pdf` 第 5 章 | 命令调色板第一层分类；Elements→3D Objects 的 14 个按钮（Block 3Pt/Center Sphere/Ellipsoid/Cylinder/Toroid/Elliptical Fiber/Revolved/Extruded/Swept/Skinned/Freeform/CPC×3）；Place Reflectors 类 | 调色板对标 |
| `lt_en_US.dll` 字符串簇 | 顶层菜单（`&File`@114934、`&Edit`/`&Help`@793780/793792、`&Optimization`@888380、`&Tools`/`&Imaging`@908288/908302、`&Window`@932738）；文件/编辑菜单项（New/&Open…/Ctrl+O/&License…/E&xit；&Undo/Ctrl+Z/&Redo/&Redo/Select &All/In&vert Selection/&Undelete/User &Materials…/User Coating&s…）；视图项（&2D Design/&3D Design/Ima&ging Path/&Components/&NS Rays/&Imaging Paths/&Spectral Regions/&This View/&Everything；&Wireframe/&Solid/&Translucent/&Fit…/Set &Current Point/Rese&t All Random Seeds）；插入项（&Block…/&Sphere…/Cy&linder…/&Toroid…/&Revolved…/&CPC/&Swept…/&Freeform…/&Quick Lens…/&Lens/&Reflector/&Camera/&Point Light/&Spot Light/&Distant Light…）；模拟项（&Ray Trace/&Begin all/&Continue all Backward/&Hybrid Simulations）；优化（&Optimize!/&Input…/&Results…/&Backlight Pattern Optimization）；工具（&Run Macro…/&Addins…/&Utility Library…/&Options…/&Parameter Analyzer/&Glass Catalogs/LE&D Library/&Source Library/Example Model Library）；分析（I&llumination/Lum&Viewer/&Add Intensity Mesh/&Add Spatial Luminance Mesh/&Automotive Test Point Analyzer）；窗口（&Cascade/&Tabbed Document/&Close View）；导航面板名（System Navigator@730182/Preferences Navigator@730216/Window Navigator@730260/Output@730294/&Configuration Control Panel@704404） | 菜单/面板名唯一性校验 |
| `CommandReferenceGuide.txt` | 36 条“Click the button … on the command palette”路径 → 调色板层级（Elements/Mechanical/Modifying/Ray Tracing/Viewing…） | 调色板增量 |
| `lighttools.chm`（5060 页 HTML） | 命令/面板/首选项细节页 | 后续逐项深挖 |

## 1. 主窗口布局模型（以 CoreUG 图为准）

```
┌────────────────────────────────────────────────────────────────────────┐
│  Menu Bar        (File Edit View Insert Imaging RayTrace Analysis …)   │
├──────────────────────────────────────┬─────────────────────────────────┤
│  Toolbar (Save/Delete/Set depth/UCS/ │                                 │
│          Begin all/Continue all/     │    Command Palette（右侧）      │
│          Aim NS Ray/Ray Display)     │    (第一层分类→飞行菜单)        │
├───────────┬──────────────────────────┴─────────────────────────────────┤
│ System    │                                                            │
│ Navigator │            Layout pane（3D/2D/Imaging Path 设计视图）      │
├───────────┤                                    Cursor Location 坐标   │
│ Pref.     │                                                            │
│ Navigator │                                                            │
├───────────┤                                                            │
│ Window    │                                                            │
│ Navigator ├────────────────────────────────────────────────────────────┤
│           │  Command Line（上方 Prompt 提示行 + 命令输入框）            │
├───────────┴────────────────────────────────────────────────────────────┤
│  Output Window（Message log/Simulations/Data exchange/Macro/           │
│                  Optimization/Photoreal 六标签）                       │
└────────────────────────────────────────────────────────────────────────┘
```

四个可停靠窗（Sys/Preference/Window Navigator、Configuration Control Panel）、
Output 窗可浮动/自动隐藏/关闭；三种设计视图（3D/2D/Imaging Path）菜单与调色板随视图裁剪。

## 2. 菜单栏对标清单

状态图例：✅ 已有（菜单项+handler）｜🟡 部分（菜单项在，命令 NYI）｜⬜ 规划（未建成入口）

### 2.1 File

| 菜单项 | LT 命令名（CRG） | 状态 | 备注/规划 |
|---|---|---|---|
| New Model | NewModel | ✅ | 已有；待补 `新建视图` 动作 |
| Open… | Open | ✅ | 支持 .lts |
| Recent Models | — | ✅ | 已实现 |
| Close Model / Close View | Close/CloseView | ✅ | 视图级关闭待接 |
| Save / Save As… | Save/SaveAs | ✅ | 字节保真写回 |
| Save With Ray Data… | SaveWithRayData | 🟡 | 已写 .ray；`ORAIntensityDataMeshObj` 回写 LTS 待做 |
| Save Library… / Load Library Element…/with Options | SaveLibrary/LoadElement | 🟡 | 库元素(.ent)导出/导入规划 |
| Import: CODE V/IGES/STEP/Plain SAT/Parasolid/STL/DXF/CATIA V4/V5 | ImportCodeV/IGES/STEP/PlainSAT(X_T/STL/DXF/Catia4/5) | 🟡 | SAT/STL/STEP/IGES 已通（OCC）；DXF/CATIA/CODE V 规划 |
| Export: LightTools/CODE V/STEP/SAT/Parasolid/STL | Export… | 🟡 | STL/STEP/SAT 已通；LTS 原样导出已通；CODE V 规划 |
| Print…/Print Setup… | Print/PrinterSetup | 🟡 | 截图导出已有（PNG）；打印设置规划 |
| Run… | RunExt | 🟡 | 外部程序调用规划 |
| Restore Environment / Save Environment | RestoreEnv/SaveEnv | ⬜ | 会话环境（偏好+布局+最近文件）序列化规划 |
| Exit | Exit | ✅ | |

### 2.2 Edit

| 菜单项 | LT 命令 | 状态 | 备注 |
|---|---|---|---|
| Undo/Redo | Undo/Redo | 🟡 | 命令路由已接；`lts/undo.py` 编辑事务栈规划 |
| Cut/Copy/Paste | Cut/Copy/Paste | 🟡 | 模型内部剪贴已通；跨元素/库剪贴规划 |
| Copy Geometry | CopyGeometry | ✅ | |
| Copy to Clipboard | CopyClipboard | 🟡 | 位图/文本导出规划 |
| Delete/Undelete | Delete/Undelete | 🟡 | 删除已实现（写回）；Undelete 依赖 undo 栈 |
| Select All/Invert Selection | SelectAll/InvertSelection | ✅ | |
| Properties… | Properties | ✅ | 属性对话框（表驱动） |
| Edit All Selected/Descendants | EditAllSel/EditAllDesc | ⬜ | 批量属性编辑规划 |
| Hide/Show/Show All/Show All Descendants/Swap Hidden | Hide/Show/ShowAll/ShowAllDesc/SwapHidden | ✅ | |
| Preferences… | Preferences | ✅ | 已接（通用/默认分类） |
| Immersion Manager… | ImmersionManager | ⬜ | 介质/浸没管理规划（rayspace 已备） |
| User Materials…/User Coatings…/Optical Properties… | UserMaterials/UserCoatings/OpticalProperties | ✅ | 材料/区链已接；涂层库规划 |

### 2.3 View

| 菜单项 | LT 命令 | 状态 | 备注 |
|---|---|---|---|
| 2D Design / 3D Design / Imaging Path | View2D/View3D/ViewImaging | 🟡 | 3D 已实现；2D 投影视图 + 成像路径（顺序追迹）规划 |
| Table View | TableView | ✅ | 显示体表；对象属性表规划 |
| Pane Layout 1/4 | Pane1/Pane4 | ✅ | 多窗格渲染规划 |
| Fit / Fit All / Fit All Same | Fit/FitAll/FitAllSame | 🟡 | |
| Fit View to Selected Object/Surface | FitSelObj/FitSelSurf | 🟡 | 对象已接；曲面规划 |
| Zoom In/Out/Window | ZoomIn/ZoomOut/ZoomWindow | ✅ | |
| Front/Side/Top/Back/Bottom/Other Side/Isometric | Front/Side/Top/… | ✅ | |
| View UCS / Normal To / Set Current Point | ViewUCS/NormalTo/SetCurrentPoint | 🟡 | 当前点已接 |
| Render Mode: Wireframe/Solid/Translucent/Hidden Line | Wireframe/Solid/Translucent/HiddenLine | ✅ | |
| Automatic Rendering / Show Through Objects | AutoRender/ShowThrough | 🟡 | 着色策略规划 |
| View Preferences… / UCS Preferences… | ViewPrefs/UCSPrefs | 🟡 | 视图偏好已接框架 |
| Show: Components/NS Rays/Imaging Paths/Spectral Regions/This View/Everything | ShowComponents/ShowNSRays/… | 🟡 | 图层过滤：显示/隐藏已有，按类别显示规划 |
| System Navigator/Preferences Navigator/Window Navigator/Configuration Control/Output | — | ✅ | 可停靠面板开关 |

### 2.4 Insert（与命令调色板 Elements/Mechanical 联动）

| 菜单项 | LT 命令 | 状态 | 备注 |
|---|---|---|---|
| Optical Element: Block 3Pt/Center Sphere/Ellipsoid/Cylinder/Toroid/Elliptical Fiber/CPC/Quick Lens/Lens/Reflector | Block3Pt/CtrSphere/Ellipsoid/Cylinder/Toroid/EFiber/CPC/QuickLens/Lens/Reflector | 🟡 | Block/Sphere/Cylinder/Toroid 已实现；EFiber/CPC/QuickLens 规划（参数化创建+SAT 写出已有 `lts_create`） |
| Optical Element: Revolved/Extruded/Swept/Skinned/Freeform Solids | Revolve/Extrude/Sweep/Skin/Freeform | ⬜ | 草图→拉伸/旋转/扫掠（P2 规划 `lts/geometry/sketch.py`） |
| Mechanical Element: Block/Cyl/Sphere/Toroid | MechBlock/… | 🟡 | 复用图元创建+吸收材质 |
| Source: Point/Cylinder Surface/Sphere Surface/Block Surface/Ray Data | PlacePointLight/CylSource/SphereSource/BlockSource/RayData | 🟡 | 点源插入已通；面光源向导 + apodizer 采样已通（自动绑定）；RayData 源规划 |
| Receiver: Surface/Primitive/Solid/Far Field | SurfaceReceiver/…/FarFieldReceiver | 🟡 | 远场/平面接收器绑定已通；创建向导规划 |
| Dummy Surface/Reference Geometry/Text Annotation | DummySurface/RefCS/TextAnnot | 🟡 | 哑面=方块已通；参考系/文本规划 |
| 2D Patterns/3D Textures/Place Zones（palette 对应） | AddCirclePattern…/AddSphereTexture…/PlaceZones… | ⬜ | 纹理区已能**绑定**；创建类命令 P-后续（区链物理已就绪） |

### 2.5 Imaging（可选模块）

Imaging Paths/Field Specification…/Ray Aberration Plot…/Spot Diagram…/Pupil Specification/Set EPD/Set NAO/Set Vignetting → 规划：顺序追迹路径视图（先照亮成像路径 API + 光线追迹，再用 matplotlib 出 Spot/RayAberration 图）。当前为占位。

### 2.6 Ray Trace（Simulation）

| 菜单项 | LT 命令 | 状态 | 备注 |
|---|---|---|---|
| Aim NS Ray | NSRayAim | ✅ | 当前点→瞄准+红折线 |
| Aim Fan/Aim Grid/Aim Point Grid/Aim Virtual Grid | NSFan/NSGrid/AimGrid… | 🟡 | 扇形/网格瞄准（复用 emitter 采样）；虚拟网格规划 |
| Begin Forward/Backward/All Simulations | BeginForwardSimulation/BeginBackwardSimulation/BeginAllSimulations | ✅ | 正向已全通（面发射+分区物理+接收器网格）；反向/混合规划 |
| Continue Simulation | ContinueSimulation | ✅ | 追加种子 |
| Quick Ray Preview | QuickRayPreview | ✅ | |
| Ray Display | RayDisplay | ✅ | 路径折线+发射/显示过滤（路径/波长）规划 |
| Reset All Random Seeds | ResetAllRandomSeeds | ✅ | |
| Precision/Accelerated Ray Trace | SetupRTMode | 🟡 | 精度开关（占位） |

### 2.7 Analysis

Illuminance/Intensity（✅ 接收器网格图表）、Spatial Luminance/Angular Luminance/LumViewer（⬜ 亮度网格→`CandelaDataMesh` 复用）、Encircled Energy（⬜ 成像分析）、CIE/CCT/Color Difference Chart（⬜ 色度学 `ltsoptics/spectrum.py` 已备）、Region Analysis（🟡），Add Intensity/Add Spatial Luminance Mesh（⬜ 网格写出→写回 LTS）、Automotive Test Point Analyzer（⬜ 工具库）。

### 2.8 Optimization / Tolerancing / Photoreal / Tools / Window / Help

- Optimization：Optimize!/Variables…/Constraints…/Merit Function…/Results…/Clear Results/Backlight Pattern Optimization → 占位（优化引擎 P7 规划：变量/评价函数/阻尼最小二乘+单纯形+遗传）。
- Tolerancing：Manager…/Sensitivities…/User Defined Tolerance Group… → 占位（公差/灵敏度与优化同引擎）。
- Photoreal：New Photoreal View/Place Camera…/Point Light…/Spot Light…/Distant Light（✅ 命令字符串已见）/Start Lit Simulation/Render After → 规划（OSG 不可用；用 VTK 分层渲染近似 + 相机/光源放置）。
- Tools：Options…（🟡 偏好已接）/Addins…（⬜）/Run Macro…（⬜ MACRO 解释器 P7）/Glass Catalogs…（✅）/Display Film Library/Example Model Library/LED Library/Source Library/Utility Library…（⬜ 库窗口，.ent 载入已备）/SOLIDWORKS Link（⬜）/Parameter Analyzer（⬜ 与优化同批）。
- Window：Tabbed/Floating Views（✅ QTabWidget；浮动=独立窗口规划）/Cascade/Tile H/V/Arrange Icons/Save-Restore-Clear View Layout（🟡 布局序列化规划，与 RestoreEnv 统一）。
- Help：Contents and Index/What's This?/Document Library/Release Notes/Command Reference/API/Macro/Intro Tutorial（⬜ 内嵌文档→外部 PDF 打开+CHM 解包索引）；About（✅）。

## 3. 命令调色板（Command Palette）对标

LT 调色板：第一层分类按钮 + 悬浮子面板；点击菜单 Insert 项时对应调色板按钮高亮。

| 第一层 | 子面板（已核实战） | 状态 |
|---|---|---|
| Elements | 3D Objects（Block 3Pt/CtrSphere/Ellipsoid/Cylinder/Toroid/EFiber/Revolved/Extruded/Swept/Skinned/Freeform/CPC-Revolved/CPC-Extruded/CPC-Poly）；2D Patterns；3D Textures；Place Zones；Place Reflectors（Revolved/Extruded Sheet） | 🟡 一级+飞行菜单已有，子面板逐步补 |
| Mechanical | Reference Geometry（SetModelRefCS/RemoveModelRefCS）… | 🟡 占位 |
| Modifying | Editing（Copy/CopyVector/CircArray/Align）；Element Editing（Cement/DeclareContact/AutoDeclareContacts/ReportOpticalContacts）；Grouping（AddToGroup） | 🟡 Copy 已通；其余规划 |
| Ray Tracing | Path Definition（AimPath/NSPath）；Surface Sources（RemoveSource…）；NS Raytrace（Ray Print） | 🟡 Ray Display 已通 |
| Viewing | Viewpoint（Depth/DepthValue）；Zooming（Center）；UCS Axes（OnCoordSys）；Metrics（AngularMeasure） | 🟡 测量已接 |
| Sources / Receivers（Illumination 模块扩展） | Apodizer 分布/光谱/接收器网格 | 🟡 采样引擎已通；调色板按钮待建 |

## 4. 工具栏对标（CoreUG Figure 6）

LT 3D 视图工具栏（从上到下按图示分区）：**Save｜（Editing）Delete、Set depth、User coordinate system placement｜Begin all simulations、Continue all simulations｜Aim NS Ray｜Ray Display options**。

规划最终形态 = LT 同构三工具条：A）标准（New/Open/Save/Print/Undo/Redo/Delete/Copy/Paste）→ 已有；B）视图（Fit/Zoom/Pane 1-4/Front-Side-Top-ISO/Wireframe-Solid-Translucent-Hidden）→ 已有；C）仿真（Set depth（✅规划）/UCS 放置/预备仿真/继续仿真/Aim NS Ray/Ray Display 选项）→ 待建。快捷键跟随全局（F keys/单键 X/Y/Z 已有）。

## 5. 3D Design 视图对标

| 元素 | LT 行为 | 现况 | 规划 |
|---|---|---|---|
| 布局 pane | 网格坐标/图纸坐标；多 pane（1/4） | VTK 渲染已有 | 四视窗+网格 overlay |
| 光标工具 | Select/Move/Rotate/SetDepth/Zoom/Pan/Measure/SetCurrentPoint/… | Select/Move/Measure/SetCurrentPoint 已接 | Rotate/Pan/深度设置工具条 |
| 鼠标/滚轮 | 左=选择/交互，中=旋转，右=平移，滚轮=缩放，双击=属性 | 已实现 | 与 LT 对齐微调（中键旋转、右键列） |
| 渲染模式 | Wireframe/Solid/Translucent/Hidden Line/Auto Render/Show Through | ✅ | 隐藏线消除+剖切（clip plane） |
| 视角 | XY/YZ/XZ/ISO/Other Side/Normal To/UCS 坐标系 | ✅ | UCS 徽章+法向视角 |
| 选择/高亮 | 点选/框选/Shift 增选；导航联动高亮 | ✅（导航联动） | 框选（rubber） |
| 坐标读取 | Cursor Location（X/Y/Z 实时坐标） | ➖ 未建 | 状态栏坐标条（规划） |
| 射线显示 | Ray Display 选项（按 path/波长/payload 过滤、ray history） | 🟡 折线 + origin 显示已有 | 过滤面板+命中列表 |
| 测量 | 距离/角度/度量（AngularMeasure） | 距离已通 | 角度/圆弧/坐标 |
| 视线方向/相机 | 透视/正交切换 | ➖ | 摄像机模型（复用视图矩阵） |

## 6. 导航/控制/输出面板对标

| 面板 | LT 行为 | 现况 | 规划 |
|---|---|---|---|
| System Navigator | 模型树（Components/Sources/Receivers/…）；≥500 项双击翻倍；右键排序/拖放/显示隐藏/属性 | ✅ 树+勾选+排序+上下文 | 类目节点（Sources/Receivers/Spectra/Configurations）+ 翻倍加载 + 拖放重排 |
| Preferences Navigator | General Preferences/Defaults/View Preferences 三大类→分类对话框 | ✅ | 与 LT 分类逐一对照（首选项清单→`PreferencesDialog` 表驱动） |
| Window Navigator | 已打开窗口列表，点击激活 | ✅ | 增加图表/对话框条目 |
| Configuration Control Panel | 配置创建/切换；最近仿真用的配置标记 | 🟡 面板存在 | 配置引擎（配置=参数组；合并到 scene 构建） |
| Output Window | Message log/Simulations( Ray Report)/Data exchange/Macro/Optimization/Photoreal 六标签；右键 Save text As/Clear All Text | ✅ 六标签已一致 | 智能分块（按仿真/命令时序）+ 保存/清除右键（部分已接） |
| Command Line | Prompt 提示 + 命令输入；空格补全；逗号分隔坐标；`;`=当前点；命令完成即高亮调色板按钮 | ✅（提示行+输入+历史+冒号输入） | 命令→调色板高亮联动（部分有）；tab 补全 |
| 状态栏/消息区 | 状态文本/消息气泡（警告/错误计数） | ➖ | 轻量状态栏（当前点/单位/仿真状态）+ 消息汇总 |

## 7. 视图类型与专用视图

- 2D Design：YZ 剖面；2D 草图（点/线/弧/圆）；2D 调色板（Block/Cylinder/Center Sphere/Sphere/Ellipsoid/EFiber/Skinned，已核实）→ 规划：正交投影 pane + 草图工具。
- Imaging Path：Y-Z 顺序路径 + 镜头处方表（lens prescription）→ 规划：顺序追迹组件。
- Table View：对象表/结果表（addColumn/setColumn/insertColumn/deleteColumn 已见字符串）→ 现有显示体表 + 网格结果表（图表已能导出 CSV）。
- Special Views：Glass Map（Vd-Nd 图+坐标读取）、LumViewer、参数分析器、Color Chart Viewer → 均以 matplotlib/表格窗口实现（glass map 立即可行：GLASS_CATALOG 已备）。

## 8. 当前完成度矩阵（概览）

| 区域 | 面数量(估算) | ✅ 完成 | 🟡 部分 | ⬜ 未建 |
|---|---:|---:|---:|---:|
| 菜单（13 菜单 180+ 项） | 185 | 62 | 76 | 47 |
| 命令调色板 | 60 | 10 | 18 | 32 |
| 工具栏 | 30 | 16 | 8 | 6 |
| 3D 视图交互 | 26 | 12 | 8 | 6 |
| 面板/输出/命令行 | 22 | 15 | 5 | 2 |
| 专用视图 | 9 | 2 | 2 | 5 |
| **合计** | **332** | **117 (35%)** | **117 (35%)** | **98 (30%)** |

> 上述“面数量”为 UI 元素计数（菜单项/按钮/面板项），与命令覆盖度（710 命令）正交：界面入口 100% ≠ 命令 handler 100%，两者分线推进，最终在 feature_checklist.json 上双 100%。

> **命令实现化进度（2026-08-25）**：菜单注册表（`ui_command_map.json`）198 项 —— **134 implemented / 64 NYI**（145 个已注册 handler）。“命令实现化”批量轮将 Analysis 全部分解为独立命令并接 `lts_charts`（Spatial/Angular Lum、LumViewer、Encircled、CIE/CCT/ColorDiff、Region、Add Intensity Mesh 导出 CSV）、补齐 View（2D/Other/UCS/NormalTo/AutoRender/ShowThrough/FitAllSame/FitSelSurf/UCSPrefs）、File（ExportLTS/PrintSetup/Save+LoadLibrary/RunExt）、Edit（CopyClipboard/UserCoatings/Immersion）、Tools（Options/Example·Film·LED·Source·Utility Library 浏览器）。

## 9. 分阶段路线图

### M-UI1 · 视图与工具栏骨架 —— ✅ 完成（2026-08-25）
1. 3D：四窗格布局（viewport 4 renderer，各窗格加视图名标签）、窗格几何网格、光标坐标栏（Cursor Location 实时显示于提示行）。
2. 工具栏第三区：Set depth（点击设定相机深度点）、Place UCS（当前点放置坐标标架）、Begin/Continue all simulations、Aim NS Ray、Ray Display 选项按钮（新增 depth/ucs/rays 矢量图标）。
3. View 菜单补齐（Pane 1/4、渲染模式、视角）——已有；隐藏线/Components 显隐分类列入 M-UI3。
**验收**：启动即 LT 同构图；所有渲染模式与视角可切换；坐标实时显示 —— 已达成。

### M-UI2 · 菜单→命令全量落地 —— ✅ 完成（2026-08-25）
1. 新增 `lts_menus.py` 声明式菜单注册表（**13 菜单 / 198 菜单项**，每项：label / cmd / lt(官方 9.1 命令名) / 快捷键 / 状态）；`lts_gui._build_menus` 重构为从注册表构建。
2. 自动生成 `ui_command_map.json`（菜单项 ↔ 命令 ↔ handler 三列，随构建刷新）；**136 个官方命令名**经 `official_aliases()` 合并进 `LT_ALIASES`，命令行可直接输入官方名（如 `MeshIllum`、`UnhideAll`）。
3. 当前覆盖：**82 implemented / 116 NYI**（93 个已注册 handler）；NYI 项保持现有“命令输入→Output 提示”机制。
4. Insert 三族创建向导（M-UI2b）：已落地 —— `lts_insert.py` 创建层（光学/机械实体含逐面 PropertyZone、表面光源含灯功率/apodizer/发射面、远场/平面接收器含网格），`InsertWizardDialog` 参数向导，创建后 `model.save()` 做 .lts 写回 + `_rebuild_scene` 重算；写回→重解析→区/光源/接收器绑定端到端验证通过。
**验收**：198 菜单项 100% 有入口与提示；45% 命令有真实 handler —— 已达成（82/198 = 41%，向导族完成后过 45%）。

### M-UI3 · 命令调色板对齐 —— ✅ 完成（2026-08-25）
1. 第一层分类与 LT 一致：**Elements / Modifying / Mechanical / Ray Tracing / Sources / Receivers / Viewing / Photoreal**。
2. **Elements > 3D Objects = LT 14 按钮**（Block 3Pt / Center Sphere / Ellipsoid / Cylinder / Toroid / Elliptical Fiber / Revolved / Extruded / Swept / Skinned / Freeform / CPC-Revolved / CPC-Extruded / CPC-Polygonal）；另含 Optical Element、3D Textures、Reference Geometry、Path Definition、Metrics/UCS、Photoreal 等子面板；按钮绑定官方命令名（tooltip 标注）。
3. **菜单↔调色板高亮联动**：任一菜单项激活即高亮对应调色板子面板（LT 行为），`lts_palette.highlight()` 按命令定位分类；`palette_coverage()` 统计覆盖。
**验收**：调色板 8 类全部可见；Insert/View/Simulation 菜单项激活后对应按钮高亮 —— 已达成（离屏冒烟 + 4 项调色板单测）。

### M-UI4 · 面板与工程化 —— ✅ 完成（2026-08-25）
1. System Navigator：类目化（Components/Materials/Spectral Regions/NS Rays/Illumination Manager/Source/Receiver List/Optimization Manager）、**500/翻倍分批加载（双击展开更多）+ 拖放重排 + 右键 Sort Alphabetically**。
2. **Configuration Control Panel 配置引擎**（`lts_config.ConfigurationEngine` 命名覆盖集/创建/激活/删除 + last-sim 标记；`ConfigPanel` 引擎驱动 + 右键 New/Delete/Mark current；`BeginForwardSimulation` 后标记 last-sim）。
3. **会话环境**：`SaveEnv/RestoreEnv`（QSettings：窗口几何/状态、面板可见性、浮动窗几何、最近文件）；`Save/Restore/Clear View Layout`；**Window**：Floating/Tabbed Views、Cascade/Tile H/Tile V/Arrange（`lts_layout.arrange_rects` 排布浮动窗）；Output 窗右键 Save text As/Clear All Text（已有）。
**验收**：导航/配置与 LT 分类对表；重启恢复环境 —— 已达成（配置引擎、排布、布局序列化、Navigator 分批 4 项单测 + 离屏冒烟）。

### M-UI5 · 专用视图与结果展示（随 P5/P6 并行）
Glass Map、LumViewer、网格结果表（照度/强度/亮度）、Ray Report 汇总、Color Viewer。全部分析接线到 `lts_charts.py`（已建成热图/极坐标/CSV）。

## 10. 工程与校验机制

- 组件边界：`lts_gui.py`（主窗/菜单/工具栏）、`lts_panes.py`（导航/输出/命令行）、`lts_view3d.py`（VTK 视图）、`lts_dialogs.py`（属性/向导）、`lts_charts.py`（分析图）、`lts_commands.py`（命令总线/710 名解析）、`lts_*` 数据层（模型/物理/追迹）。
- 每轮验收自检：`python output\_ui_diff.py`（新增脚本）——（1）从 lt_en_US.dll 重扫字符串簇，diff 菜单面；（2）菜单注册表 vs feature_checklist.json 覆盖；（3）`lts_gui.py` 中 handler 覆盖率统计。
- 复用既有资产：命令/命令名解析（resolve_command）、数据网格（远场/平面）、区链物理、接收器图表、材料/光谱。
- 单测：菜单注册表完整性（每菜单项有命令 id）、palette 路径存在性、环境保存/恢复往返。

## 11. 明确不做（首版范围外）

- Photoreal 光追真实感渲染（VTK 近似，不追 LT 渲染器语义）。
- COM/LTAPI 双向桥（P7，与优化器同批）。
- MACRO 解释器 UI（宏编辑器窗口，P7）。
- 分布式仿真（DSIM）界面。

## 附：逆向再取证手册

```powershell
# 1) 资源字符串（菜单/面板名唯一性）
$data = [IO.File]::ReadAllBytes('C:\Program Files\Optical Research Associates\LightTools 9.1.0\lt_en_US.dll')
#（脚本：输出 UTF-16LE 可打印序列 → 按偏移聚类）详见 output/_scan_dll.py
# 2) 命令→调色板/菜单路径
pdftotext -layout '…\Doc\CommandReferenceGuide.pdf' output\docs_txt\CommandReferenceGuide.txt
# 3) 界面章节原文
pdftotext -layout -f 44 -l 130 '…\Doc\CoreUG.pdf' output\coreug_ui.txt
# 4) 全量 HTML 帮助（5060 页）
& 'C:\Program Files\7-Zip\7z.exe' x -y -ooutput\ltchm '…\Help\lighttools.chm' '*.html'
```