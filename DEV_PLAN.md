# ltsdecoding → LightTools 9.1.0 100% 对标 开发计划（刷新版）

> 刷新日期：2026-09-04
> 刷新依据：当前四张面覆盖率/深度 + 命令执行深度审计 + CAD 引擎能力探测 + parity 语料规模 + 验证链现状。
> 与旧版差异：旧版按「覆盖率/解析/物理/UI/COM 验证」定义 100%；**刷新版重申：100% 对标 = 功能执行深度 + 数值等价，而不仅是「覆盖率 100%」**，并量化「覆盖率 100% 但执行深度薄」这一核心缺口，据以重排路线。
> 旧版里程碑 M0–M7 见 §7 对照与状态；本计划为 M0–M7 之后的**第 2 轮深化**。

---

## 0. 当前状态快照（2026-09-04，实测）

| 维度 | 现状 | 证据/说明 |
|---|---|---|
| 命令表—覆盖率 | **710/710 = 100%** | `coverage_report.py --json` |
| API 面—覆盖率 | **290/290 = 100%** | 同上 |
| 宏面—覆盖率 | **84/84 = 100%** | 同上 |
| 类面—覆盖率 | **378/378 = 100%** | 同上 |
| 命令/API/宏/类—「真实绑定」深度 | **均 100%** | 深度=`status=="real"` 或非 `pa_*` 别名（**我们自己的度量**） |
| **真实 T3 执行深度**（本次审计） | **result 13 / intent 557 / void 140** | `_audit`：按 handler 返回是否含真实计算载荷（volume/centroid/count/tris/spectrum/…） |
| GUI 真实执行命令 | **约 72 条内部命令** | `lts_commands.IMPLEMENTED`（其余多为菜单别名/passthrough） |
| 几何内核 | **manifold3d（无 OCC）** | `occ_available()=False`；SAT/STEP/IGES 读写均 **False**；布尔用 manifold3d 网格（box 级 union=12/cut=4 精确） |
| SAT 独立解码 | **66 文件** | `output/sat`；`sat_tessellator`+自研 loop 包围盒/三角化（本地自洽） |
| 实时 LT 交叉验证 | **阻塞** | `lt.exe` headless 超时 → `lt_parity --lt` 回退「pinned refs」（**非 LT 派生**）；`verify_sat_import` 阶段B（COM）本环境不可跑 |
| parity 语料 | **17 用例** | 多数 pinned 自算值（回归锁），仅少数为解析/自洽基准 |
| LTS 往返 | **约 183 文件字节一致** | `test_roundtrip.py`（OOM 跳过机制） |
| 宏 LT 扩展 | **已实现** | `_call` 内置 LTDBGET/LTDBSET/LTCHECKVAR/LTVERSION$/LTEVAL/COMMAND |
| 测试 | **41 文件 / 277 通过** | `pytest tests/` |
| 验证脚本 | 7 个 | verify_all / cad_exchange / goldens / pipeline / raytrace / sat_import / ui |

**结论**：四张面「识别/语义」层已 100%；但「**真实执行 + 数值等价**」远未 100%。真正驱动 LT 功能的几何内核、实时 LT 对表、模型作者化写回、以及大部分命令/API 的真实执行，仍是主要缺口。**覆盖率 100% ≠ 功能 100%**。

---


## 0.5 R1/R2 进展（2026-09-04，本轮实测）

