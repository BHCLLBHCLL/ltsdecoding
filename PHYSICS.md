# PHYSICS.md — 物理深度归总

ltsdecoding 的光学/物理引擎扩展，按用户指定顺序逐项实现。每个模块都有独立单测；
引擎集成路径经 `verify_all.py --full`（UI 202/202、16 golden、pipeline、raytrace）校验。

## 模块地图

| 模块 | 领域 | 关键内容 |
|---|---|---|
| `ltsoptics/bsdf.py` | 表面散射 | .bsdf 解析(Lambert/Phong/Tabular) + 重要性采样, 接 surface_event |
| `ltsoptics/textures.py` | 区域纹理 | VariableSpacedTexture/TextureZone, create_texture_zone 写回 |
| `ltsoptics/colorimetry.py` | 色度学 | CIE1931/CCT/CRI/普朗克/主波长/黑体SPD/LuminousEfficacy/色移/MacAdam |
| `ltsoptics/grin.py` | 梯度折射率 | radial/axial/Luneburg + 射线方程追迹 |
| `ltsoptics/volume_scatter.py` | 体散射 | HG 相位/平均自由程/指数自由程事件/波长相关 alpha_at/mu_s_at |
| `ltsoptics/thinfilm.py` | 薄膜 | Abelès 特征矩阵 FilmStack/Layer, 接界面 (coating) |
| `ltsoptics/phosphor.py` | 荧光/磷光 | Stokes 位移/发射波长/寿命延迟/各向同性发射 |
| `ltsoptics/polarization.py` | 偏振 | Jones/Stokes/DOP/s_p 基/emission_jones/accumulate_stokes |
| `ltsoptics/coherence.py` | 相干 | 高斯/模态相位/随机相位(coherence_length)/复场相干/可见度 |
| `ltsoptics/diffraction.py` | 衍射 | 光栅方程/sinc^2 级效率/倏逝截断/角向色散 |

## 引擎集成 (lts/trace/)

- `engine.py`: 工作栈携带 (p,d,w,medium,depth,jones,wl,phase); 体介质(alpha/mu_s/g/depol/qe/tau),
  Beer 吸收, 散射(HG), 荧光重发射(寿命延迟, 退偏 jones=None), 波长相关系数, 偏振输运, 衍射级计数.
- `from_model.py`: scene_from_model(medium/media 查表), rays_from_sources(APodizer/光谱/相干相位),
  stokes_grid/plane_stokes_grid(逐格 S0..S3/DOP/mean_wl), color_shift_grid(xy/CCT/dCCT/duv/MacAdam),
  coherent_grid(复场 |E|^2/可见度/相位), receiver_spectrum, format_trace_report(媒体/发光/色移/相干/衍射).

## 关键公式

- 普朗克黑体: `L(lambda)=c1/(lambda^5)/(exp(c2/(lambdaT))-1)`, Wien 峰 `2.898e6/T` nm.
- 发光效能: `K = 683 * int(V(l)S(l)) / int(S(l))` lm/W; `lamp_power = elec*eff*K`.
- 光栅方程: `m*lambda = d*(sin(th_i)+sin(th_m))`; 级效率 sinc^2(m*duty) 归一.
- 光栅矢量: 切向动量加 `m*G (G=2pi/d)`, 倏逝级 `|k_t|>k0` 截断.
- HG 相位: `p(ct)=(1-g^2)/(4pi(1+g^2-2g*ct)^1.5)`, 均值 cos = g.
- 分层介质 Snell 不变量: `n*sin(theta)=const` (GRIN 轴向).
- 薄膜 Abelès 特征矩阵: 每层 `[[cos d, i sin d/eta],[i eta sin d, cos d]]`, R=|r|^2.
- Jones 相干相位并入: `J_c = J * e^{i*phase}`; 复场 `E_cell = sum sqrt(w)*J_c`;
  `S0_coh=|Es|^2+|Ep|^2`, `visibility=(S0_coh-S0_incoh)/S0_incoh`.
- MacAdam: `steps = sqrt((u'/a)^2+(v'/b)^2)`, N-step 判 `steps<=N`; 25 色表选最近参考色.
- 色移: `dCCT = CCT(cell)-CCT(on-axis)`, `duv = sqrt((u'-u'_ref)^2+(v'-v'_ref)^2)`.
- 荧光寿命: `delay ~ exp(tau)`, 到达时间直方图均值 ~ tau.

## 校验约定

- `python -m pytest tests/ -q`（当前 **238 passed**）
- `python verify_all.py --full`（UI 202/202、16 golden、pipeline、raytrace，退出码 0）
- 黄金回归 SQLite `tests/goldens.db`（16 键）
## Coverage & Depth Alignment (面向 LT 官方面 100%)

四张 LT 官方面全部 surface coverage 100%; key 深度: command 100%, api 100%, macro 100%, class 100%.

度量: python coverage_report.py (四面 coverage+depth+缺口); 门禁: python verify_all.py --full (9 道 coverage/depth gate + pipeline/raytrace).
