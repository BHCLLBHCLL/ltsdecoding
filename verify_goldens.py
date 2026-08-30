# -*- coding: utf-8 -*-
"""常驻校验: 黄金回归 (确定性管线 vs committed goldens.db).

用法:
  python verify_goldens.py            # 校验 (偏移即 exit 1)
  python verify_goldens.py --seed     # 写回/重建基准
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lts.golden import GoldenStore
from tests.test_golden import golden_suite


def main():
    seed = "--seed" in sys.argv
    store = GoldenStore()
    status = golden_suite(store, seed=seed)
    for s in status:
        print(s)
    drift = [s for s in status if s.startswith("DRIFT")]
    if drift:
        print("\nFAIL: %d drift(s)" % len(drift))
        return 1
    print("\nOK: %d golden checks (%s)" % (
        len(status), "seeded" if seed else "verified"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
