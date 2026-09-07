# ltsdecoding 项目长期知识

## 项目本质
将 LightTools `.lts` 文件 (ORACAD 脚本 + 内嵌 ACIS SAT 几何) 在 Python 端完整可写；目标是让自写出的 `.lts` 被 LT 打开后几何、属性、布尔关系一致。

## 关键架构事实 (2026-09 勘察)
- **LT 原生几何表达是 CSG 参数化**：`ORACSGCuboid/Cylinder/Sphere/ToroidPrimitiveObj` 携带 `setRadius / setWidth / setHeight / setLength / setTaper / setPosition / setOrientation`，**不内嵌 SAT**；LT 打开时由 ACIS 内核按参数重建几何。
- **仅 GenericPrimitiveObj 内嵌 SAT**（导入的 B-rep 自由形状）；66/66 = 全部。
- **Solid 容器链**：`ORAGenericSolidObj` → `getCSGTree → ORACSGTreeObj` + `restoreRootNode → ORACSG*PrimitiveObj | ORACSGUnionOperatorObj | ORACSGDifferenceOperatorObj` + `restoreRegion → ORABoundedRegionObj`。
- **写 .lts 的真正"正确路径"是 CSG 参数化**，不是内嵌 SAT 文本。新建实体应优先走这条。

## 工具链现状
- **ACIS 校验器在本环境不存在（终论 2026-09-06）**：`cadquery-ocp 7.9.3` (`.venv-occ`) 的 `OCP.SATControl` 模块**整体缺失**（Reader 与 Writer 都被剔除）；`pythonocc-core 7.9.3` 同；**系统 `C:\OCCT77\opencascade-7.7.0` 官方完整版也无 SATControl**（src 仅 TKXSBase=STEP）。OCP/OCCT 弃用 ACIS 是 license 原因，不会回退。
- **OCC 可用**：`cadquery-ocp 7.9.3.1.1` 提供 B-rep 布尔、GProp、STEP/IGES 读写；可作 CSG 参数识别与 STEP 交叉验证。
- **自研 ACIS 文本封装**已落地 box 骨架（`lts_sat_writer.write_box_body` ACIS 30.0 布局 + `self_check`），读侧 `sat_tessellator` 66/66 可解析；但缺独立 ACIS 校验器。
- **R5 G4 LT 验收链路已完成并复现**（commit 2fa1aa6 + 82c516e）：`verify_lt_bridge.py` 三链验收（作者化 .lts Open 读回 VOLUME=480 / ImportPlainSAT / ExportPlainSAT3）G4 PASS。**license 正常**（用户双击可打开）；历史"license 失效"误判根因 = COM 直接 Dispatch 启动的嵌入实例 license 初始化异常，GUI 启动+附着即可（见 connect_lt 82c516e）。

## LT COM 关键用法
- 需先装 `pywin32`（`.venv-occ` 用 `uv pip install pywin32 comtypes`）。
- **连接方式（关键）**: 不要用 COM 直接 `Dispatch` 启动嵌入实例 —— 其 license 初始化异常（`\\V3D` 失败 / `DbList` 查不到 / `ImportPlainSAT` 假 stat=0）。**正确做法**: 无现存实例时先 `Popen lt.exe`（GUI，等 25s），再 `Dispatch("LightTools.LTAPI3")` 附着。已封装在 `verify_sat_import.connect_lt`（commit 82c516e）。
- `lt.Cmd("ImportPlainSAT \"D:/path.sat\"")` 带引号；`GetLastMsg(0)` 返回 `(msg, status)`，无参会报错。
- `LicenseIsAvailable()` 返回 0 有误导性，不可作 license 判据（license 正常时也可能返回 0）。
- LT API 70 方法（Cmd/Eval/DbGet/DbSet/DbList/DbKeyDump/ListSize/ListNext/ListDelete/GetMeshData/GetReceiverRayData/Version/LicenseIsAvailable/SetOption 等）；无 ListEntities/CountEntities。
- **ImportPlainSAT 需含 3D 视图 + solid 的宿主模型**（先 Open rearlighting.1.lts + `\\V3D`），空 NewModel 会报 73 "Not expecting"。

## R5 G4 验收状态
- **三链 G4 PASS 已复现**（commit 82c516e）：作者化 .lts Open 读回 VOLUME=480.000038 rel=7.8e-8 / ImportPlainSAT stat=0 / ExportPlainSAT3 stat=0 size=939607。
- `verify_lt_bridge.py` 三链验收；宿主文件 `D:\training\lighttools\LT_files\Tutorial\EllipseStart.1.lts`（作者化宿主）+ `LT rearlighting.1.lts`（导入/导出上下文）。

## 路线
- **P0** `_sat_text_for_part` 改为"形状识别→CSG 参数化写出"。**已落地** (`lts_csg_prim.py` + `_primitive_block_for`)。
- **P1** OCC shape→CSG 参数识别 (cuboid/cylinder/sphere/toroid)。识别双路径（A: 直接 B-rep / B: bbox-only 兜底），14/14 测试 100%。
- **P2** 仅对自由形状自研 SAT 写侧；**已落地 box 骨架** (`lts_sat_writer.write_box_body` + `self_check`)，前置 LT 无头验收链路未通, LT 接受度未断言。

## 关键文件
- `lts_csg_prim.py` **新增** —— 识别 `classify_shape` + 渲染 `render_csg_primitive_block`
- `lts_sat_writer.py` **新增** —— P2 自研 ACIS SAT 文本封装 (box)
- `lts_create.py` —— `render_graph` 新增 `block_provider` 参数（优先级 > `sat_provider`）
- `lts_model.py` —— `_sat_text_for_part` 拆分为 `csg_primitive_for` / `freeform_sat_for` / `_primitive_block_for` / `_shape_for_obj`
- `lts_model.py:193 _sat_text_for_part` —— **旧入口保留兼容**，现由 `_primitive_block_for` 主导
- `lts_parser.py:175 readSATdata 原始模式` + `lts_parser.py:339 extract_sat`
- `sat_tessellator.py` ACIS 文本解析/三角化 (66/66 OK)
- `lts_occ.py:34 _FX` 后端能力字典；`lts_occ.py:354 sat_write` / `lts_occ.py:792 sat_shape_from_text`
- `verify_csg_prim.py` **新增** —— 不依赖 Qt 的回归测试 (63/63 PASS)
- `output/sat/` 66 个 LT 导出 SAT 样本 (语料)
- `DEV_PLAN.md` R5 已有 SATControl 勘察定论 (与本勘察一致)