# M12 — 从官方 1.5.0 构建四个自定义版本（2026-11-03）

## 动机和版本约定

历史上设备的**第一版自定义 1.5.0 已包含 SSH、自有验签公钥，以及部分中文/Web 修改**。但旧的统一 `build.py` 只接受 `1.5.1`、`1.5.2`、`1.5.3`，且将 SSH/验签错误地归在 1.5.1 补丁。为了避免项目版本定义与历史实际行为冲突，现在明确规定：

| 目标版本 | 应用补丁 | 内容 |
|---|---|---|
| 自定义 1.5.0 | `v1_5_0` | 仅持久 owner RSA-2048 公钥验证器、LAN root SSH、CGI 可执行权限、`cr6c → cs6c`、更新清单中排除 `fs-uboot` |
| 自定义 1.5.1 | `v1_5_0 + v1_5_1` | 上述功能 + `zh_CN` r2、CGI 语言注册、Web 语言包 loader |
| 自定义 1.5.2 | `v1_5_0 + v1_5_1 + v1_5_2` | 上述功能 + 端口 1 WAN VLAN 内核修复 |
| 自定义 1.5.3 | 全部四级补丁 | 上述功能 + 简体中文 v3 |

**这是从本次重构开始的标准补丁分类，不是重新给历史已刷写镜像改名。** 新最小化 1.5.0 不包含旧版特制 1.5.0 当时的中文改动，故不能宣称其与历史首次升级镜像字节等价或已完成同样的实机测试。自定义 1.5.0 仍保留原官方的 `soft_ver:1.5.0 Build 20260605 Rel. 41062` 字段，区分镜像身份时必须依据签名密钥、SHA-256 与构建记录，**不能只看 Web 里的版本号**。

## 实现

- `build.py --version` 新增 `1.5.0`，其他三个版本参数与产物命名保持不变。
- `patches/v1_5_0.py`：从旧 `v1_5_1.py` 拆出 owner 公钥验证器、LAN-only Dropbear 启动和两份 SSH `authorized_keys`，明确检查签名公钥为 RSA-2048；仅处理 CGI 可执行权限，便于首次迁移后访问页面。
- `patches/v1_5_1.py`：仅负责中文 r2、Web CGI 语言注册和 chunk 加载路径。两段补丁连续执行时，对原版 RootFS 的修改结果与重构前一致。
- `patches/v1_5_2.py` 不更改内核补丁逻辑，仍强制对照实机验证的内核 SHA-256 `773b66e574a11b4cf6ce8962f83541272df69a0e0cc0084571a104ed5b2400f8`。
- `patches/v1_5_3.py` 保持中文 v3 资源和权限。
- Cloud AES/RSA-PSS 输入生成从历史 `build_owner_153.py` 拆至 `cloud_signing.py`，统一构建器不再依赖旧的“以自定义 1.5.2 为基础”的构建模块。
- `verify_patch_chain.py` 验证各版本 RootFS 的精确差异以及可选的已验证基线对比。

## 实际离线测试

对**确切官方 AX12(RU) V1 1.5.0 原始 BIN**分别执行四个版本：

```sh
python3 build.py --version 1.5.0
python3 build.py --version 1.5.1
python3 build.py --version 1.5.2
python3 build.py --version 1.5.3
```

每项均验签并解密官方原包、重新封装 SquashFS、应用相应补丁、校验分区长度和 `fs-uboot` 更新项缺席，且生成 Cloud AES 密文和 256 字节 RSA-PSS 编码消息。随后**四个版本分别使用一次性测试 RSA-2048 密钥**完整执行本地 `--sign-key`、最终封装、RSA-PSS 验签、AES 解密和 RootFS 回读，全部 **PASS**。测试密钥和签名文件保留在临时目录，未进入仓库。

| 版本 | 新增 RootFS 项 | 修改 RootFS 项 | 封装 RootFS 字节 | 余量（`0xB00000`） |
|---|---:|---:|---:|---:|
| 1.5.0 | 4 | 2 | 11,419,651 | 114,685 |
| 1.5.1 | 5 | 3 | 11,464,707 | 69,629 |
| 1.5.2 | 5 | 3 | 11,464,707 | 69,629 |
| 1.5.3 | 6 | 3 | 11,509,763 | 24,573 |

### 差异回归结果

- `1.5.0 → 1.5.1`：RootFS 仅变化 `www/cgi-bin/luci`、`www/webpages/js/update-store-DnZhtCy9.js.gz`，以及新增 `www/webpages/locale/zh_CN/index-AX12r2.js.gz`。
- `1.5.1 → 1.5.2`：RootFS **0 处**变化；只有内核 WAN 补丁。
- `1.5.2 → 1.5.3`：仅改动 Web loader，并新增 `index-AX12r3.js.gz`；保留原 r2 语言文件。
- 重构后的 `1.5.1` 和 `1.5.2` RootFS 与已有**实机成功 1.5.2 的全部 2,309 项文件/链接**逐项一致（相同字节 SHA-256、链接目标及模式）。
- 1.5.2 的内核校验仍使用实机通过的**固定已知 SHA-256**。

**验收边界：** 当前这次重构没有执行路由器 Flash 写入或启动测试。第一次从旧版原厂 `1.1.22` 升级使用新的、最小化 owner 1.5.0 镜像的实机兼容性尚未单独通过；不能用以上离线构建成功推断这一首次迁移必然安全。历史成功记录仍应以 [M6](M6-first-flash-2026-11-03.md) 和 [FIRST_MIGRATION](FIRST_MIGRATION_1.1.22.md) 为准。

> **Historical result / superseded 1.5.3:** This table records the pre-M13 multilingual 1.5.3. A later 1.5.3 patch keeps only Chinese + English for the router Web UI and changes the RootFS size to **10,121,219 bytes**. The 1.5.0–1.5.2 implementation and regression data here are unchanged. See [M13](M13-1.5.3-zh_CN-en_US-flash-optimization.md).
