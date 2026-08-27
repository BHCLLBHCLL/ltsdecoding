# ltsdecoding → LightTools 100% 对齐开发计划

> 目标：功能完整度与深度均达成与 **LightTools 9.1.0** 100% 对齐
> 差距基线：见 [function_gap_analysis.md](function_gap_analysis.md)（当前综合覆盖度约 25–30%）
> 功能清单基准：[`feature_checklist.json`](feature_checklist.json)（9.1：710 命令 + 290 API + 84 宏 + 378 类）
> **UI 100% 对标规划**：见 [UI_PARITY_PLAN.md](UI_PARITY_PLAN.md)（依据 lt_en_US.dll 资源字符串 / CoreUG 第 3-5 章 / CommandReferenceGuide 命令→调色板路径 / CHM 逆向）
> 制定日期：2026-08-23（8.7 基准）→ **2026-08-24 升级 9.1 基准；M0/M2 已达成**

---

## 进度快照（2026-08-25）

| 里程碑 | 状态 | 证据 |
|---|---|---|
| **M0** checklist 固化 + 语料基建 | **✅ 完成** | `feature_checklist.json`（710+290+84+378）；181 LTS 文件语料 0 错误 0 警告（自 40.2 万警告清零）；22 篇官方 PDF 全文提取 |
| **M2** 几何验证链闭环 | **✅ 完成** | `verify_sat_import.py` 四重全绿：本地自洽 66/66、COM 导入 66/66、重导出 body bbox 66/66（≤1e-6）、loop 级裁剪面 bbox 66/66（**dev=0 逐位一致**）；loop 并集包围盒确认为权威参照 |
| M1 解析层 100% | 🔶 部分 | 378 类可读；对象创建写回/往返字节级一致/Undo 未建 |
| M3 光学属性 100% | 🔶 部分 | PropertyZone 链 205/205 解析并逐面绑定；Fresnel/RT/TIR/Lambert/Mirror/Mechanical 分区物理；`tests/test_zones_receivers.py` 10 项纯物理单测（合成 LTS 全绿） |
| M4/M5 追迹+分析 | 🔶 部分 | 面发射采样（位置+方向 apodizer+光谱+灯功率 lm/ray）；远场接收器 30×60 网格（立体角归一 candela）与 LT 已算网格比对；通量守恒闭合（Beer/TIR 计入吸收）；接收器假彩色/极坐标图 + LT 参考对比 + CSV 导出（matplotlib）；区链支持 setPropertiesName 预设与纹理区域（VariableSpacedTexture/PlanarReferenceSurface，backlight 语料 205 区全部解析） |
| M6 优化器+MACRO+API | ⬜ | 空白 |

关键解锁：**LightTools 9.1.0 license 可用**，COM 自动化（LTLocator/Dispatch + JumpStart ltcom64.jsml）全链路打通，"对表验证"不再被阻塞。

## 一、"100%"的定义与验收度量

100% 不是口号，按以下四条硬性度量执行，每项建立 checklist（以 `feature_checklist.json` 为销项基准）：

1. **解析完整**：所有 LTS 类（9.1 全功能清单 378 类）可读、可写、可往返。
2. **物理正确**：每个光学特性有可验证的物理实现——与 LightTools COM 输出或解析解比对，几何容差 ≤1e-6、通量容差 ≤1%。
3. **界面等价**：LightTools 的每个操作（创建/编辑/仿真/绘图）有对应 UI 入口。
4. **验证闭环**：`verify_sat_import.py` 式自动比对跑通全绿（**已达成**）；`feature_checklist.json` 条目 100% 销项。

---

## 二、分阶段计划

### P0 · 基础设施与功能清单固化 —— **✅ 完成（2026-08-24）**
- ~~从官方文档提取 LightTools 9.1 全功能清单~~ → `feature_checklist.json`（710 命令/290 API/84 宏/378 类，15 子系统分组）
- ~~多样本语料~~ → 181 个 LTS 文件（LT_files + ExamplesLibrary），解析 0 错误 0 警告
- ~~COM 验证链路~~ → `verify_sat_import.py` 双阶段全绿（license 恢复后打通）
- 待办：pytest 黄金文件回归、CI、代码结构重组为 `lts/` 包

### P1 · 解析层 100%
**目标**：任意 LTS 文件无损读写。

| 工作项 | 模块 |
|---|---|
| 类 schema 注册表：类→属性类型/默认值/单位/枚举，替代裸 dict | 新增 `lts/schema.py` |
| 对象**创建**：生成合法 ORACAD 脚本（对齐缩进/命名规则/边连接语句） | 扩展 `lts_model.py` |
| 往返保证：parse→serialize→逐字节一致（黄金测试） | 新增 `tests/` |
| 多版本兼容（v4.x 各版本头差异）、损坏文件恢复、警告分级 | `lts_parser.py` |
| Undo/Redo 事务化编辑栈 | `lts/undo.py` |