### R1 · OCC 精确几何一等公民 —— 已集成并验证
- lts_occ 现支持 **pythonocc-core（OCC.Core）** 后端：修复 GProp 检测（from OCC.Core.BRepGProp import brepgprop，静态 brepgprop.VolumeProperties/SurfaceProperties），occ_available()=True。
- **运行时 = conda env occ**（conda-forge pythonocc-core + numpy/PyQt5/vtk/manifold3d/pytest；仅缺 requests/sklearn 不相关）。经 run_occ.ps1 前置 occ 环境的 Library/bin 入 PATH（OpenBLAS/OCC DLL 延迟加载必需），并设 PYTHONIOENCODING=utf-8（occ env 控制台默认 cp1252，打印中文会 UnicodeEncodeError）。
- 验证（occ env）：engine=OCC.Core；GProp 精确体积/面积/质心（box: vol=8, area=24）；OCC B-rep 布尔 boolean_meshes 返回 OCC shape，model_boolean 走 engine=OCC 且 union=12/cut=4 **精确**；STEP/IGES 往返保体积（sphere vol=33.51）；verify_cad_exchange.py 由 SKIP 转正 → 59/66 OK。
- **base env 已装 cadquery-ocp(OCP) 但其扩展 DLL 加载失败**（from OCP.OCP import * → DLL load failed），故 base 回退 manifold3d（geom_csg 仍 12/4/4，正常）。tests/test_occ.py **OCC 门控**：occ env 5 通过，base 5 跳过（基础套件 278 passed, 5 skipped）。

### R2 · lt.exe 无头 / COM 对表 —— 已打通
- lt.exe CLI -macro/-run/-batch 均 >6s 超时（启动完整 GUI/About/许可框）。
- **COM Dispatch("LightTools.LTAPI3") + DialogWatchdog 连接成功**（约 12–20s，看门狗自动关 About/许可对话框）。
- 新模块 **lt_com.py**：LTSessionCOM.connect/cmd/eval/dbget/getvar/close，封装真实 LT API（Cmd/Eval/DbGet/GetVar…）。
- lt_parity --lt 改走 COM：连接 → Eval 探针 → **live LT 派生基线**（macro_for_sum LT Eval("1+2+3+4+5")=15.0），与 ours 15.0 **rel=0 MATCH**。
- 注：LicenseIsAvailable() 返回 False，但 Cmd/Eval 可执行（计算引擎可用）。其余语料项需逐用例的 LT 命令映射（R2 剩余，G3）。



### R3 · OCC 精确路径铺开 + OCC 用例纳入 occ 运行时（2026-09-04 续）
- lts_geom_exec: 新增 occ_solid_metrics(kind) / occ_geometry_corpus() —— 经 OCC GProp 精确求实体 体积/面积/质心/包围盒 (sphere/cylinder/cone/torus/block)，全部与解析一致 (rel~1e-16)。
- 修复 lts_occ.prim_cylinder: r1 夹到 0 而非 1e-12，允许真锥(顶点), BRepPrimAPI_MakeCone(r1=0)。
- lt_parity: OCC 可用时把 OCC 几何语料纳入 CORPUS (geom_occ_sphere/cylinder/cone/torus/block_vol)；引擎敏感的重照亮网格/追迹语料 (rearlighting_mesh_tris / trace_escape，基于 base tessellation) 仅归 base 门禁，OCC 下移除以免数值随引擎漂移。
- occ 运行时 lt_parity --gate 全 PASS：base 用例 + CSG(OCC 精确 rel~1e-16) + 5 OCC 几何语料。
- 用 run_occ.ps1 于 occ 环境跑 lt_parity --gate / pytest tests/test_occ.py 即纳入 OCC 用例。

### R2 续 · 更多 live LT 派生基线（2026-09-04 续）
- lt_parity _lt_status 现对 macro_for_sum (LT Eval) 与 cie_ybar_550 (LT GetCIE1931YBar) 取 live LT 值，均 MATCH (rel 约 0 / 1e-7)。
- 新语料项 cie_ybar_550（colorimetry, ref=LT 实测 0.9949501）；lt_parity 从 17 -> 18（base）/ +5 OCC = 23。
- LT COM 语义探明：Eval 为度制 BASIC（Atan(1)*4=180, Log=log10）；GetCIE1931YBar/GetPhotopicFunction 可用。其余光学项（cct/focal/glass）需逐用例 LT 命令序列（R2 剩余 G3）。


