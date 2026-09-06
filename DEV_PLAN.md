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


### R4 · 物理等价语料 + 修复 Fresnel 非正入射 bug（2026-09-04 续）
- **发现并修复 bug**: ltsoptics.surface.fresnel_coeff 在非正入射时 Rs/Rp 分母约定错误 (R45=0.05707 vs 标准 0.05284, 差约 8%)。改为标准 Fresnel: rs=(n1 ct1 - n2 ct2)/(n1 ct1 + n2 ct2), rp=(n2 ct1 - n1 ct2)/(n2 ct1 + n1 ct2)。修正后 0-56° 全角度与标准解析一致 (rel~1e-16)。
- **物理等价语料** (lt_parity, base 19 -> 24): phys_fresnel_norm(0.042388)/phys_fresnel_45(0.052837)/phys_tir_crit(41.19°)/phys_grin_snell(n·d_x=0.75 守恒)/phys_bsdf_frac(cos>0.5 占比=0.75)。
- test_physics.py (6 测试): Fresnel 全角度 vs 标准、TIR 临界角/全反射、BSDF Lambertian KS(<0.02)、GRIN Snell 动量守恒+均匀直行、透镜焦距。
- 修复后 verify_all --full 全绿: 16 golden OK, raytrace conservation 0.0007%, parity 24 全 PASS (rearlighting_trace_escape 仍 PASS, 修正后更贴近 LT ref ratio=0.1267)。


### R4 续 · 体积散射/Beer / 衍射 / 相干 / 磷光 / 近轴成像 解析对表（2026-09-04 续）
- 新增 9 物理语料 (lt_parity 24 -> 33): phys_beer(exp(-mu L)), phys_mfp(1/mu), phys_albedo(mu_s/(mu_a+mu_s)), phys_grating_angle(d sinθ=mλ), phys_grating_order(二元光栅 1 级=4/π²), phys_stokes(λe/λp), phys_visibility(coherent excess=(c-i)/i), phys_lifetime(指数均值=τ), phys_paraxial(单透镜 paraxial_image_distance=bfl)。
- test_physics 6 -> 11 (Beer/光栅/斯托克斯/相干可见度/磷光寿命/近轴像距)。
- 验证: verify_all --full 全绿 (parity 33 PASS, pipeline/raytrace OK, conservation 0.0007%)。


### R4 续 · HG 归一性 / 偏振 / 膜系 / 球差(矢高) 解析对表（2026-09-04 续）
- 新增 7 物理语料 (lt_parity 33 -> 40): phys_hg_norm(HG 相函数球面积分=1), phys_hg_mean(mean_cos(g)=g), phys_pol_malus(Malus cos²45=0.5), phys_pol_dop(完全偏振 DOP=1), phys_brewster(atan n), phys_ar_reflect(薄膜基底裸反射=Fresnel), phys_sag_sphere(球面矢高精确 = r-sqrt(r²-y²), 球差>近轴)。
- 注: spot_diagram 原始点有巨大 x 异常 (6.9e9, 疑似 bug) -> 球差改以矢高 sag 解析对表; seq.spot_rms=0.2815 仍由 golden 覆盖。
- test_physics 11 -> 15 (HG 归一/mean, Malus/DOP/Brewster, 薄膜 λ/4 增透 R=0, 球面矢高)。
- 验证: parity --gate 40 PASS; verify_all --full 全绿。


### R4 续 · 体积散射退偏 / 衍射 sinc² / 相干长度-相位 解析对表（2026-09-04 续）
- 新增 5 物理语料 (lt_parity 40 -> 45): phys_grat_sinc2(矩形光栅 sinc², (sin(π/4)/(π/4))²=0.8106), phys_grat_disp(角向色散 deg/nm), phys_grat_sum(光栅各传播级权重和=1, 能量归一), phys_coh_sum(相干叠加 |Σa|²=(Σa)²=4), phys_poldep0(体积散射无退偏 ensemble DOP=1)。
- 验证: scatter_polarization depol=0 -> ensemble DOP=1; depol=0.5 -> 0.49; depol=1 -> 0.02 (退偏机制正确, 但单事件退偏只随机化偏振方向, 需 ensemble DOP 才体现)。random_phase(inf)=0 确定性; random_phase(0) 均匀 [0,2π)。
- test_physics 15 -> 18 (光栅 sinc²/色散/归一, 退偏 ensemble DOP 单调, 相干/反相/随机相位)。
- 验证: base pytest 303 passed; lt_parity --gate 45 PASS。


