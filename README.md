# UltraHOFs · 知声无界 / Ultra-X

**氢键有机框架（HOF）设计平台** — 从分子到晶体：分子生成与可解释评分、拓扑驱动的周期结构构建、
MACE-OFF24 结构优化，以及带完整文献引用的实验 HOF 数据库。

**Hydrogen-bonded organic framework design platform** — explainable tecton generation and scoring,
topology-driven periodic structure building, MACE-OFF24 relaxation, and an experimental HOF database with
traceable citations.

---

## 功能 / Features

| 模块 Module | 内容 |
|---|---|
| 实验 HOF 数据库 | 632 个实验晶相（HOFSyn v2，CC BY 4.0）；每条含组分 SMILES、CCDC 编号、DOI 引用（Crossref 补全，可导出 BibTeX/RIS）、合成条件、去客体框架孔隙（Zeo++）、氢键网络维度，以及五项“是/否/未知”证据标签；支持名称、DOI、子结构和相似性检索；提供审核队列 |
| 分子评估 | 11 项可解释的 HOF 倾向评分（不是概率），并给出实验先例（同一分子 / 不同质子化态 / 同骨架 / 相似分子 + 引用）和拓扑推荐 |
| 分子生成 | 核心(24) × 连接臂(8) × 合成子(17)，对称取代，并提示合成路线；可复现 TMA、ATC、TTBI、MTB、H4TBAPy、TCPP 等经典构筑单元 |
| 双组分 | 脒鎓/胍鎓/铵 × 羧酸根/磺酸根/膦酸根，给出电荷平衡配比、互补性和拓扑兼容性 |
| 结构构建 | 2,271 个 RCSR 3D 网 + 4 个 2D 层网；连接点放在合成子配对中心，节点位置与晶胞联合最小二乘优化，再做合成子扭转对齐；推荐拓扑经过实际嵌入检查（合成子能否正对、连接点能否闭合、分子是否重叠）；支持层堆积（AA/AB/ABC/滑移）、n 重穿插、二部/双节点双组分；可导出 CIF/POSCAR/XYZ/LAMMPS/PDB |
| 结构优化 | MACE-OFF24 两阶段（先原子后晶胞），作为后台任务运行；默认 CPU；带坍塌标记和轨迹；Slurm 执行器已就绪（`-A m4517`） |
| 账号与项目 | JWT 认证，角色分 admin / curator / member，数据带 org_id（为 SaaS 预留）；项目收藏、任务中心 |
| 界面 | React + Ant Design，中英双语；朱雀仿宋 + Cormorant Garamond，字体自托管；Ketcher 分子绘制；3Dmol.js 三维显示（含晶胞、超胞、氢键） |

## 快速开始（NERSC 登录节点）/ Quick start on NERSC

```bash
# 1. 环境（已创建于 /global/cfs/cdirs/m4517/jiaao/envs/ultrahofs）
module load conda
mamba env create -p /global/cfs/cdirs/m4517/jiaao/envs/ultrahofs -f environment.yml   # 首次
conda activate /global/cfs/cdirs/m4517/jiaao/envs/ultrahofs
pip install -e "./backend[dev,relax]"
(cd frontend && npm ci && npm run fonts && npm run build)

# 2. 启动（只监听 127.0.0.1）
scripts/dev.sh prod     # API + 已构建界面 → http://127.0.0.1:8000 ，并启动任务 worker
scripts/dev.sh          # 开发模式：Vite 热更新 → http://127.0.0.1:5173

# 3. 在本地电脑访问：VS Code Remote-SSH 的 Ports 面板会自动转发端口；或手动转发
ssh -L 8000:127.0.0.1:8000 <user>@perlmutter.nersc.gov
```

初始管理员账号为 `admin`，密码保存在 `var/initial_admin_password.txt`（权限 600，不会提交到 git），首次登录后请修改。

### 命令行 / CLI

```bash
ultrahofs create-user --username alice --role curator      # 角色：admin | curator | member
ultrahofs ingest-hofsyn [--limit N] [--offline] [--no-pores]  # 导入 HOFSyn，可重复运行
ultrahofs score-molecules --experimental [--force]          # 计算 / 刷新评分
ultrahofs worker                                             # 后台任务进程
ultrahofs run-job <id>                                       # 在 Slurm 批处理作业中执行
python scripts/build_net_cache.py                            # 由 PORMAKE 重建 RCSR 网络缓存
python scripts/make_brand.py                                 # 重新生成 logo 与字标 SVG
python scripts/validate_scoring.py && python scripts/validate_builder.py
```