**验收**：多样本文件往返字节一致；新建 solid/source/receiver 能被 LightTools 正常打开（COM 链路已可用，随时验证）。

### P2 · 几何内核 100%
**目标**：精确 B-Rep。~~66/66 SAT 全绿~~ **已达成**（本地 + COM 双阶段）。

1. ~~消灭 7 个 WARN~~ → **确认为误报**：body 记录包围盒为未裁剪松散盒，loop 并集才是权威参照；细分器本身精确（dev ≤2e-4）
2. **OCC 精确路径为一等公民**（非可选）：SAT→OCCT 形状精确求值，网格仅用于显示；统一布尔（含变换树）。
3. LightTools 全图元集：块/球/柱/锥/圆环/管/挤出/旋转/放样/薄面/facet 实体 → `lts/geometry/prims.py`（9.1 geometry_modeling 187 条命令为对照面）。
4. 草图特征系统（2D 草图→拉伸/旋转/扫掠）→ `lts/geometry/sketch.py`。
5. CAD 交换：STEP/IGES 导入导出（OCCT 内建）、SAT 精确写出（9.1 data_exchange 40 条命令为对照面）。
6. 几何分析：距离/角度/质量属性/干涉检查。
7. 剖切视图（clip plane）与测量工具入 `lts_vtk.py`。

**验收**：~~verify_sat_import.py 阶段A 66/66 OK；阶段B 与 lt.exe 重导入 bbox/体积差 ≤1e-6~~ **已达成（2026-08-24，loop 级比对 dev=0 逐位一致）**；STEP/IGES 往返与 LightTools 互导对表。

### P3 · 光学属性 100%
**目标**：文件里的 205 个 PropertyZone、198 个 SurfaceInfo、108 个 AmplDirOpticalProperties 变成可计算物理。

- **材料**：折射率模型全套（常数/Schott 色散/Laurent/光学密度）——`lts/optics/materials.py`；吸收/透射光谱（Beer–Lambert）；玻璃目录系统（用户目录格式读写 + refractiveindex.info 公共数据替代授权目录）；GRIN 梯度折射率。
- **表面属性**：镜面反射、Lambertian 散射、菲涅尔损耗、BSDF（含 .bsdf 文件格式）、apodizer（uniform/Lambertian）、dominant ray direction、ray amplitude 规则、property zone 逐面/逐区域指派 → `lts/optics/surface.py`。
- **光谱**：波长系统（559 个 ORAWavelengthObj 语义化）、spectral region、color component、明视觉响应 → `lts/optics/spectrum.py`（9.1 colorimetry 45 条命令为对照面）。
- UI：材料管理器、表面属性编辑器、属性指派对话框（对照 LightTools 界面）。

**验收**：单位测试比对解析解（平板菲涅尔、色散公式采样值）；与 LightTools DbGet 读取值一致（COM 链路已通）。

### P4 · 光源与接收器 100%
- 光源：surface emitter（空间×角度分布、apodizer 加权）、cylinder source、ray aiming（AimSphereDir/ForwardStart）、光谱/偏振态配置 → `lts/optics/sources.py`（9.1 source_modeling 34 条命令为对照面）。
- 接收器：far-field receiver、照度面接收器、intensity data mesh/scatter mesh（解析出网格拓扑）→ `lts/optics/receivers.py`。
- 创建向导 UI + 3D 符号精确化（现有 marker 球升级）。

**验收**：发射采样分布与设定 apodizer 的解析分布 K-S 检验通过；接收器网格数据结构与 LTS 落盘一致。

### P5 · 光线追迹引擎 100%（核心，工作量最大）
**目标**：替代 `ORAForwardIllumSimObj`+`NSRayManager`（9.1 ray_tracing 31 条命令 + simulation_management 22 条命令为对照面）。

架构（新包 `lts/trace/`）：

```
lts/trace/
  scene.py      # 光学场景装配：B-Rep→BVH 加速结构（AABB/Embree 可选）
  raygen.py     # 波长/位置/方向/偏振采样（蒙特卡洛+低差异序列）
  intersect.py  # 相交：BVH 网格法线插值（快路径）+ OCC 精确（校验路径）
  physics.py    # Snell/Fresnel（含镀膜）/TIR/Beer 吸收/BSDF 重要性采样/偏振(Jones)
  engine.py     # 主循环：ray splitting、路径历史、Russian roulette、种子控制
  rayspace.py   # NSRayManager 等价：光线缓冲、过滤、持久化(.ray)
```

- 性能阶梯：numpy 向量化（≥1M rays/min）→ 可选 CUDA 后端（对标 LightTools 速度）。
- **验证金标准**：(a) 解析解用例——理想透镜成像、积分球、TIR 棱镜、菲涅尔平板通量守恒；(b) **COM 对表（链路已通）**：与 LightTools 跑同一模型比对照度图，通量差 ≤1%。
- 仿真控制面板：ray 数/波长/种子/收敛判据，进度与取消。