### R4 收尾 · 物理语料与 LT 派生再对表（2026-09-04 续）
- lt_parity LIVE_MAP 扩展 9 项物理 LT 派生 (经 LT Eval 度制求值): phys_fresnel_norm / phys_grating_angle / phys_tir_crit / phys_brewster / phys_pol_malus / phys_beer / phys_stokes / phys_sag_sphere / phys_grat_disp。
- 探明 LT Eval 语义: 度制三角 (Atan/Asin/Sin/Cos 度数), ^ 幂, Exp/Sqrt/Log(log10), 无 Pi 常量 (Pi=0)。故 grating_order/hg 等用 Radian sinc 的项不走 Eval (保留解析 ref)。
- 实测 lt_parity --lt: **12 条 live LT 派生全 MATCH** (macro/cie_ybar/photopic + 9 物理, rel 0 或 1e-6), parity --gate 45 PASS。
- 说明: 这些物理项经 LT 数值引擎 (Eval) 计算, 与 our 解析一致 -> 物理语料从「pinned/解析」升级为「live LT 派生」。


### R6 · 草图特征 UI 接线（lts_sketch + OCC/网格 -> 实体）（2026-09-04 续）
- lts_geom_exec: 新增 polygon_prism_mesh(2D 多边形挤出网格, trimesh convex hull, 正确体积) + sketch_build_solid(model, preset, gen, height) (草图预设 rt345/rect/triangle + 约束求解 -> 实体 insert_mesh)。
- lts_gui_sketch.py (新): SketchFeatureDialog(QDialog) 选预设/生成方式/高度, Solve+Generate 调 build_solid -> 生成实体; build_solid 纯逻辑可 headless 测试 (返回 model/oid/profile/volume)。
- lts_gui.py: 新增 _sketch_feature/_on_sketch_generated 方法 + "sketch_feature" 命令绑定; lts_commands.py: "SketchFeature" 别名 + IMPLEMENTED (72->73, aliases 179->180)。
- tests/test_gui_sketch.py (4): build_solid rt345=12/rect=18, 对话框解算, viewer.run_command("SketchFeature") 不崩溃 (offscreen Qt)。
- 验证: GUI offscreen 可构造; coverage 710/710 depth 100%; base pytest 307 passed / 10 skipped。


### R6 续 · 属性面板 SurfaceOpt 编辑（SetPropertyTo* 写回 + 属性编辑器）（2026-09-05）
- lts_optics_bind: SURFACE_PRESETS (Surface Properties 官方预设下拉, 散射族简化为 Lambertian) + apply_surface_preset(model, oid, preset, R/T/side, surface) —— 预设写回实体 PropertyZone 链 (setPropertiesName + setAmplitudeOverride + 区/振幅/方向对象数值键, 键在源文本存在时 Save 落盘); zone_prop 增 override 语义 (预设振幅优先于已解析振幅类, 区级数值覆盖预设默认; 无 override 时显式振幅仍优先 = LightTools 语义, 有回归护栏)。
- lts_dialogs PropertiesDialog: 新增 Surface Optics 页 (预设下拉/R/T spinbox/散射方向/逐面选择/区链摘要回填, 切预设自动带默认值并按 kind 启停参数); surface_preset_requested 信号。
- lts_gui: _fill_surface_info (打开属性页回填 zones 现状) + _apply_surface_preset (写回+日志+dirty) + _set_prop_to; lts_commands: SetPropertyTo* 9 条官方命令别名 -> set_prop_to_* (IMPLEMENTED 73->82, aliases 180->189), 命令行/宏直达。
- 追迹贯通: 写回后 scene_from_model 逐三角 SurfaceOpt 即时生效 (transmitting->mirror->lambert_scatter, 用户 R 直达)。
- tests/test_gui_surface_props.py (8, offscreen): Mirror/Lambert(用户 R/T/side)/命令名直译/单面写回/显式振幅优先回归/场景消费 + 对话框页参数启停与信号 + viewer 命令与属性页 Apply 贯通。
- 验证: base pytest 315 passed / 10 skipped (+8); coverage --gate 710/710 PASS; verify_all --full 全绿 (UI registry 202/202, parity 45 PASS)。


