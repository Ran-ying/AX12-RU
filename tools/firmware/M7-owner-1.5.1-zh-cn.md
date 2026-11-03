# M7 — AX12 RU 自签名固件 1.5.1-owner / 简体中文修复（2026-11-03）

## 目标与状态

以实机 M6 成功引导的 owner-signed 1.5.0 `cs6c` 为基线。**下一版离线候选已构建、尚未正式 owner 私钥签名，不能刷写**。没有接触路由器 Flash，也没有重启设备。

## 修改

1. `/www/cgi-bin/luci` 从 0700 改为 0755。M6 已经通过临时 bind mount 在实机验证此修改能消除纯文本 403 并恢复网页。
2. 新增完整 `www/webpages/locale/zh_CN/index-AX12r2.js.gz`，基于官方该版完整繁体中文 `zh_TW` 模块进行 OpenCC t2s 简体转换；保留原有翻译键、占位符和 JS 模块接口。此资源为自动转码，专业术语尚未逐条人工审校。
3. 补充 `update-store-DnZhtCy9.js.gz` 中 `zh_CN` 的动态导入映射，并在后端语言列表无 `zh_CN` 时于前端提供“简体中文”选项。原 LuCI locale 处理逻辑已确认：`force=false` 时允许保存 locale，读取时检查 `/www/webpages/locale/<locale>/index*.js.gz` 的存在。
4. Soft-version 字段调为自定义 `1.5.1 Build 20261103 Rel. 41063`（**非 TP-Link 官方发布版本**）；原 Bootloader 和 cs6c 内核不变。未来 RootFS 构建同时打入 CGI 权限及中文修复。

## VPS 构建目录（未签名）

`/var/lib/linux-panel/ax12-firmware-work/owner-2026-r2/`

- `rootfs.sqfs`：xz、block 262144、root UID/GID。
- `rootfs.sealed`：11,464,707 字节，SHA-256 `c9ece0ffa08493b9f5361745214f02d4626e96a130883aa6584711959e0270e8`。
- 真实 mtd2 RootFS 最大 `0xb00000`，预留 69,629 字节；没有扩张到 ART。
- `UNSIGNED-AX12-1.5.1-owner.bin`：15,416,028 字节；SHA-256 `4e52ff93fc5af42a80eada09312b62ceaf5a3cecf0afc6c1d8c0461356d83e94`。
- `em-for-mac.bin`：256 字节待 RSA 私钥原语签名的 PSS encoded message，SHA-256 `7819fa09adcdfa5f05e38b84b194c32d09a0cfe70c9bd311cf3ab06440d67b0f`。

## 离线检查

- 原版签名基线通过 owner 公钥验签后解密。
- 新 RootFS 的 `unsquashfs -ll` 确认 CGI 权限为 `rwxr-xr-x`。
- 两个被修改/新增的 JS 通过 `node --check`。
- `validate_owner_r2_unsigned.py` 通过：核对 PSS encoded message 与密文 digest、从 encoded message 恢复 AES 参数后解密整包、逐字节核对除签名槽以外所有 Cloud 明文、RootFS、无 fs-uboot 更新条目与自定义 1.5.1 版本。
- **尚未执行正式 owner RSA 签名、最终签名验签、新版实机升级器校验、QEMU 写入轨迹或第二次实机刷写。**

## 本地签名要求

Mac mini 中的 `~/.ssh/ax12_owner_2026` 是唯一 owner 私钥。任何情况下都不向 VPS 传输该私钥。

1. 把 `em-for-mac.bin` 送到 Mac，使用 `sign_owner_em.py` 与上述私钥生成 256 字节 big-endian 签名。
2. 将**仅该签名**送回 VPS。
3. 用 `finalize_owner_cloud.py` 注入签名（写入 Cloud 小端签名槽），再独立验 owner 公钥签名、AES 解密和 manifest/RootFS。
4. 最终校验通过后，再考虑实机 `-c` 只读验收；第二次写入必须另行授权。

已保留 M6 可用 SSH、Web、现有设备配置及老版本固件备份。