- lt_parity _lt_status 重构为可扩的 LIVE_MAP：现对 macro_for_sum (LT Eval)、cie_ybar_550 (GetCIE1931YBar)、photopic_550 (GetPhotopicFunction) 取 3 条 live LT 派生，全部 MATCH。
  live: macro_for_sum=15.0 (rel=0), cie_ybar_550=0.9949501 (rel=1e-7), photopic_550=0.9949501 (rel=1e-7)。
- 新语料项 photopic_550（colorimetry, v_lambda）；lt_parity base 17 -> 19 / +5 OCC = 24。
- **R2 剩余 (逐用例调通 LT 命令序列, G3) —— 本环境探明为硬阻塞**：
  - 证据: LTAPI3 薄层 (Eval/Cmd/DbGet/GetVar) 无法触达 LT 内部模型/DB/宏系统：DbGet -> status 30 (not found)；GetVar -> (None,1) (Cmd 赋值不持久)；Begin/End -> status 70；DbList/DbKeyStr 对用户键全 NULL；Cmd("Material BK7"/"UserMaterials"/"GlassCatalogs"/"MaterialsTable") 返回 0 但无可查询对象；安装目录无可读玻璃目录文件 (Default 为 chart/env，Doc 无 glass/refract/schott)。
  - bb_cct: 需建黑体光源+颜色分析命令序列 (候选 API: BBSpectrum/BBSpectrumPeak/MakeBlackbodySpectralRayDistribution，不在薄 COM 暴露面)；Eval 无黑体/CCT 函数 (返回 0)。
  - glass_bk7_nd: 需正确材料创建 (MakeMaterialNew/SetMaterial) 后查其 DB 折射率键；薄 COM 无材料创建方法。
  - seq_focal: 需序列透镜建模 + 追迹 (QuickRayQuery/GetReceiverRayData)；薄 COM 无建模命令。
  - apod_lambert: 蒙卡采样；需 LT 源 apodizer 语义查询。
  - 结论: 这四项当前为解析基线 (bb_cct=6500 / seq_focal=lensmaker / glass=Sellmeier / apod=2/3)，均 PASS；若要变 live LT 派生，需走 LT 全自动宏 (lt.exe 宏/批处理) 或 LT 完整 API (非薄 LTAPI3)。已用可扩 LIVE_MAP 预留接入位。


### R3 工程侧 · OCC 运行时纳入 CI + 更多 B-rep 图元/草图/扫掠/放样（2026-09-04 续）
- **CI 纳入**: 新增 ci_occ.ps1 —— 用 occ env (Library/bin PATH + UTF-8) 跑 OCC 专项: occ_available/engine 断言 + pytest tests/test_occ.py + lt_parity --gate (含 9 OCC 几何语料) [+ -Full 时 verify_cad_exchange]。
- **更多 B-rep 图元 (草图/扫掠/放样)**: lts_occ 新增 prim_prism(草图挤出 / BRepPrimAPI_MakePrism)、prim_revolve(草图回转 / MakeRevol)、prim_loft(放样 / BRepOffsetAPI_ThruSections)、prim_pipe(扫掠 / BRepOffsetAPI_MakePipe，截面为 face 才成实体)。全部 GProp 体积与解析一致 (rel~1e-16)。
  - prism_tri=6.0 / revolve_tube=pi*3=9.4248 / revolve_disc=pi*4=12.5664 / loft_frustum=pi*7=21.991 / loft_cone=3.1419 / pipe_cyl=pi*5=15.708。
- lts_geom_exec: occ_solid_metrics 支持 prism/revolve/loft/pipe；occ_geometry_corpus 增 4 项 (geom_occ_prism/revolve/loft/pipe_vol)。
- test_occ 增 test_occ_sketch_primitives (occ 6 通过 / base skip)。
- lt_parity OCC 语料 5 -> 9；occ --gate 26 项全 PASS。