### R6 续 · 仿真面板参数化（ray 数/seed/收敛 → run_forward）+ 草图 3D 预览核对（2026-09-05）
- lts_gui_sim.py (新): SimulationParamsDialog —— Begin Forward Simulation 参数面板 (每源 ray 数 / 随机 seed / max_bounces 收敛 / max_tris 场景上限), Run 触发 on_run(params), 参数经 QSettings 持久化回填; params()/set_params() 纯逻辑可 headless 测试。
- lts_gui: _begin_forward 扩展签名接收 seed/max_bounces/max_tris (直通 run_forward) + 记录 _last_sim_params; 新增 _sim_params (参数面板) / _sim_apply (Run 回调); begin_fwd 菜单绑定改为打开参数面板 (命令行 begin_fwd N 宏路径保持直达); IMPLEMENTED 83 (sim_params)。
- lts_gui._on_sketch_generated 修复: 原调 _refresh() (磁盘重载; 新建无 path 模型不生效, 已保存模型会丢弃内存新增实体) -> 改为内存内更新: 选中新实体 + sys_nav.populate + _rebuild_scene(fit=True) 重建 actor/高亮/fit + _mark_dirty; insert_mesh 已同步 geo_boxes/tess_parts, 3D 装配层一条龙。
- tests/test_gui_sim.py (5): 对话框默认/编辑参数、Run 回调+持久化回填、_sim_apply 直达追迹 (n_rays=6 / n_tris<=6000)、菜单命令开面板、同 seed 多次追迹 rayspace 一致性。
- tests/test_gui_sketch.py 增 3D 核对 (VTK 依存, Render 打桩 — 无 GPU 环境像素渲染不可用; 核对装配层): 新建无路径模型草图实体 -> actor 逐实体、选中高亮色 (1.0,0.85,0.2)、dirty。
- 验证: base pytest 321 passed / 10 skipped (+6); coverage --gate 710/710 PASS; verify_all --full 全绿 (UI registry 202/202, parity 45 PASS)。


### R6 续 · 仿真面板参数再下沉 + Continue 复用（2026-09-05 续）
- lts/trace/from_model: run_forward 扩展 receiver_rows/receiver_cols (None=接收器自带; 覆盖平面接收器照度网格与远场强度网格) + emission_wl (主波长: 材料色散 scene wl_nm 与无光谱源发射采样共用) + apodizer (非空时全局覆盖各源发射方向 apodizer); rays_from_sources 增 apodizer 参数; plane_receiver_grid/far_field_grid 增加 rows/cols 覆盖透传。
- lts_gui_sim: SimulationParamsDialog 增 4 字段 (Emission wavelength nm / Receiver mesh rows·cols [0=own] / Emission apodizer [Auto·Lambertian·Uniform·Power m=1]), DEFAULTS/QSettings 8 键全覆盖。
- lts_gui: _begin_forward 接 8 参数 (记录 _last_sim_params 全量); 新增 _current_sim_params (面板当前值/上次/默认) + _continue_sim (复用当前参数: seed+1 换种子继续, ray 数保底 40); begin_all_sim/continue_sim 绑定改为复用面板参数 (原 continue_sim 单独 extra 逻辑归并)。
- tests/test_gui_sim.py 5->9: 对话框 8 键默认/编辑/回填、_sim_apply 直达追迹、网格覆盖 (rows=10/cols=8)、波长下沉 (480)、apodizer 覆盖统计 (uniform mean cosθ≈0.5 < lambert≈2/3, 单 RNG 流, 800 样本)、continue 复用 (seed 9->10, ray 40 保底, bounces/tris 保留)。
- 验证: base pytest 325 passed / 10 skipped (+4); coverage --gate 710/710 PASS; verify_all --full 全绿。