## 架构 / Architecture

```
frontend/ (React 19 + TS + Vite + antd 6 + Ketcher + 3Dmol.js + ECharts, i18n zh-CN/en-US)
   │ /api/v1
backend/ultrahofs/
   api/        FastAPI routers (auth, hofs, design, build, meta)
   chem/       standardise · synthons (SMARTS) · descriptors · conformers/X points · scoring · enumerate · pairs
   crystal/    nets (RCSR cache + 2D) · building blocks · assembler · QC · exporters
   analysis/   periodic bonding · H-bond network dimensionality · Zeo++ · CIF→molecules (gemmi, valence matching)
   relax/      MACE-OFF24 engine          jobs/  DB queue · worker · Local/Slurm executors
   ingest/     HOFSyn · RTF bibliography · Crossref · OPSIN/PubChem · optional CSD connector
var/  (gitignored) SQLite DB · CIFs · structures · jobs · models     data/raw/ (gitignored) source datasets
```

数据库：开发环境使用 SQLite，生产环境使用 PostgreSQL（见 `deploy/docker-compose.yml`）。结构迁移由 Alembic 管理（`backend/alembic`）。

## 验证 / Validation

- **pytest**：48 项测试，另有 1 项慢速 MACE 测试（`pytest -m slow`）。覆盖合成子识别、评分排序、枚举、网络、组装器（含扭转对齐和嵌入检查排序）、导出往返、CIF→SMILES、Zeo++ 和 API。
- **Playwright 端到端**：7 个流程全部通过，依次为登录 → 统计 → 数据库与引用 → 三维 → 评估 → 生成 → 构建与导出 → MACE 优化任务 → 双组分 → 中英切换。运行方式：`cd frontend && UH_E2E_PASSWORD=… npx playwright test`。
- **评分**（`docs/validation/scoring.md`）：在设计适用范围（含经典氢键合成子的分子）内，实验构筑单元相对背景分子的 ROC-AUC 为 0.87，全部分子为 0.73。HOFSyn 中约 28% 的“HOF”不含经典 N–H/O–H 合成子。
- **构建器**（`docs/validation/builder.md`）：
  - TMA 的 hcb 层晶格为 16.7–17.0 Å，实验 2D 蜂窝为约 1.66–1.7 nm；
  - ATC 的 dia 网络（1 重和 2 重穿插）连接点零偏差，氢键网络为 3D；
  - 80 个实验构筑单元在首选网上用默认参数构建，79 个成功；未优化结构的质量检查为通过 56、警告 17、失败 6；
  - 若只按方向匹配排序，结果为通过 48、警告 16、失败 15；
  - 73/79 的氢键网络维度达到网络维度。

## 数据与许可 / Data & licences

- HOFSyn（Wang, 2025，figshare，**CC BY 4.0**）：元数据与结构在 CC BY 4.0 下使用，已署名；晶体结构以 CCDC 编号引用，CSD 来源的数据按运营方的 CSD 许可使用。
- RCSR 拓扑数据通过 PORMAKE（MIT）获取，需引用 O'Keeffe 等人，*Acc. Chem. Res.* 2008。Zeo++ 为修改版 BSD 许可。RDKit、pymatgen、gemmi、3Dmol.js、Ketcher 和 ECharts 均为宽松许可。
- **MACE-OFF24 采用学术软件许可（ASL）**，商用需获得作者授权。优化引擎是可插拔的，生产环境可以替换。
- 字体：朱雀仿宋、Cormorant Garamond、Inter、JetBrains Mono、Noto Sans SC，均为 SIL OFL 1.1，并且都是自托管。
- HOF 倾向评分是基于文献设计规则的排序分数，**不是形成概率**；平台生成的结构均为**假想结构**。

## 路线图 / Roadmap (v2)

- AI 生成模型（强化学习或扩散模型）
- 晶体结构预测与致密相能量比较（成孔代价）
- GCMC 吸附
- Slurm 生产化部署
- SaaS 计费与配额
- LLM 辅助文献抽取
- 导入 HypoHOFs 假想结构参照库
- CrystalNets.jl 自动识别拓扑
- 无序结构更完善的解析
