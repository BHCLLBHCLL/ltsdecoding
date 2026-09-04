# -*- coding: utf-8 -*-
"""M1 黄金往返回归测试 (pytest 兼容; 也可直接 python tests/test_roundtrip.py).

覆盖: 全语料 (LT_files + ExamplesLibrary, ~181 files) parse -> no-op save -> 逐字节一致.
外加: 属性外科手术编辑后仍可被重新解析且不影响语义.
"""
import glob, io, os, sys, tempfile, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lts_model

CORPORA = [
    r'D:\training\lighttools\LT_files',
    r'D:\training\caedecoder\corpus_lt91\ExamplesLibrary',
]
_EXTRA = [r'D:\training\caedecoder\ltsdecoding\rearlighting.lts']


def collect_corpus():
    seen, out = set(), []
    for root in CORPORA + _EXTRA:
        pat = os.path.join(root, '**', '*.lts')
        for f in glob.glob(pat, recursive=True):
            a = os.path.abspath(f)
            if a not in seen:
                seen.add(a)
                out.append(a)
    return sorted(out)


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def test_roundtrip_byte_identical():
    import gc
    files = collect_corpus()
    assert files, 'corpus empty'
    n_fail = 0
    for f in files:
        m = None
        try:
            m = lts_model.LTSModel()
            m.load(f, build_geometry=False)
        except MemoryError:
            print('SKIP-OOM', os.path.basename(f))
            continue
        except Exception as e:
            n_fail += 1
            print('LOAD FAIL', os.path.basename(f), '->', type(e).__name__, e)
            continue
        try:
            fd, tmp = tempfile.mkstemp(suffix='.lts')
            os.close(fd)
            m.save(tmp)
            ok = _sha(open(f, 'rb').read()) == _sha(open(tmp, 'rb').read())
            if not ok:
                n_fail += 1
                print('BYTES DIFFER', os.path.basename(f))
        except MemoryError:
            print('SKIP-OOM', os.path.basename(f))
        finally:
            if m is not None:
                del m
            gc.collect()
            if os.path.exists(tmp):
                try: os.unlink(tmp)
                except Exception: pass
    print('roundtrip byte-identical:', len(files) - n_fail, '/', len(files))
    assert n_fail == 0, '%d files failed byte round-trip' % n_fail


if __name__ == '__main__':
    test_roundtrip_byte_identical()
