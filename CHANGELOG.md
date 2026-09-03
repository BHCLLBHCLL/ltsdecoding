# CHANGELOG

本日志按里程碑记录 ltsdecoding 的演进。**Physics Depth** 阶段为「物理深度」系列
(按用户指定顺序逐项实现并逐项提交 + 全量回归 238+).

## Physics Depth 里程碑（当前阶段，全绿）

| 提交 | 主题 |
|---|---|
| 3510d7d | 7 项物理深度: BSDF/区域纹理/色度学/GRIN/体散射/磷光-薄膜/偏振 |
| 3365d70 | 平面接收器 Stokes 积累 + GUI 视图 + verify_all 编码修复 |
| bff37d1 | 体积介质/体散射接入 scene_from_model 的 medium 查表 |
| 957fa10 | 散射介质偏振输运/退偏 + 媒体摘要报表 |
| 80f4f44 | 光谱采样扩展 + 荧光/磷光介质发光 (Stokes 位移/寿命/量子效率) |
| 3624d04 | 媒体/散射 GUI 面板 + Stokes 接收器 DOP/椭圆度 (Poincare) 图 |
| 6df97d3 | 跨波长多色聚合 (波长->RGB/色图/接收器光谱) + GUI Color 面板 |
| f896dcd | 荧光入接收器 (波长记录/色图) + 磷光表面分支 + 色散感知界面 n(lambda) |
| 202bd5d | 接收器色度/CCT 报表 + 退偏磷光发射 + tabbed Stokes 对话框 |
| 3fb005a | zone 色散传播 + 材料表/目录 n@450/550/650 + 荧光能量守恒交叉核对 |
| 933766c | 统一发光守恒子块 (介质/表面荧光分账 vs 吸收/逃逸) |
| c8d2f23 | 发光守恒 GUI 面板 (Media & Scatter 的 Luminescence 页) |
| c8cda78 | 荧光寿命/时序 (指数衰减->到达时间分布) + 波长相关系数 (幂律/实测表) |
| 5f0e2bd | 热辐射/电致发光源 (黑体 SPB + 阴极/电流效率) |
| c0c0fd3 | 黑体/电致发光映射到 GUI 源向导 (温度滑杆/电流/电压/效率/发射谱预览) |
| 3984a3e | Luminous Efficacy (lm/W) 光谱换算: lamp_power = elec*eff*K |
| e337ddd | 光谱角向发射调制 (离轴色温偏移) + GUI 向导字段 |
| 7b92d54 | 接收器色移 map (CIE xy + dCCT + duv) 呈现离轴色偏 |
| c5fc1f4 | MacAdam 椭圆 / N-step (SDCM) 容差判定 (色移图轮廓) |
| 6307571 | MacAdam 25 色实测表 + 按参考色选取 (xy->uv Jacobian) |
| fcc4c75 | 衍射光栅角向光谱 (光栅方程/sinc^2 级效率/倏逝截断) |
| 58a4cbc | 相干/多模光源相位 (相干采样 -> 部分相干) |
| 9993f80 | 复振幅 Jones 驱动的相干追迹 (相位并入 Jones) |
| 91a159f | 新物理项统一挂到 GUI 面板/报表 (相干/可见度/衍射级/相位图) |

## 既有里程碑（早期）

- M-UI1..M-UI5: 4 窗格 / 命令注册表 / 命令面板对齐 / Insert 向导 / 配置引擎 / 特殊视图
- 命令实现批次 (Analyze/view/file/edit/tools/profile/aim/help)
- P7 优化器 / P7 MACRO 解释器 / P5 序列成像
- 最终命令全覆盖 202/202
- 工程收尾: SQLite 黄金回归 + 常驻 verify_*.py
## Coverage & Depth Alignment (面向 LT 官方面 100%)

前置: Phase 0 覆盖度仪表; 之后逐面对齐 (coverage=表面可表示, depth=真实绑定).

| 阶段 | 面 | total | coverage | depth(real) |
|---|---|---|---|---|
| Phase A | command | 710 | 100% | 100% |
| Phase B | api | 290 | 100% | 100% |
| Phase C | macro | 84 | 100% | 49 = 58.33% |
| Phase D | class | 378 | 100% | 378 = 100% |

### 工具
- coverage_report.py: 四张面覆盖率+深度+缺口; --gate/--depth-gate/--api-gate/--api-depth-gate/--macro-gate/--macro-depth-gate/--class-gate/--class-depth-gate.
- lts_phase_a.py: 命令面自动登记+真实/骨架 handler (LT_ALIASES+GUI bus).
- lts_api.py: API 面绑定层 (290, 真实/validated).
- lts/macro/macro.py: MACRO 解释器函数表+known_functions/depth_stats.
- lts_class.py + lts/lts_bind.py: LTS 类面绑定 (族分类).
- verify_all.py: 9 道门禁 (command/api/macro/class 的 coverage+depth + --full 的 pipeline/raytrace).

### 关键提交
- Phase 0: 74a5f00; Phase A: 81b7618/913ecf0/58837e2/7475c4e; Phase B: 1f3f8f0/fb39a7b/d2e2cad; Phase C: 342ac10; Phase D: 92a6af2/ff8ec60/e0b7c92.
