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
