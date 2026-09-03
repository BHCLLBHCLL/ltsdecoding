# -*- coding: utf-8 -*-
"""一键常驻校验: 依次跑 verify_ui / verify_goldens / (可选) verify_pipeline / verify_raytrace."""
import subprocess, sys, os
# Windows 控制台默认 cp1252 无法编码中文 -> 强制 UTF-8 (errors=replace)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
root = os.path.dirname(os.path.abspath(__file__))


def run(name, args=None):
    r = subprocess.run([sys.executable, os.path.join(root, name)] + (args or []),
                       cwd=root)
    return r.returncode


def main():
    codes = []
    # Phase 0: coverage gate — LT 命令面覆盖率下限 (随 Phase A 提升而提高)
    print("== coverage_report.py ==")
    codes.append(run("coverage_report.py", ["--gate", os.environ.get("LT_COV_GATE", "100.0")]))
    codes.append(run("coverage_report.py", ["--depth-gate", os.environ.get("LT_DEPTH_GATE", "100.0")]))
    codes.append(run("coverage_report.py", ["--api-gate", os.environ.get("LT_API_GATE", "100.0")]))
    codes.append(run("coverage_report.py", ["--api-depth-gate", os.environ.get("LT_API_DEPTH_GATE", "100.0")]))
    for name, args in (("verify_ui.py", None), ("verify_goldens.py", None)):
        print("== %s ==" % name)
        codes.append(run(name, args))
    # 重任务默认跳过; --full 才跑
    if "--full" in sys.argv:
        for name, args in (("verify_pipeline.py", None),
                           ("verify_raytrace.py", None)):
            print("== %s ==" % name)
            codes.append(run(name, args))
    else:
        print("(重任务 verify_pipeline/verify_raytrace 用 --full 运行)")
    return max(codes, default=0)


if __name__ == "__main__":
    sys.exit(main())