### P6 · 结果分析与可视化 100%
- `lts/analysis/`：照度图（假彩色+等值线）、坎德拉图（极坐标/笛卡尔）、强度分布、亮度图、通量/效率/均匀性统计（9.1 receiver_analysis 70 条 + imaging_analysis 16 条命令为对照面）。
- 3D 窗格光线显示（按 path/history/波长过滤）——扩展 `lts_vtk.py`。
- 绘图窗（matplotlib）、CSV/位图导出、图例与色标。
- 结果写回 LTS（ORAIntensityDataMeshObj 等）实现文件级往返。

**验收**：rearlighting.lts 全模型跑通，照度/坎德拉图与 LightTools 视觉与数值比对通过（COM 可用）。

### P7 · 优化器 + MACRO 脚本 + API 100%
- **优化**（`lts/optimizer/`）：变量/评价函数/约束、阻尼最小二乘+单纯形+遗传、参数扫描、灵敏度/公差分析（对标 OptimizationManager；9.1 optimization 45 条命令为对照面）。
- **MACRO**（`lts/macro/`）：按 9.1 MACRO 参考实现解释器（词法/语法/命令映射到内部 API，84 宏函数全实现）、宏编辑器、批处理。
- **LTAPI 兼容层**：暴露 COM 接口（pywin32），使既有第三方脚本可驱动本引擎（290 API 函数为对照面）；同时保留现有"驱动 LightTools"方向（`verify_sat_import.py` 的 LTSession 抽象为双向桥）。

**验收**：9.1 MACRO 参考中的命令集 100% 可执行；一个第三方优化宏不改一行跑通。

### P8 · 工程化收口 100%
- 全功能回归矩阵（checklist 逐条销项）、性能基准（追迹吞吐、大模型加载）。
- 打包发行（Windows 安装包）、用户文档、崩溃报告。
- 最终验证：`feature_checklist.json` 全绿 + 双向 COM 比对报告归档。

---

## 三、阶段依赖与推进顺序

```
P0 ──> P1 ──> P2 ──> P3 ──> P4 ──> P5 ──> P6 ──> P8
              │                    │
              └── P2 贯穿 P5-P6（精确求交支撑）  └── P7（依赖 P5/P6 的 API 面）
```

关键路径：**P1→P2→P5→P6**（解析→几何→追迹→分析）。P3/P4 可与 P2 后期并行；P7 在 P5 API 稳定后启动。

## 四、关键风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| ~~LightTools license 不可用~~ | ~~COM 验证被阻塞~~ | **已解除（2026-08-24）**：license 恢复，COM 全链路打通，66/66 对表全绿；保留 verify_sat_import.py 作常驻回归 |
| ACIS 为商业内核 | 精确几何无法直接复用 | OCCT 全面替代（P2 转正）；SAT 读写 OCCT 原生支持 |
| 玻璃目录为授权数据 | 材料库缺口 | 用户目录格式兼容 + refractiveindex.info 公共数据；允许导入厂商 CSV |
| 蒙特卡洛性能对标商业软件 | P5 吞吐量 | numpy 向量化起步 → Embree/CUDA 后端分层优化 |
| 单人代码量（P5+P6 约占一半工作量） | 排期风险 | 引擎与 UI 分层解耦，可先交付 headless 追迹 CLI |
| body 记录包围盒为松散盒（未裁剪曲面范围） | 几何验证误判 | 已确立 loop 并集包围盒为权威参照（写入 verify_sat_import.py） |

## 五、里程碑总览

| 里程碑 | 内容 | 达成标志 | 状态 |
|---|---|---|---|
| M0 | checklist 固化 + 测试基建 | `feature_checklist.json` 覆盖 9.1 全子系统（710+290+84+378） | **✅ 2026-08-24** |
| M1 | 解析层 100% | 黄金文件往返字节一致 | 🔶 |
| M2 | 几何内核 100%（验证链） | verify_sat_import 双阶段 66/66 OK | **✅ 2026-08-24** |
| M2b | 几何内核 100%（精确 B-Rep + CAD 交换） | OCC 精确路径 + STEP/IGES 互导对表 | ⬜ |
| M3 | 光学属性+光源接收器 100% | 物理语义单测全绿（解析解比对） | ⬜ |
| M4 | 光线追迹引擎 100% | 解析解用例全绿；与 LT 通量差 ≤1% | ⬜ |
| M5 | 分析与可视化 100% | rearlighting.lts 全模型跑通出图 | ⬜ |
| M6 | 优化器+MACRO+API 100% | 第三方宏零修改跑通 | ⬜ |
| M7 | 收口 | feature_checklist 全绿 + 比对报告归档 | ⬜ |
