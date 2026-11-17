"""Make LiCSBAS13_sb_inv.py (comet-licsar/LiCSBAS @ a145e6c) resumable with small patches.

Upstream, --load_patches only works when the whole cum cube is kept in memory, which
LiCSBAS chooses only if --mem_size > 2 x the cube size (~530 MB for the ascending frame).
Patches of that size ran out of memory in the 7.6 GB Docker VM, so we run with
--mem_size 160, which switches to the "save memory" mode that writes straight into
cum.h5 and cannot be resumed: after an interruption step 13 started again from patch 1
(lost ~11 h on 2026-11-16).

With LICSBAS13_CUM_IN_MEMORY=1 this patch
  1. keeps cum in memory (264 MB) while the patches stay as small as --mem_size says;
  2. resumes robustly: cum.h5 is always created fresh (a hard kill corrupts it); the
     finished rows are the minimum over all per-patch output files, rounded down to a
     patch boundary; partly written files are truncated to that; vintercept is read from
     its own file (upstream reads vel); the gap cube is restored from a new per-patch
     file results/gap_patches;
  3. writes results/cum atomically (temp file + rename).
Without the variable, and without --load_patches, behaviour is unchanged. Inversion
results are identical: only storage and bookkeeping change.

Also fixes get_patchrow in LiCSBAS_tools_lib.py (patches past the last image row).

Usage: python patch_licsbas13.py [path/to/LiCSBAS13_sb_inv.py [path/to/LiCSBAS_tools_lib.py]]
"""
import sys

f = sys.argv[1] if len(sys.argv) > 1 else "/opt/LiCSBAS/bin/LiCSBAS13_sb_inv.py"
src = open(f).read()


def sub(old, new, count=1):
    global src
    n = src.count(old)
    if n != count:
        sys.exit(f"patch_licsbas13.py: expected {count} x {old.strip()[:60]!r}, found {n}; update the patch")
    src = src.replace(old, new)


# 1. in-memory cum, patch size from --mem_size
sub("    if memory_size > cum_size*2:\n",
    "    if memory_size > cum_size*2 or os.environ.get('LICSBAS13_CUM_IN_MEMORY'):\n")
sub("        memory_size_patch = memory_size - cum_size\n",
    "        memory_size_patch = memory_size if os.environ.get('LICSBAS13_CUM_IN_MEMORY') else memory_size - cum_size\n")

# 2a. disable the upstream loader (it reopens cum.h5 r+ and misreads vintercept)
sub("    if load_patches:    \n        if os.path.exists(cumfile):\n",
    "    if load_patches and save_mem:  # in-memory resume: see patch_licsbas13.py block below\n"
    "        if os.path.exists(cumfile):\n")

# 2b. robust resume after cum.h5 and the arrays have been created fresh
sub("    # By here, need to have identified which patchrows have been completed",
    """    if load_patches and not save_mem and os.path.exists(cumfile):
        ## patch_licsbas13.py: resume from the per-patch files
        try:
            def _rows(p, per_row):
                return os.path.getsize(p) // per_row if os.path.exists(p) else 0
            _names = ['vel', 'vintercept', 'resid_rms', 'n_gap', 'n_ifg_noloop', 'maxTlen']
            _files = [os.path.join(resultsdir, x) for x in _names]
            _files += [os.path.join(incdir, '{0}_{1}.inc'.format(imdates[i], imdates[i+1])) for i in range(n_im-1)]
            _files += [os.path.join(resdir, '{0}.res'.format(d)) for d in ifgdates]
            _gapfile = os.path.join(resultsdir, 'gap_patches')
            _n = min([_rows(p, 4*width) for p in _files] + [_rows(_gapfile, (n_im-1)*width)])
            _n = max([0] + [r[1] for r in patchrow if r[1] <= _n])
            if _n > 0:
                _cum = np.fromfile(cumfile, dtype=np.float32).reshape((n_im, length, width))
                cum[:, :_n, :] = _cum[:, :_n, :]
                del _cum
                vel[:_n, :] = np.fromfile(_files[0], dtype=np.float32)[:_n*width].reshape((_n, width))
                vconst[:_n, :] = np.fromfile(_files[1], dtype=np.float32)[:_n*width].reshape((_n, width))
                gap[:, :_n, :] = np.fromfile(_gapfile, dtype=np.int8)[:_n*(n_im-1)*width].reshape((_n, n_im-1, width)).transpose(1, 0, 2)
                for p in _files:
                    os.truncate(p, _n*4*width)
                os.truncate(_gapfile, _n*(n_im-1)*width)
            processed_rows = _n
            print('Processed patches loaded - {} rows completed (patch_licsbas13)'.format(processed_rows), flush=True)
        except Exception as e:
            print('Could not resume ({}). Restarting inversion'.format(e), flush=True)
            processed_rows = 0

    # By here, need to have identified which patchrows have been completed""")

# 2c. per-patch gap file (row-major, so finished rows are a prefix)
sub("""            for i in range(len(names)):
                file = os.path.join(resultsdir, names[i])
                with open(file, openmode) as f:
                    data[i].tofile(f)
""", """            for i in range(len(names)):
                file = os.path.join(resultsdir, names[i])
                with open(file, openmode) as f:
                    data[i].tofile(f)

            if store_patches and not save_mem:  # patch_licsbas13.py
                with open(os.path.join(resultsdir, 'gap_patches'), openmode) as f:
                    gap_patch.reshape((n_im-1, lengththis, width)).transpose(1, 0, 2).tofile(f)
""")

# 3. atomic results/cum
sub("""            if store_patches and not save_mem:
                with open(cumfile, 'w') as f:
                    cum.tofile(f)
""", """            if store_patches and not save_mem:
                with open(cumfile + '.tmp', 'w') as f:
                    cum.tofile(f)
                os.replace(cumfile + '.tmp', cumfile)
""")
sub("""        if store_patches:
            os.remove(cumfile)
""", """        if store_patches:
            os.remove(cumfile)
            if os.path.exists(os.path.join(resultsdir, 'gap_patches')):
                os.remove(os.path.join(resultsdir, 'gap_patches'))
""")

open(f, "w").write(src)
print(f"patched {f}: resumable step 13 with LICSBAS13_CUM_IN_MEMORY=1")

# 4. tools_lib.get_patchrow: with ceil(length/n_patch) rows per patch, n_patch patches can
#    overshoot the image (301 rows, 40 patches of 8 -> [296,304], [304,312], [312,301]),
#    and step 13 fails on the first patch past the last row. Use only as many patches as needed.
f = f.replace("/bin/LiCSBAS13_sb_inv.py", "/LiCSBAS_lib/LiCSBAS_tools_lib.py") if len(sys.argv) < 3 else sys.argv[2]
src = open(f).read()
sub("    ### Devide only row direction\n",
    "    n_patch = int(np.ceil(length/int(np.ceil(length/n_patch))))  # patch_licsbas13.py: no rows past the image\n"
    "    ### Devide only row direction\n")
open(f, "w").write(src)
print(f"patched {f}: get_patchrow without patches past the last row")
