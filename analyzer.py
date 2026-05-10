#!/usr/bin/env python3
import os, sys, json, struct, argparse
from datetime import datetime
from collections import defaultdict

try:
    import lief
    lief.logging.disable()
except ImportError:
    print("ERROR: LIEF not installed. Run: pip install lief")
    sys.exit(1)

MAGIC_BYTES = {
    b'MZ': 'PE', b'\x7fELF': 'ELF',
    b'\xfe\xed\xfa\xce': 'MachO32', b'\xce\xfa\xed\xfe': 'MachO32RE',
    b'\xfe\xed\xfa\xcf': 'MachO64', b'\xcf\xfa\xed\xfe': 'MachO64RE',
    b'\xca\xfe\xba\xbe': 'FatBinary', b'\xbe\xba\xfe\xca': 'FatBinaryRE',
}

def detect_format(path):
    try:
        with open(path, 'rb') as f:
            h = f.read(4)
        for m, fmt in MAGIC_BYTES.items():
            if h.startswith(m): return fmt
    except: pass
    return None

def parse_rich_header(data):
    try:
        i = data.find(b'Rich')
        if i == -1: return None
        key = struct.unpack('<I', data[i+4:i+8])[0]
        dans = 0x536e6144 ^ key
        di = data.find(struct.pack('<I', dans))
        if di == -1: return None
        recs = []
        for j in range(di+16, i, 8):
            if j+8 > i: break
            v1 = struct.unpack('<I', data[j:j+4])[0] ^ key
            v2 = struct.unpack('<I', data[j+4:j+8])[0] ^ key
            recs.append({'prod_id': v1>>16, 'build': v1&0xFFFF, 'count': v2})
        return {'xor_key': hex(key), 'records': recs[:5]}
    except: return None

def get_arch(bin):
    try:
        if isinstance(bin, lief.PE.Binary): p = "Win"
        elif isinstance(bin, lief.ELF.Binary): p = "Linux"
        elif isinstance(bin, (lief.MachO.Binary, lief.MachO.FatBinary)): p = "Mac"
        else: return "Unknown"
        obj = bin.at(0) if isinstance(bin, lief.MachO.FatBinary) else bin
        h = obj.abstract.header
        a = str(h.architecture).split('.')[-1].lower()
        b = "64" if h.is_64 else "32"
        am = {"x86_64": "x64", "i386": "x86", "x86": "x86", "aarch64": "arm64", "arm64": "arm64", "arm": "arm"}
        return f"{p}/{am.get(a,a)} ({b}bit)"
    except Exception as e: return f"Error: {type(e).__name__}"

def analyze_pe(bin, data):
    r = {'debug': False, 'debug_type': 'stripped', 'debug_detail': None, 'symtab': False, 'exports': False, 'exports_count': 0, 'extra': {}}
    rich = parse_rich_header(data)
    if rich: r['extra']['rich_header'] = rich
    for dbg in bin.debug:
        if dbg.type == lief.PE.Debug.TYPES.CODEVIEW:
            cv = dbg.code_view if hasattr(dbg, 'code_view') else None
            if cv and cv.filename:
                r['debug'] = True
                r['debug_type'] = 'pdb'
                r['debug_detail'] = cv.filename.split('\\')[-1].split('/')[-1]
                return r
    return r

def analyze_elf(bin):
    r = {'debug': False, 'debug_type': 'stripped', 'debug_detail': None, 'symtab': False, 'exports': False, 'exports_count': 0, 'extra': {}}
    try:
        for n in bin.notes:
            if n.name == "GNU" and "BUILD" in str(n.type).upper():
                r['extra']['build_id'] = bytes(n.description).hex()
                break
    except: pass
    if bin.has_section(".debug_info"):
        r['debug'] = True
        r['debug_type'] = 'dwarf'
        r['debug_detail'] = '.debug_info present'
    if bin.has_section(".symtab"): r['symtab'] = True
    try:
        ds = list(bin.dynamic_symbols)
        if ds: r['exports'], r['exports_count'] = True, len(ds)
    except: pass
    return r

