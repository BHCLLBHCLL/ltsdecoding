# ltsdecoding 与 LightTools 功能差距分析

> 基准版本：**Synopsys LightTools 9.1.0（December 2020）**
> 基准依据：本机安装的官方文档（22 篇 PDF 全文提取至 `output/docs_txt/`）+ 181 个 LTS 样本语料
> 功能清单：[`feature_checklist.json`](feature_checklist.json)（9.1 基准，机器可销项）
> 分析基线日期：2026-08-23（8.7 版）→ **2026-08-24 升级至 9.1 基准并纳入验证结果**
> 综合覆盖度评估：**约 40–45%**（完整度与深度加权；材料绑定 + 正向追迹已接到 GUI，优化/MACRO/Photoreal/偏振仍为空白）

---

## 〇、9.1 基准功能清单（对齐目标的数据化）

| 基准源 | 条目数 | 说明 |
|---|---|---|
| Command Reference Guide | **710 条命令** | TOC 全量提取，覆盖 15 个子系统 |
| API Reference Guide | **290 个 COM API 函数** | LTAPI3 接口面 |
| Macro Reference Guide | **84 个宏函数** | MACRO 语言 |
| LTS 语料（181 文件） | **378 个对象类** | 实测 distinct ORACAD 类 |

命令按子系统分布（前 8）：

| 子系统 | 命令数 | | 子系统 | 命令数 |
|---|---|---|---|---|
| 几何建模 | 187 | | 数据交换 | 40 |
| 接收器/分析 | 70 | | 光源建模 | 34 |
| UI/视图 | 70 | | 光线追迹 | 31 |
| 优化 | 45 | | 光学属性 | 23 |

其余：色度 45、工具 40、仿真管理 22、真实感可视化 17、成像分析 16、宏脚本 10。

## 一、现有代码资产清单

| 模块 | 职责 | 成熟度 |
|---|---|---|
| `lts_parser.py` | LTS（ORACAD v4.4 文本脚本）解析器：对象创建/方法调用/属性块/内嵌 SAT/通用 ORA 数据块 | **181 文件 0 错误 0 警告**（自 40.2 万警告清零） |
| `sat_tessellator.py` | 纯 Python ACIS SAT 细分（NURBS 曲面/边界环/三角化） | **66/66 OK**（loop 并集包围盒作为权威参照后全绿） |
| `lts_occ.py` | OCCT 几何引擎封装（布尔/变换/图元），OCC 不可用时降级 | 可用，但为可选路径 |
| `lts_geom.py` | CSG 树求值（Union/Difference/Intersection）、刚体变换级联、网格布尔 | 可用 |
| `lts_vtk.py` | VTK 渲染层：PolyData、着色/线框/半透明 actor、相机、方位标记 | 可用 |
| `lts_model.py` | Qt-free 文档模型：属性外科手术式编辑、对象删除、保存 | 可用 |
| `lts_gui.py` / `lts_panes.py` / `lts_icons.py` | 类 LightTools GUI：三窗格（树视图/3D/控制窗口）、菜单/工具栏 | 可用（只读为主） |
| `verify_sat_import.py` | 双阶段验证：阶段A 本地自洽；阶段B lt.exe + COM 重导入+重导出比对 | **四重全绿：本地自洽 66/66；COM 导入 66/66；重导出 body 包围盒 ≤1e-6；重导出 loop（裁剪面）包围盒逐位一致（dev=0）** |
| `feature_checklist.py` | 从 9.1 官方文档提取功能清单 → `feature_checklist.json` | 完成（710+290+84+378 条目） |
| `output/docs_txt/` | 22 篇官方 PDF 全文（Command/API/Macro Reference 等已利用） | 完成 |

## 二、对象级覆盖（181 文件语料，378 类）

解析层面：**378 类全部可读**（corpus_scan.json 完整落盘，0 错误 0 警告）；语义/物理层面：**不足 15 类有实质处理**。

- 几何类（CSG 树/通用实体/圆柱/圆环/球/长方体/图元算子，rearlighting.lts 中 220+ 实例）→ 已渲染、已与 LightTools 往返验证
- 光学属性类（PropertyZone / SurfaceInfo / AmplDirOpticalProperties / RTRayAmplitude / SpecularRayDirection / LambertianScatterer / FresnelLoss）→ 材料级 SurfaceOpt 已绑定；逐面 PropertyZone 链仍未驱动
- 材料类（UserGlass / MaterialInstance / ConstantRefractiveIndex / LaurentIndex / OpticalDensityAbsorption / TransmissionAbsorption / WavelengthData）→ **已绑定 n(λ) 与 α**，接到追迹界面
- 光源类（SurfaceEmitter / CylinderSource）→ 沿局部 +Z 锥发射；NS Aim 已接 GUI
- 接收器类（FarFieldReceiver / IntensityDataMesh / IntensityScatterMesh）→ **无网格拓扑解析**
- 仿真管理（ForwardIllumSim / NSRayManager）→ Begin Forward / Ray Display 已接；管理器对象仍为占位
- 光谱（WavelengthObj / SpectralRegionEntity / ColorComponent）→ 材料吸收光谱已采样；系统级光谱未驱动追迹波长