### R3 工程侧续 · B-rep 全图元（圆角/布尔树/变换树/抽壳）（2026-09-04 续）
- lts_occ 新增 B-rep ops: prim_transform(变换树/刚体, 体积不变)、boolean_tree(布尔树, 依次 fuse/cut/common N 个 shape)、prim_shell(抽壳, BRepOffsetAPI_MakeThickSolidByJoin, 移除一面向内空腔 thickness; 偏移取负才向内, 4x4x4 厚1 -> 杯 52)、prim_fillet(圆角, BRepFilletAPI_MakeFillet, 全部边或第 N 条, 单边 r=0.5 长2 -> 7.8927)。
- lts_geom_exec occ_geometry_corpus 增 4 项 (geom_occ_shell/fillet/booltree/transform_vol) -> OCC 语料 9 -> 13; 全部 rel~1e-16。
- test_occ 增 test_occ_brep_ops (occ 7 通过 / base skip)。
- 验证: ci_occ.ps1 (occ 运行时) test_occ + lt_parity --gate (13 OCC 精确) 全 PASS; base pytest 278 passed, 7 skipped。


### R3 收尾 · 草图约束系统 + 镜像（2026-09-04 续）
- **镜像**: lts_occ.prim_mirror(shape, normal, point) 经 BRepBuilderAPI_GTransform 反射; 体积不变 (box 关于 x=2 镜像 vol=8, 质心 [4,0,0])。加 geom_occ_mirror_vol。
- **草图约束求解**: 新模块 lts_sketch.py —— 2D 草图点集 + 几何约束 (distance/angle/coincide/horizontal/vertical/fixed/mirror)，迭代投影(Gauss-Seidel)求解。验证: 距离=5；勾股 3-4-5 直角三角 (约束 dist+angle, 面积 6, 斜边 5)；镜像对称。
- **草图 -> B-rep**: 约束求解后的三角形喂 prim_prism/extrude -> 体积 12 (面积6 x h2)。加 geom_occ_sketchtri_vol。
- tests: test_sketch.py (3 测试, 纯 Python base 可跑) + test_occ 增 test_occ_mirror_invariant。
- occ 语料 13 -> 15; ci_occ (occ) 全 PASS; base pytest 281 passed / 8 skipped。


### R3 收尾续 · 草图约束全族（切线/中心对称/过点线/样条镜像）（2026-09-04 续）
- lts_sketch 扩展约束族: tangent(线段-圆相切, 圆心到无限直线距离=半径)、symmetric(两点关于点中心对称)、point_on_line(点共线)、mirror_to/mirror_spline(镜像复制: 源控制点固定, 目标取关于轴的反射)。
- 验证(base): 切线 d=1.0；中心对称中点=目标；点过线投影到 y=0；样条镜像 A 固定 (1,1),(2,3) -> B=(1,-1),(2,-3)。
- test_sketch 3 -> 7 (tangent/symmetric/point_on_line/spline_mirror)；base pytest 285 passed / 8 skipped。


### R3->raytrace · OCC 精确求交接入追迹校验路径（2026-09-04 续）
- lts_occ.ray_intersect(shape, origin, dir, tmax) —— 经 IntCurvesFace_ShapeIntersector 精确射线-实体求交, 返回按 t 升序命中 (校验路径 ground truth)。
- lts_geom_exec.mesh_ray_nearest (Moller-Trumbore 网格求交) + occ_ray_verify(kind) —— 交叉验证: 生产网格/BVH 求交 vs OCC 精确 B-rep 求交的命中距离相对误差。
- 验证(occ): block/cylinder mesh vs OCC rel=0 (tessellation 精确); sphere(48 段) mean_rel=4e-4 (<0.1%); OCC block ray t=[4,6] (精确入口/出口)。
- test_occ 增 test_occ_ray_intersection_exact + test_occ_ray_mesh_agree (块精确, 球体<1%); occ 下 10 通过; ci_occ 全 PASS; base 285 passed / 10 skipped。