def analyze_macho(bin):
    r = {'debug': False, 'debug_type': 'stripped', 'debug_detail': None, 'symtab': False, 'exports': False, 'exports_count': 0, 'extra': {}}
    obj = bin.at(0) if isinstance(bin, lief.MachO.FatBinary) else bin
    if obj.has_uuid: r['extra']['uuid'] = bytes(obj.uuid.uuid).hex()
    if obj.has_section("__debug_info"):
        r['debug'] = True
        r['debug_type'] = 'dwarf'
        r['debug_detail'] = '__debug_info present'
    if obj.has_symbol_command: r['symtab'] = True
    try:
        ex = list(bin.exported_functions) if isinstance(bin, lief.MachO.FatBinary) else list(obj.exported_functions)
        if ex: r['exports'], r['exports_count'] = True, len(ex)
    except: pass
    return r

def analyze_file(path):
    res = {'file': os.path.basename(path), 'path': path, 'arch': 'Unknown', 'debug': False, 'debug_type': 'stripped', 'debug_detail': None, 'symtab': False, 'exports': False, 'exports_count': 0, 'extra': {}}
    try:
        with open(path, 'rb') as f: data = f.read()
        bin = lief.parse(list(data))
        if not bin: res['arch'] = 'Parse failed'; return res
    except Exception as e:
        res['arch'] = f'Error: read/parse - {type(e).__name__}'
        return res
    try:
        res['arch'] = get_arch(bin)
    except Exception as e:
        res['arch'] = f'Error: arch - {type(e).__name__}'
    try:
        if isinstance(bin, lief.PE.Binary): res.update(analyze_pe(bin, data))
        elif isinstance(bin, lief.ELF.Binary): res.update(analyze_elf(bin))
        elif isinstance(bin, (lief.MachO.Binary, lief.MachO.FatBinary)): res.update(analyze_macho(bin))
    except Exception as e:
        res['extra']['analyze_error'] = f'{type(e).__name__}: {e}'
    return res

def ignore(path, lst):
    pl = path.lower()
    return any(p.lower() in pl for p in lst)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default='manifest_downloads')
    ap.add_argument('--output', default='analysis_results.json')
    ap.add_argument('--ignore', default='ignore.txt')
    a = ap.parse_args()
    if not os.path.isdir(a.dir): print(f"ERROR: {a.dir} not found"); sys.exit(1)
    ign = []
    if os.path.isfile(a.ignore):
        ign = [l.strip() for l in open(a.ignore, encoding='utf-8') if l.strip() and not l.startswith('#')]
    print(f"Scanning: {a.dir}")
    if ign: print(f"Ignoring: {len(ign)} patterns")
    dirs = defaultdict(list)
    total = 0
    for root, ds, fs in os.walk(a.dir):
        ds[:] = [d for d in ds if not ignore(os.path.join(root, d), ign)]
        for f in fs:
            fp = os.path.join(root, f)
            if ignore(fp, ign): continue
            if detect_format(fp):
                dirs[os.path.relpath(root, a.dir)].append(fp)
                total += 1
    print(f"Found {total} binaries in {len(dirs)} dirs")
    result = {}
    for dp, fls in dirs.items():
        res = [analyze_file(p) for p in fls]
        res.sort(key=lambda x: (-int(x['debug']), -int(x['symtab']), -x['exports_count']))
        result[dp] = {'total': len(res), 'files': res}
    out = {'scan_time': datetime.now().isoformat(), 'total_files': total, 'total_directories': len(result), 'directories': result}
    open(a.output, 'w', encoding='utf-8').write(json.dumps(out, indent=2))
    print(f"Results: {a.output}")
    dc = sum(1 for d in result.values() for f in d['files'] if f['debug'])
    sc = sum(1 for d in result.values() for f in d['files'] if f['symtab'])
    ec = sum(1 for d in result.values() for f in d['files'] if f['exports'])
    print(f"Debug: {dc}, Symtab: {sc}, Exports: {ec}")

main()