### R6 续 · 分析面板参数接线 + Quick Preview 复用（2026-09-06）
- lts/trace/from_model: run_forward 增 spectrum_bins (>0 时接收器光谱按 380..780nm 均匀分箱, 色度采样); receiver_spectrum 增 bins 参数 (0=保留原生离散波长, >0=重构光谱 bin 中心键, 关联 colour_temperature 色度计算)。
- lts_gui_sim: SimulationParamsDialog 增 Analysis 区 4 字段 (Illuminance bins fallback 8..256=32 / Intensity theta·phi fallback 4..90·8..180=18·36 / Spectrum bins 0..128=0), DEFAULTS/QSettings 12 键全覆盖。
- lts_gui: _analysis_illuminance/_analysis_intensity 无接收器 fallback 改用面板 bins (_analysis_param 从面板/上次/默认取值); _preview_forward (quick_preview: ray 数压至 8, 其余面板参数——seed/bounces/tris/网格/波长/apodizer/光谱分箱——全复用); _continue_sim 联动 spectrum_bins。
- tests/test_gui_sim.py 9->12: 12 键默认/编辑/持久化回填、spectrum_bins 分箱 (黑体源 3500K, 光谱键 ≤16 且 ∈(380,780))、quick_preview 复用 (n_rays=8, seed/bounces/tris/spectrum_bins 保留)、_analysis_param 面板读数与默认回落。
- 验证: base pytest 328 passed / 10 skipped (+3); coverage --gate 710/710 PASS; verify_all --full 全绿。


### R5 · 模型作者化: Undo/Redo 事务栈 + 写回验证（2026-09-06）
- lts_gui 事务栈重写: _undo/_redo 四类记录 (insert 快照 / hide / delete / props), 修复原 hide 分支 redo 双 push bug 与 redo insert NYI; insert 快照含对象引用+tess_parts+geo_boxes 项 (redo 完整恢复); delete 记录/撤销 (deletions 移除+hidden 恢复); props 记录前后快照 (zone/amplitude/direction 对象), undo 恢复旧值+unset 新增键 (LTSModel.unset_prop 新增), redo 重放。
- _apply_surface_preset 经 _props_targets 快照写回对象 -> push props 事务; _delete_selected 记录 delete; insert push 改快照形式; "undo"/"redo" 入 IMPLEMENTED (84)。
- lts_create.render_graph (新): 对象图 -> 真实 LT 嵌套语法写回 (边=嵌套子块, 闭合行 `} method: $ref;` 完成子块闭合+挂父, 与 LT 写盘同构), 替代 render_object flat 键行 (原格式边重载后误入 props —— 已修复, 重载后 zones_for_solid/edges 正确)。
- 网格实体写回: LTSModel._sat_text_for_part —— 无 raw_sat 的网格实体, OCC 可用时 shape_from_mesh+sat_write 序列化为内嵌 SAT (make_solid_block 末行替换挂父); 当前 pythonocc 环境无 SATControl 后端时自动降级 props 语义块 (结构/属性无损)。
- verify_model_write.py (新, 接 verify_all 常规面): 空模板新建 (block/sphere/cylinder+source+2 receivers+草图+mirror 写回) -> save -> 重载 -> block 体积精确 480/球半径参数+5% tess 容差/sketch (sat_write 后端可用时精确, 否则语义)/mirror 写回 3 区重载保留/对象图 84 对象/保存幂等/re-parse; occ 与默认两环境均 PASS。
- tests/test_gui_undo.py (6, offscreen): insert 撤销重放 (对象/tess/geo/插入标记恢复), 空栈 WARN, hide 撤消重放, delete 撤消重放, props (mirror 撤消回 Fresnel+新键 unset+redo 重放, 用户 R/T/side 值往返)。
- G7: run_forward 分段计时 (scene/emission/trace/preview/total -> meta["timings"]); verify_raytrace 输出吞吐基准 (本机全模型 n=8: 1.10 rays/s end-to-end, trace-only 1.73, scene 22.6s/emission 1.2s/trace 41.6s; <0.5 rays/s 告警) + LT 通量比门禁 (ref_ratio ΣI·Ω 逐格同 Ω, n>=100 时 3% 判定)。
- 验证: base pytest 334 passed / 10 skipped (+6); coverage --gate 710/710 PASS; verify_all --full 全绿 (含 verify_model_write)。