### R3 收尾 · verify_raytrace_occ 全模型逐射线校验（2026-09-04 续）
- lts_geom_exec 增 occ_mesh_ray_verify(mesh) (任意网格缝成 OCC B-rep, 外圈向质心发射射线, mesh_ray_nearest vs ray_intersect 交叉验证) + occ_model_ray_verify(model) (真实模型最大实体)。
- 新验证器 verify_raytrace_occ.py: 阶段A 图元级 (block/cylinder 精确, sphere<0.1%) + 阶段B --model rearlighting 最大实体 (sphere 2690 tris 等, mesh vs OCC rel=0)。OCC 不可用 SKIP; 接入 ci_occ.ps1 -Full。
- 验证: ci_occ -Full 全 PASS (cad_exchange 59/66 + ray-occ 图元/模型精确 + test_occ 10 + parity 15 OCC)；base geom/sketch 15 passed (无回归)。

## 1. 关键结论：把「100%」从覆盖率升级为执行深度 + 数值等价

旧版 100% 定义偏向「清单覆盖/解析/物理可实现/COM 验证」。但覆盖率 100% 时仍有 557/710 命令只返回 intent（`op/kind/message/params`），13 条返回真实计算载荷。**真正的 100% 对标，要求每条命令/API 的意义被「执行」出来并可与 LightTools（或解析解）对表。**

刷新版四条硬性可测度量（每项建立 checklist 销项）：

1. **执行深度（T3）**：每条命令/API 触发真实执行 —— 变更真实 `LTSModel`/`SurfaceOpt`/网格，或产出**可复算**的数值结果（体积/质心/网格/光谱/照度/追迹输出…）。`feature_checklist.json` 逐条按 T3 销项（阈值：**≥90% 命令、≥90% API 达到 T3**，不再是「status=real」）。
2. **数值等价**：结果与 LT 派生基线或解析解做相对误差比对 —— 几何 ≤1e-6、通量 ≤1%、色度 CCT ≤1%、追迹逃逸占比 ≤3%。
3. **几何 B-rep 一等公民**：OCC（cadquery-ocp / pythonocc-core）可用并作为精确路径（B-rep 布尔、GProp 质量属性、SAT/STEP/IGES 读写、精确求交）；manifold3d 仅作显示/兜底。CAD 交换与 LT 互导对表。
4. **验证闭环**：`verify_*` 全绿 + parity 语料按「命令/API 覆盖清单」扩展（目标：≥300 用例，每条命令/API 至少 1 个对表用例），并能区分「LT 派生 ref」与「自洽 pinned ref」。

---

## 2. 缺口分析（按杠杆排序）

| # | 缺口 | 现状 | 目标 | 影响 |
|---|---|---|---|---|
| G1 | **命令/API 执行深度** | 13 result / 557 intent / 140 void | T3 覆盖 ≥90%（先补高密度子系统） | 决定「能不能真的做 LT 做的事」 |
| G2 | **几何 B-rep 内核** | manifold3d；无 OCC；SAT/STEP/IGES 全 False | OCC 转正；B-rep 布尔/质量属性/CAD 交换 | LT 是 ACIS B-rep，精确几何/形状保真的根 |
| G3 | **实时 LT 交叉验证** | `lt.exe` CLI 超时；COM 已通（看门狗），live ref 已验证 | headless/COM 打通 → ref 变真 LT 派生 | 「与 LT 对表」成为可能而非自说自话 |
| G4 | **模型作者化写回** | `lts_insert`/`create_solid` 生成本地 .lts；未验证 LT 可开 | 写出的 .lts 被 LT 正常打开；SAT 精确导出 | 完成「可写」闭环 |
| G5 | **物理等价单测** | 有多项物理实现；对表用例少 | 解析解+LT 双路径逐特性对表（Fresnel 平板/TIR 棱镜/理想透镜/BSDF K-S/GRIN/色度） | 证明物理正确而非仅可实现 |
| G6 | **UI 功能等价** | M-UI1/M-UI2 完成；116+ NYI/薄处理 | 每 LT 操作有真实执行入口 | 「界面等价」落到功能 |
| G7 | **追迹吞吐/真实性** | numpy 追迹（rearlighting 全模型 OK） | 吞吐基准 + 与 LT 照度图对表（通量差 ≤1%） | 商业化规模可用 |

