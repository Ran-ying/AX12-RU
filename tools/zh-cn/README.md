# Archer AX12(RU) v1 · 简体中文运行时语言包

2026-11-02 实机验证：原厂后台显示“简体中文”，可切换语言；无需重启或刷写。
此处仅记录部署与生成源码，不提交 TP-Link 的原厂翻译文件、完整网站或含设备配置的固件。

## 原理

- 原厂 `/www/webpages/locale/language.js` 已包含 `ZH_CN: "简体中文"`，但不存在 `locale/zh_CN/`。
- `/etc/config/locale` 的 `langinfo` 段决定语言列表，原厂有 `ZH_TW`、没有 `ZH_CN`。
- 根目录是只读 SquashFS；`/etc` 是 RAMFS。不能直接永久覆盖 `/www`。
- 用 Mac 的 Foundation/ICU 转换**设备自身的** `zh_TW/lan.js`（以及非空的 `help.js`），保留 `lan.css`。
- 在 AX12 用一层符号链接目录和 bind mount 添加 `zh_CN`，不再复制整个约 6 MiB 的语言目录，原有语言均保持可用。

## Mac mini：生成并上传

Mac mini 上已配置 `ssh ax12`。

```sh
sh tools/zh-cn/build.sh
tar -C /tmp/ax12-zh-cn -cf - zh_CN |
    ssh ax12 'mkdir -p /tmp/ax12-zh-cn && tar -C /tmp/ax12-zh-cn -xf -'
ssh ax12 sh -s < tools/zh-cn/activate.sh
```

刷新 `http://192.168.0.1`（Mac 上 `Command+Shift+R`），选择“简体中文”。

只读验证：

```sh
ssh ax12 'test -s /www/webpages/locale/zh_CN/lan.js && tail -4 /etc/config/locale'
curl -I http://192.168.0.1/webpages/locale/zh_CN/lan.js
```

## 回滚

本仓库 `activate.sh` 新部署的版本：

```sh
ssh ax12 sh -s < tools/zh-cn/restore.sh
```

**注意：2026-11-02 首次实机成功的手动部署使用了另外一组临时路径**，
`/tmp/ax12-locale-base`、`/tmp/ax12-locale-view` 和
`/tmp/ax12-locale-config.backup`。当前运行中的手动部署不能直接运行上面的通用
`restore.sh`；对应回滚命令是：

```sh
ssh ax12 'umount /www/webpages/locale; umount /tmp/ax12-locale-base; cp /tmp/ax12-locale-config.backup /etc/config/locale'
```

## 限制

- 此版本是**运行时临时补丁**，路由器重启后消失；完整固件构建另行处理。
- 简体翻译是繁简转换加常用术语替换，未经过逐句人工校对。
- 原厂某些语言帮助文件是空文件；保留这一点，不凭空生成内容。
- 避免未经登录直接批量请求 LuCI 接口；初次整体复制语言目录曾导致后台 `Operation failed`，已撤销，轻量符号链接方案由用户确认成功。