## 追加发现与最终候选修订（r3）

在使用 Mac mini 私钥第一次完成 r2 RSA 签名（成功并验证）后，离线检查进一步发现 `locale.lua` 的 `set_sysinfo` LuaJIT 字节码里有独立语言白名单，其中存在 `zh_TW`、但不存在 `zh_CN`。**因此第一次签好的 r2 不满足中文切换要求，不可刷写**，已在 VPS 改名为 `owner-2026-r2/SUPERSEDED-DO-NOT-FLASH.bin`。该旧包 SHA-256 为 `99f651aa92b9220a1dd3d1d2be7d54cac4ce4f362eb016688699a31a8eb03069`。

最终代码修订在 CGI 启动时加载本版本的 `luci.controller.locale`，使用已经在同款 MIPS LuaJIT 模块离线确认的 `set_sysinfo` 第 4 个 upvalue 白名单表，令 `zh_CN` 允许的索引复用 `zh_TW`。维持原有其他语言与认证逻辑。此实现依赖 1.5.0 中现有 LuCI 字节码布局，未来升级必须重新检查。

**最新完整候选（r3，未正式签名，NO FLASH）：**

- 目录：`/var/lib/linux-panel/ax12-firmware-work/owner-2026-r3/`。
- SquashFS 经 `mksquashfs` 重新打包；LuCI CGI 权限为 0755，新的 CGI 脚本使用同版本原生 LuaJIT 编译器 `-b` 通过语法检查。
- `rootfs.sealed` 11,464,707 字节；SHA-256 `39cbd4ad9e1a6fd360363dc083204c22c368b17a1a85a4fdc671f2209d5c2a6c`；真实 mtd2 仍有 69,629 字节余量。
- `unsigned.bin` 15,416,028 字节；SHA-256 `2d2d3f77ea3710b96758961e4ad140e09d966c250edf43d6fa9ec6d39857aea8`。
- `em.bin` 256 字节；SHA-256 `e8547edfabc1e8c849230024599e4cae90306bf58bfa752e4e8b72e76cb4ede0`。**不可复用 r2 的签名，必须给此新 EM 单独签名**。
- 新版未签名容器通过 `validate_r2.py` 的 PSS encoded message、AES 全载荷逐字节、版本元数据和无 Bootloader 更新条目校验。
- `em.bin` 已复制到 Mac mini `/tmp/ax12-1.5.1-final-em.bin`。Mac 上 owner 签名私钥仍留在 `~/.ssh/ax12_owner_2026`。
- r3 正式签名及最终验签**尚未完成**。签名远程命令被安全检查阻止，不能将 r2 已签名结果视为 r3 的结果；不得使用 r2 固件代替。实机刷写也未进行。

将 r3 的 256 字节 encoded message 在 Mac 通过 `openssl pkeyutl -sign -pkeyopt rsa_padding_mode:none -inkey ~/.ssh/ax12_owner_2026 -in /tmp/ax12-1.5.1-final-em.bin -out sig-owner-r3.big` 签署后，仅传回 `sig-owner-r3.big`，通过 `finalize_owner_cloud.py` 正式封装并校验。执行真正的升级写入仍需另行确认。


## macOS LibreSSL 签名命令更正

macOS 系统自带 LibreSSL 3.3.6 的 `openssl pkeyutl -sign -pkeyopt rsa_padding_mode:none` 会拒绝 256 字节 PSS encoded message，报 `non-raw input data length 256 is too long - max supported hashed size is 64`。正确的原始 RSA 私钥运算应使用：

```bash
openssl rsautl -sign -raw \
  -inkey ~/.ssh/ax12_owner_2026 \
  -in /tmp/ax12-1.5.1-final-em.bin \
  -out ~/Desktop/ax12-1.5.1-r3.sig
wc -c ~/Desktop/ax12-1.5.1-r3.sig
```

签名应为 256 字节，之后必须在 VPS 通过 owner 公钥校验 RSA 原语结果与 r3 的 `em.bin` 完全一致，再完成 Cloud 封装和校验。**此记录不代表该签名已生成。**