---

## 3. 刷新分阶段路线图 R0–R7

> 原则：先用可测的「执行深度/数值等价」基建立起度量，再做最大的两杠杆（几何 B-rep、实时 LT 对表），最后铺全命令/API 真实执行并收口。

### R0 · 执行深度度量与分类器（1–2 天）
- 交付：`coverage_report.py` 增加 **T3 深度分类**（T1 识别 / T2 语义 intent / T3 真实执行——变更模型或产出可复算载荷），逐命令/API 打标并写 `depth_tier.json`。
- 验收：`--depth-t3-gate <n>` 门禁；报表区分 4 张面 × {识别/语义/执行} 三维。

### R1 · OCC 几何内核转正（3–5 天，最高保真收益）
- 交付：安装/探测 `cadquery-ocp` 或 `pythonocc-core`；`lts_occ` 引为精确路径 —— B-rep 布尔、`shape_metrics`（GProp 体积/面积/质心）、SAT 精确读写、STEP/IGES 导入导出、OCC 精确求交（追迹校验路径）。
- 验收：`verify_cad_exchange.py` 不再 SKIP；阶段A 全绿；`geom_csg_*` 在 OCC 下体积/质心达 ≤1e-6；SAT 66/66 本地自洽 + 写回 roundtrip。

### R2 · 实时 LT headless/COM 打通（3–5 天）
- 交付：lt.exe 无头/宏模式看门狗（自动关 About/许可对话框，`verify_sat_import.py` 已有 COM 看门狗可复用）；`lt_parity --lt` 产出**真 LT 派生 ref**；COM 双向桥（驱动 LT + 读 LT）。
- 验收：`lt_parity --lt` 对现有 17 用例给出 LT 真实基线并 diff；`verify_sat_import` 阶段B 66/66。

### R3 · 命令/API 真实执行补全（按高密度子系统铺开，持续）
- 交付：按 `_audit` 密度排序逐子系统补 T3 —— `geometry_modeling`(157 intent)→`receiver_analysis`(62)→`misc`(53)→`ui_view`(45)→`colorimetry`(43)→`optimization`(41)→… ；每命令/API 接真实模型变更或真实数值计算。
- 验收：T3 覆盖 ≥90%（命令/API）；新增命令级 parity 用例。

### R4 · 物理等价对表语料（与 R3 并行）
- 交付：解析解 + LT 派生双路径用例：平板 Fresnel（R/T）、TIR 棱镜、理想透镜焦距/像距、BSDF 采样 K-S、GRIN 光程、色度 CCT、散射介质 Beer 吸收、衍射/相干/磷光。
- 验收：各项相对误差达 §1.2 阈值；parity 语料 17→≥300。

### R5 · 模型作者化 + CAD 交换（依赖 R1）
- 交付：结构化写出 ORACAD（对齐缩进/命名/边连接），写回 .lts 被 LT 打开；SAT/STEP/IGES 导出；Undo/Redo 事务栈。
- 验收：新建 solid/source/receiver 的 .lts 在 LT 打开无警告；STEP/IGES 与 LT 互导对表。

### R6 · UI 功能等价（消灭 NYI）
- 交付：把 M-UI 的每一项菜单/面板接到真实 handler；116+ NYI 转真实执行；命令调色板/工具条/状态栏功能闭环。
- 验收：UI 每操作产生真实模型/分析变更；UI 回归全绿。

