r"""test_migrate_dist.py —— migrate_dist 的三组回归测试（Windows 专用）。

为什么每个用例都要配正样本
--------------------------
这些规则全部是"防假绿 / 防假红"性质的：
  * 只判负不判正的探测器，恒红也能显得在工作；
  * 只判正不判负的，恒绿更是毫无价值。
所以每组都同时给出**负样本（必须被抓）**与**正样本（必须被放过）**。

三组内容
--------
  1. 路径前缀替换与跨根 key 折算（大小写不敏感 / 老 manifest 兼容）
  2. junction 判定与差异分类（谁该判负、谁该降级为备注）
  3. 真实文件系统端到端：建 junction → rename → 按新路径定位 → 重定点 →
     回读目标 → 幂等

退出码：0 = 全部通过；1 = 有失败。
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir))
import migrate_dist as M  # noqa: E402

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("  [PASS] %s" % name)
    else:
        FAIL += 1
        print("  [FAIL] %s\n        期望 %r\n        实际 %r" % (name, want, got))


print("== 1. replace_root_prefix（大小写不敏感）==")
# 期望值别用 .replace 现场算——它大小写敏感，会把它自己当成期望值：
# 目标小写 d: 匹配不上大写 D: 的前缀 → 原样返回 → 期望值退化成"没替换"。
# 期望值必须手写常量。
check("小写盘符目标（前缀被换，其余保留原样）", M.replace_root_prefix(
    r"d:\Sandbox\Repo\X\dist\X\App",
    r"D:\Sandbox\Repo\X\dist\X", r"D:\Portapps\X"),
    r"D:\Portapps\X\App")
check("正常大写目标", M.replace_root_prefix(
    r"D:\old\X\App", r"D:\old\X", r"D:\Portapps\X"), r"D:\Portapps\X\App")
check("不匹配返回 None",
      M.replace_root_prefix(r"E:\other\a", r"D:\x", r"D:\y"), None)

print("\n== 2. _jkey 对老 manifest（无 target_rel）能现推 ==")
old = {"root": r"D:\Sandbox\Repo\W\dist\W",
       "junctions": [{"rel": "Data/a", "target": r"D:\Sandbox\Repo\W\dist\W\App\G",
                      "inside": True}]}
new = {"root": r"D:\Portapps\W",
       "junctions": [{"rel": "Data/a", "target": r"D:\Portapps\W\App\G",
                      "inside": True, "target_rel": "App/G"}]}
check("老/新 key 折算后一致",
      M._jkey(old, old["junctions"][0]) == M._jkey(new, new["junctions"][0]),
      True)

print("\n== 3. diff_manifest 能抓到「目标指向旧路径的悬空 junction」==")
pre = {"pkg": "W", "root": r"D:\old\W", "files": {"a": [1, "h"]},
       "junction_count": 1, "total_bytes": 1,
       "junctions": [{"rel": "Data/a", "target": r"D:\old\W\App\G",
                      "inside": True}]}
# 负样本：目标没跟着换根（迁移缺陷的实际后果）
post_bad = {"pkg": "W", "root": r"D:\Portapps\W", "files": {"a": [1, "h"]},
            "junction_count": 1, "total_bytes": 1,
            "junctions": [{"rel": "Data/a", "target": r"D:\old\W\App\G",
                           "inside": False, "target_rel": ""}]}
# 正样本：目标正确重定点
post_ok = {"pkg": "W", "root": r"D:\Portapps\W", "files": {"a": [1, "h"]},
           "junction_count": 1, "total_bytes": 1,
           "junctions": [{"rel": "Data/a", "target": r"D:\Portapps\W\App\G",
                          "inside": True, "target_rel": "App/G"}]}
d_bad = M.diff_manifest(pre, post_bad)
d_ok = M.diff_manifest(pre, post_ok)
check("负样本(目标没换根→inside 变 False)被判 FAIL", len(d_bad) > 0, True)
print("        抓到: %s" % d_bad[:1])
check("★正样本(已正确重定点)判 PASS（证明不是恒红）", d_ok, [])

# 负样本 2：树内 junction 迁移后整个没了 → 必须判负
post_gone = {"pkg": "W", "root": r"D:\Portapps\W", "files": {"a": [1, "h"]},
             "junction_count": 0, "total_bytes": 1, "junctions": []}
check("负样本(树内 junction 迁移后消失)被判 FAIL",
      len(M.diff_manifest(pre, post_gone)) > 0, True)

# 关键反例：树外目标 junction 随冒烟起落，**不应**判负（否则假红 9 包）
pre_out = {"pkg": "W", "root": r"D:\old\W", "files": {"a": [1, "h"]},
           "junction_count": 1, "total_bytes": 1,
           "junctions": [{"rel": "Data/c", "target": r"D:\Sandbox\Ext\W\App",
                          "inside": False}]}
post_out = {"pkg": "W", "root": r"D:\Portapps\W", "files": {"a": [1, "h"]},
            "junction_count": 0, "total_bytes": 1, "junctions": []}
d_out = M.diff_manifest(pre_out, post_out)
check("★树外 junction 被清理 → 不判负（只记备注）", d_out, [])
_, notes_out = M.diff_junctions(pre_out, post_out)
check("  但要在备注里留下痕迹（不静默）", len(notes_out) > 0, True)

print("\n== 3.5 运行期状态分类（不能滑向假绿）==")
check("Data 下的浏览器缓存 → 易变", M.is_volatile("Data/profile/cache2/entries/ABC"), True)
check("Data 下的 prefs.js → 易变", M.is_volatile("Data/profile/prefs.js"), True)
check("★App 下的程序体 → **不**易变（防假绿）",
      M.is_volatile("App/AppInfo/Launcher/Custom.nsh"), False)
check("★Data 下的普通用户文档 → **不**易变（防假绿）",
      M.is_volatile("Data/Documents/我的文档.txt"), False)
check("★Data/notes 下的笔记 → **不**易变（防假绿）",
      M.is_volatile("Data/notes/摘录.txt"), False)
check("目录级规则覆盖未枚举的文件名（防逐个加词条）",
      M.is_volatile("Data/profile/broadcast-listeners.json"), True)
check("Data 下散落缓存 → 易变", M.is_volatile("Data/whatever/cache2/entries/X"), True)
check("★App 下即使叫 cache 也不易变（防假绿）",
      M.is_volatile("App/AppInfo/cache2/x"), False)

h, v = M.classify_diff(["内容/大小不符: Data/profile/prefs.js pre=[1,'a'] post=[2,'b']"])
check("正样本：易变项被降级为备注", (h, len(v)), ([], 1))

h2, v2 = M.classify_diff(
    ["迁移后缺失: Data/profile/cache2/entries/XYZ"])
check("★缺失**永不**降级（哪怕路径是缓存）", (len(h2), len(v2)), (1, 0))

h3, v3 = M.classify_diff(
    ["内容/大小不符: App/AppInfo/appinfo.ini pre=[1,'a'] post=[2,'b']"])
check("★App 下变化不降级", (len(h3), len(v3)), (1, 0))

h4, v4 = M.classify_diff([
    "内容/大小不符: Data/profile/cache2/e1 pre=[1,'a'] post=[2,'b']",
    "内容/大小不符: Data/profile/prefs.js pre=[1,'a'] post=[2,'b']",
    "迁移后缺失: Data/notes.txt",
])
check("混合：易变 2 降级、缺失 1 判负", (len(h4), len(v4)), (1, 2))

print("\n== 4. 真实文件系统：rename 后按新路径能定位到悬空 junction ==")
tmp = tempfile.mkdtemp(prefix="jfix_")
oldroot = os.path.join(tmp, "old")
newroot = os.path.join(tmp, "new")
target = os.path.join(oldroot, "App", "Real")
os.makedirs(target)
os.makedirs(os.path.join(oldroot, "Data"))
with open(os.path.join(target, "z.bin"), "wb") as f:
    f.write(b"x" * 16)
link = os.path.join(oldroot, "Data", "lnk")
cp = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                    capture_output=True, text=True, encoding="gbk",
                    errors="replace")
check("预置 junction 创建成功", cp.returncode, 0)

pre_m = M.build_manifest("T", M.Path(oldroot))
check("预迁移 manifest 认出 1 个包内 junction",
      (pre_m["junction_count"], pre_m["junctions"][0]["inside"]), (1, True))

os.rename(oldroot, newroot)
# 修复前（旧逻辑）：用迁移前路径 + exists()
jp_old = M.Path(oldroot) / pre_m["junctions"][0]["rel"]
check("旧逻辑路径 .exists() 恒 False（缺陷复现）", jp_old.exists(), False)
# 修复后（新逻辑）：用迁移后路径 + is_junction()
jp_new = M.Path(newroot) / pre_m["junctions"][0]["rel"]
check("新逻辑路径 is_junction() 为 True（能定位到）", M.is_junction(jp_new), True)
check("★修复前 .exists() 对新路径也返回 False（目标已悬空）", jp_new.exists(), False)

ok = M.repoint_junction(jp_new, pre_m["junctions"][0]["target"],
                        M.Path(oldroot), M.Path(newroot))
check("重定点成功", ok, True)
check("回读目标正确", M.junction_target(jp_new, M.Path(newroot)).lower(),
      os.path.join(newroot, "App", "Real").lower())
check("★穿透可见目标内容",
      os.path.isfile(os.path.join(str(jp_new), "z.bin")), True)

post_m = M.build_manifest("T", M.Path(newroot))
check("重定点后 manifest 全等（文件+junction）",
      M.diff_manifest(pre_m, post_m), [])

# 幂等：再跑一次不应报错也不应改变
ok2 = M.repoint_junction(jp_new, pre_m["junctions"][0]["target"],
                         M.Path(oldroot), M.Path(newroot))
check("★幂等：重复重定点仍成功", ok2, True)

subprocess.run(["cmd", "/c", "rmdir", str(jp_new)], capture_output=True,
               text=True, encoding="gbk", errors="replace")

print("\n合计: PASS %d / FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