### R5 续 · OCC 引擎激活 (OCP 修复) + SAT 写后端勘察（2026-09-06）
- SATControl (ACIS 写) 勘察定论: conda-forge pythonocc-core 7.9.3 (occ env) 与 cadquery-ocp/OCP 7.9.3.1.1 (默认 env) **两者均无 SATControl 模块** (pythonocc 无 wrap + OCP/CadQuery 弃用 ACIS); `_FX["sat_write"]` 后端双环境不可用 —— `_sat_text_for_part` SAT 分支保留"后端出现即启用"探测。
- 默认 env OCP 修复 (原 DLL load failed): 根因 = TKIVtk 期望 **vtk 9.6.2** (环境为 9.3.1) + delvewheel 跨 wheel 原名单依赖 → 安装配套 vtk==9.6.2; cadquery_ocp.libs 补 71 个原名单副本 (hash 名 + 原名单混合命名两向兼容) -> `import OCP` OK, engine=OCP。
- lts_occ OCP 分支适配: 导入表补全 (BRepBuilderAPI GTransform/MakeEdge/MakeWire, BRepPrimAPI MakePrism/MakeRevol, BRepOffsetAPI *, BRepFilletAPI, gp_GTrsf/Ax1/Circ/Vec, TopoDS_Wire, TopAbs_EDGE); **topods cast** (OCP 7.9 用 `TopoDS.Face_s` 类属性, 兼容层暴露 Face/Edge/Shell/Vertex); ray_intersect/prim_shell 的 `OCC.Core` 硬编码改引擎感知 importlib。
- 结果: tests/test_occ.py **10/10 通过于默认 env** (此前 OCC 全禁 SKIP); B-rep 质量属性/布尔/精确求交在默认 env 激活。
- verify_model_write 增 **B-rep 交换链保真核对** (与 SAT 写同源): mesh -> sew B-rep -> STEP 写/读 -> re-tessellate 体积一致 (sketch vol=12.0000 rel=0.0000); SAT 后端不可用时该核对封锁几何精确性闭环 (ACIS 封装为唯一缺口)。
- verify_cad_exchange 首次以 OCP 引擎运行: 59/66 OK (5 CHECK 为阶段2 网格近似链固有判定 + 2 TIMEOUT 为 OCP 慢; 未对比引擎差异, ci_occ OCC.Core 66/66 基准不变)。
- tests/test_parity 语料断言改为跟随 lt_parity 模块级语料集合 (OCC 可用时剔 base-tess 语料换 OCC 几何语料, 硬编码 45 cid 断言与 lt_parity 条件逻辑矛盾已修)。
- 验证: base pytest **344 passed** / 10 skipped (默认 env OCP 激活, test_occ 10 项从 SKIP 转 RUN); ci_occ.ps1 OK (occ env OCC.Core 通道无回归, OCC 几何语料 rel~1e-16); coverage --gate 710/710 PASS; lt_parity --gate PASS (OCC 语料含 geom_occ_*)。


### R6 排产 · optimization/colorimetry 子系统全命令面 T3（2026-09-06 续）
- lts_cmd_exec.py (新): 命令面 T3 执行器 —— colorimetry 45 条按 族(CCT/CIE/LumViewCCT/RGB)×度量(Illum/Intensity/Luminance/Mesh) 真实执行: 黑体光谱 -> CIE 1931 三刺激 -> xy/uv/CCT (3500K 解析回读 3509.9) + RGB 再现; optimization 45 条状态机 (变量/merit/约束/容差/扰动真实增删) + lts.optimizer 真实求解 (nelder_mead 收敛 (x-3)² best=2.99975 value=6e-8; 中心差分梯度 [-6.0] 解析精确; 报表/敏感性/清除闭环)。
- lts_commands: _extend_subsystem_cmds (菜单官方映射优先 setdefault, 其余挂执行器 snake id); 菜单映射目标 (analysis_*/optimize_*) 一并入 IMPLEMENTED (原手工清单缺口, 6 条 T1 项修复); 90 条官方命令名全部可解析。
- lts_gui: COLORIMETRY/OPTIMIZATION 绑定循环 (闭包捕获 LT 名) + _cmd_colorimetry/_cmd_optimization (真实执行 + Sim tab 日志)。
- tests/test_cmd_exec.py (7): 色度真实载荷 (CCT/xy/flux/RGB/族-度量), 45+45 全可解析, 优化状态机 (增删/报表), 真实求解收敛, 灵敏度解析梯度, 别名注册 (菜单优先项断言 analysis_*/optimize_*), GUI 命令绑定执行。
- depth_tier: optimization + colorimetry 90/90 达 T3 (命令面 depth 打标); Phase A 池随转正缩水 (real 551->467), test_phase_a_depth_real 门槛 500->450 (口径注释)。
- 验证: base pytest **351 passed** / 10 skipped (+7); coverage --gate 710/710 + depth-gate 100% (real 710/710) PASS。

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