## 三、子系统差距矩阵

| LightTools 子系统 | 现状 | 覆盖度 | 差距要点 |
|---|---|---|---|
| LTS 解析/数据层 | 181 文件 0 警告、378 类可读、属性编辑+对象删除+插入写回 | **~80%** | 无多版本兼容矩阵、无 round-trip 字节级保证、Undo 仅覆盖插入/隐藏 |
| 几何内核（ACIS/CSG） | SAT 细分 **66/66 OK**；布尔依赖 OCC 可用性；测量/Move | **~70%** | 无精确 B-Rep 保证、无草图特征（拉伸/旋转/扫掠）、无剖切/质量属性 |
| 3D 显示 | 着色/线框/半透明、三视图、高亮、NS/正向光线折线 | **~55%** | 无假彩色云图、无剖切平面、测量为对话框而非 3D 标注 |
| UI 框架 | 菜单/工具栏/三窗格、材料管理器、Table View、710 命令别名 | **~50%** | 光源/接收器创建对话框仍简、无完整 Undo 栈 |
| 光学属性（材料/表面） | LTS Laurent/Constant/金属已绑定 n(λ)/α；菲涅尔界面 | **~40%** | 镀膜、BSDF 纹理、逐面 PropertyZone 链、偏振未接到 GUI |
| 光源/接收器 | 源沿局部 +Z 锥发射；Aim NS Ray | **~25%** | 完整空间×角度 apodizer、接收器网格数据、far-field 语义仍缺 |
| 光线追迹/仿真引擎 | Engine 已接 Begin Forward / Ray Display；通量守恒 | **~35%** | 无偏振/相干、无 31 条 ray_tracing 命令全覆盖、无加速模式 |
| 结果分析（照度/坎德拉） | 命中 XY 直方图 + 逃逸方向强度网格 | **~15%** | 无接收器网格照度图、无 CIE/均匀性、70 条 analysis 命令大部分 NYI |
| 优化器 | 无（OptimizationManager 仅占位对象） | **0%** | 变量/评价函数/约束、阻尼最小二乘/单纯形/遗传算法、公差分析缺失；9.1 有 45 条 optimization 命令 |
| MACRO 脚本 / LTAPI | 无（9.1 参考文档已全文提取） | **0%** | MACRO 解释器（84 宏函数）、批处理、COM API 兼容层（290 API 函数）缺失 |
| CAD 交换 | GUI 导入 SAT/STL/STEP/IGES，导出 STL/SAT；LT 导入 66/66 | **~45%** | 精确 SAT 写出、STEP 网格→B-Rep 仍弱 |
| 验证体系 | **四重全绿** + 材料/追迹单元测试 | **~85%** | 光学属性/追迹结果的 COM 对表未建；回归测试未 CI 化 |

## 四、差距本质定性

1. **量级差距**：当前项目是"LTS 解码器 + 3D 查看器 + 已接线的正向追迹"；LightTools 仍是完整商业光学 CAD（优化 / MACRO / Photoreal / 偏振 / 接收器网格）。
2. **深度断点**：解析与几何验证已闭环；材料 n(λ)/α 与蒙特卡洛传播已接到 GUI。逐面 PropertyZone、接收器网格、优化器仍是空白。
3. **决定性缺口**：优化器、MACRO/COM、Photoreal、偏振、接收器级照度图。
4. **验证已闭环（几何基线）**：`verify_sat_import.py` 双阶段 66/66；光学 COM 对表仍未建。

### 关键技术发现（几何验证链）

- LightTools 导出 SAT 的 `body` 记录包围盒常为**未裁剪曲面范围（松散盒）**；`loop` 记录包围盒才是裁剪后真实面片范围——验证须以 loop 并集为权威参照（7 个"样条边界采样警告"实为该参照错误导致的误报，细分器本身精确）。
- COM 自动化关键路径：`SetOption("ShowFileDialogBox", 0)` → 路径用正斜杠 → 保留 SAT 头行 + CRLF → list 句柄存活期管理（ListDelete 使 key 失效）→ JumpStart（ltcom64.jsml）删除实体。

## 五、"100% 对齐"的验收度量（四条硬标准）

| # | 标准 | 度量 |
|---|---|---|
| 1 | 解析完整 | 9.1 全功能清单（710 命令/290 API/84 宏/378 类）内所有 LTS 类可读、可写、可往返（黄金文件字节级一致） |
| 2 | 物理正确 | 每个光学特性有可验证实现：与 LightTools COM 输出或解析解比对，几何容差 ≤1e-6，通量容差 ≤1% |
| 3 | 界面等价 | LightTools 的每个操作（创建/编辑/仿真/绘图/优化）有对应 UI 入口 |
| 4 | 验证闭环 | `verify_sat_import.py` 双阶段比对全绿（**已达成，66/66**）；`feature_checklist.json` 条目 100% 销项 |
