import Foundation

let source = CommandLine.arguments[1]
let destination = CommandLine.arguments[2]
let original = try String(contentsOfFile: source, encoding: .utf8)
guard var converted = original.applyingTransform(StringTransform("Traditional-Simplified"), reverse: false) else {
    fatalError("Traditional-to-simplified conversion failed")
}

// The stock zh_TW translation already contains the same keys as this firmware.
let terminology: [(String, String)] = [
    ("网路", "网络"), ("设定", "设置"), ("装置", "设备"),
    ("韧体", "固件"), ("资讯", "信息"), ("使用者", "用户"),
    ("储存", "保存"), ("连线", "连接"), ("帐号", "账号"),
    ("帐户", "账户"), ("频宽", "带宽"), ("软体", "软件"),
    ("硬体", "硬件"), ("登入", "登录"), ("登出", "退出登录"),
    ("萤幕", "屏幕"), ("介面", "界面"), ("档案", "文件"),
    ("预设", "默认"), ("连结", "链接")
]
for (old, new) in terminology {
    converted = converted.replacingOccurrences(of: old, with: new)
}
try converted.write(toFile: destination, atomically: true, encoding: .utf8)
print("Converted \(original.utf8.count) -> \(converted.utf8.count) UTF-8 bytes")
