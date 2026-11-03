# Backend/front-end feature inventory (static firmware inspection)

The 1.5.2 owner RootFS includes controller paths `luci/controller/admin/{wol,yandex_dns,cwmp,wireguardvpn,vpn,pptpd,portal,usbmodem,time_machine}.lua`. Not all controllers are enabled on AX12; shared firmware includes code for other TP-Link devices.

| Candidate | Backend components | Frontend route | State |
|---|---|---|---|
| Wake-on-LAN | `/usr/sbin/wol`, config/wol, `wol.lua` | `wakeOnLan`, `index-C6bH-Pdm.js` | Present statically; inspect runtime feature flags |
| Yandex.DNS | init.d/yandex_dns, `/lib/yandex_dns`, `yandex_dns.lua` | `yandexDns`, `index-XKxj2L0l.js` | Present statically, region gated possible |
| WireGuard | init.d/wireguard, `wireguard.ko`, `wireguardvpn.lua` | `wireguardVpn`, `index-C2jTBjCp.js` | Present statically; type feature flags gate menus |
| VPN client | init.d/vpnc, OpenVPN, lib/vpn | `vpnClient`, `index-CvpqTs2K.js` | Present statically; `supportVpnKillSwitch` exists |
| CWMP/TR-069 | init.d/cwmp, `cwmp.lua` | `cwmp` | Remote administration; do not expose casually |
| Guest Portal | init.d/wportal/wifidog, `portal.lua` | guest network/portal modules | Check region and hardware configuration |
| USB storage/modem/Time Machine | shared controllers and UI modules | shared UI feature strings | AX12 lacks USB port; not usable by simply unhiding menu |

Determine actual support using **read-only** router diagnostics (do not modify profile flags blindly):

```sh
uci -c /etc/profile.d show profile | grep -Ei 'wol|wake|yandex|cwmp|vpn|wireguard|kill_switch|portal|wifidog|mesh|usb|print|time_machine|hidden|support'
```