### R7 · 性能 + 收口
- 交付：追迹吞吐基准（numpy 向量化 → 可选 Embree/CUDA）；checklist 逐条 T3 销项报告；双端（本地+LT）对表报告归档；Windows 打包/文档/崩溃报告。
- 验收：`feature_checklist.json` 全绿（T3）+ `verify_all --full` 全绿 + 性能达标。

---

## 4. 依赖与推进顺序

```
R0 ─> R1 ─> R2 ─> R3 ─> R7
           └─> R5         │
R3 ─> R4 (与 R3 并行)     │
R6 依赖 R3/R1             │
                 R0/R1 全程支撑
```

关键路径：**R0→R1→R2→R3→R7**。R3/R4/R6 可在 R2 打通后并行铺开；R5 依赖 R1 的 OCC。

---

## 5. 关键风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| OCC 在本环境不可用/编译失败 | R1/R5 阻塞 | **已解（partial）**：conda env occ 有 pythonocc-core；base 的 cadquery-ocp(OCP) 扩展 DLL 加载失败；occ 环境必须前置其 Library/bin 入 PATH（OpenBLAS delay-load）否则 numpy matmul segfault (0xc06d007f)；run_occ.ps1 封装 |
| lt.exe 无头超时（许可/About 框） | R2/R7 对表阻塞 | 看门狗关闭对话框 + 宏模式无 UI 启动；超时则 ref 标为「p-in（自洽）」，_audit 记录真实 LT 缺口 |
| 执行深度主观难分 | R0 分类器失真 | 以「是否变更模型状态 or 产出可复算载荷」为客观判据，人工校准 10% 样本 |
| 蒙特卡洛性能 | R4/R7 | numpy 向量化起步，预留 Embree/CUDA 后端；黑白盒基准 |
| 单人代码量 | 整体排期 | 引擎 headless 与 UI 解耦，先交付 CLI/对表，再 UI |

---

## 6. 近期下一步（本周，按序）

1. **R0**：写 T3 深度分类器进 `coverage_report.py`，出 `depth_tier.json`（命令/API 三维打标）。
2. **R1 第一步**：探测并安装 `cadquery-ocp`（或 `pythonocc-core`），跑 `verify_cad_exchange.py` 确认转正。
3. **R3 起点**：从 `geometry_modeling`（157 intent）开始，把 Make*/块/球/柱 + 布尔/阵列/变换补成真实执行，并加命令级 parity 用例。
4. **R2 探针**：给 lt.exe 加看门狗尝试无头宏，记录是否可回传结果；若不可，标记 G3 为本环境硬阻塞并在 refs 中体现。
5. 每步跑 `verify_all --full` + `pytest tests/` 全绿后提交。

---

## 7. 旧版里程碑 M0–M7 现状对照

| 里程碑 | 原计划内容 | 现状 |
|---|---|---|
| M0 | checklist 固化+语料基建 | ✅ |
| M1 | 解析层 100%（往返字节一致） | 🔶 往返 done；对象创建写回/Undo 未建（R5） |
| M2 | 几何验证链（SAT 66/66） | ✅ 本地自洽；阶段B COM 本环境不可跑（R2） |
| M2b | OCC 精确 B-rep + CAD 交换 | ⬜（R1） |
| M3 | 光学属性+光源接收器 100% | 🔶 物理实现广；LT/解析对表用例不足（R4） |
| M4 | 光线追迹引擎 100% | 🔶 numpy 追迹可跑；LT 通量差对表不足（R4/R7） |
| M5 | 分析与可视化 100% | 🔶 报表/绘图在；UI 功能等价未达（R6） |
| M6 | 优化器+MACRO+API 100% | 🔶 MACRO 84/84；优化器空白（R3/R6） |
| M7 | 收口 | ⬜（R7） |

> 后补：Phase A/B/C/D 已把四张面「识别/语义」层做到 100%（L5/L1/L2 部分真实执行）；本刷新版在其上补「真实执行 + 数值等价」。
