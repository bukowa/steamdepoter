import os
import lief

# Disable LIEF's internal C++ logging to keep the console clean
lief.logging.disable()

class DebugSymbolAnalyzer:
    def __init__(self, ignore_list=None):
        self.available_pdbs = set()
        self.ignore_list = ignore_list or []

    def is_binary(self, file_path):
        """Quick check for magic bytes to avoid parsing non-executables."""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)
            if header.startswith(b'MZ'): return True  # Windows
            if header.startswith(b'\x7fELF'): return True  # Linux
            macho_magics = (
                b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe',
                b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe',
                b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'
            )
            return header in macho_magics  # Mac
        except:
            return False

    def analyze_directory(self, directory_path):
        results = []
        
        # Pre-scan for all available PDB files in the directory
        self.available_pdbs.clear()
        for root, dirs, files in os.walk(directory_path):
            # Skip ignored directories during pre-scan too
            dirs[:] = [d for d in dirs if d not in self.ignore_list]
            for file in files:
                if file in self.ignore_list:
                    continue
                if file.lower().endswith(".pdb"):
                    self.available_pdbs.add(file.lower())

        for root, dirs, files in os.walk(directory_path):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if d not in self.ignore_list]
            
            for file in files:
                if file in self.ignore_list:
                    continue
                full_path = os.path.join(root, file)
                if self.is_binary(full_path):
                    has_debug, details, category, score = self.analyze_file(full_path)
                    results.append({
                        "file": full_path,
                        "filename": file,
                        "has_debug": has_debug,
                        "details": details,
                        "category": category,
                        "score": score
                    })
        return results

    def analyze_file(self, file_path):
        # returns: has_debug (bool), details (str), category (str), score (int)
        # Categories: FULL, PARTIAL, MISSING, STRIPPED, ERROR
        try:
            binary = lief.parse(file_path)
            if binary is None:
                return False, "Parse failed", "ERROR", 0

            # --- WINDOWS (PE) ---
            if isinstance(binary, lief.PE.Binary):
                for dbg in binary.debug:
                    if dbg.type == lief.PE.Debug.TYPES.CODEVIEW:
                        pdb_path = ""
                        if hasattr(dbg, "filename"):
                            pdb_path = dbg.filename
                        elif hasattr(dbg, "code_view") and hasattr(dbg.code_view, "filename"):
                            pdb_path = dbg.code_view.filename

                        if pdb_path:
                            name = pdb_path.split('\\')[-1].split('/')[-1]
                            if name.lower() in self.available_pdbs:
                                return True, f"Found matching PDB: {name}", "FULL", 100
                            else:
                                return False, f"Missing expected PDB: {name}", "MISSING", 40

                return False, "No PDB linked", "STRIPPED", 0

            # --- LINUX (ELF) ---
            elif isinstance(binary, lief.ELF.Binary):
                if binary.has_section(".debug_info"):
                    return True, "Unstripped (DWARF embedded)", "FULL", 100
                if binary.has_section(".symtab"):
                    return True, "Unstripped (Symtab embedded)", "PARTIAL", 80
                if binary.has_section(".gnu_debuglink"):
                    return False, "Separate .debug file linked (Missing)", "MISSING", 40
                return False, "Fully stripped", "STRIPPED", 0

            # --- MACOS (Mach-O) ---
            elif isinstance(binary, (lief.MachO.Binary, lief.MachO.FatBinary)):
                bin_obj = binary.at(0) if isinstance(binary, lief.MachO.FatBinary) else binary
                uuid_str = "None"
                if bin_obj.has_uuid:
                    uuid_str = bytes(bin_obj.uuid.uuid).hex()[:8] + "..."

                if bin_obj.has_section("__debug_info"):
                    return True, f"Unstripped (DWARF) UUID: {uuid_str}", "FULL", 100

                if bin_obj.has_symbol_command:
                    local_syms = [s for s in bin_obj.symbols if not getattr(s, 'is_external', False)]
                    if len(local_syms) > 50:
                        return True, f"Unstripped (Symtab) UUID: {uuid_str}", "PARTIAL", 80

                return False, f"Stripped (dSYM UUID: {uuid_str})", "STRIPPED", 0

            return False, "Unsupported format", "ERROR", 0

        except Exception as e:
            return False, f"Error: {type(e).__name__}", "ERROR", 0


def print_table(title, items, dir_path):
    if not items:
        return
    print(f"\n=== {title} ({len(items)}) ===")
    header = f"{'DETAILS':<40} | {'FILE'}"
    print(header)
    print("-" * 100)
    # Sort items by score descending, then filename
    items.sort(key=lambda x: (-x['score'], x['filename']))
    for res in items:
        rel_path = os.path.relpath(res['file'], dir_path)
        print(f"{res['details']:<40} | {rel_path}")


def main():
    import argparse, sys

    parser = argparse.ArgumentParser(description="Triage Steam binaries for symbols")
    parser.add_argument("--dir", default="manifest_downloads", help="Directory to scan")
    parser.add_argument("--ignore", default="ignore.txt", help="File containing list of directories/files to ignore")
    args = parser.parse_args()

    if not os.path.exists(args.dir):
        print(f"Error: Directory '{args.dir}' not found.")
        return

    ignore_list = []
    if os.path.exists(args.ignore):
        with open(args.ignore, "r", encoding="utf-8") as f:
            ignore_list = [line.strip() for line in f if line.strip()]

    print(f"Scanning: {args.dir}")
    if ignore_list:
        print(f"Ignoring: {', '.join(ignore_list)}")
    print("")

    analyzer = DebugSymbolAnalyzer(ignore_list=ignore_list)
    results = analyzer.analyze_directory(args.dir)

    # Sort results for display and logs: 
    # 1. By score descending (FULL > PARTIAL > MISSING > STRIPPED)
    # 2. By filename (ignoring the manifest ID in the path)
    results.sort(key=lambda x: (-x['score'], x['filename']))

    # Group results
    full_syms = [r for r in results if r['category'] == 'FULL']
    partial_syms = [r for r in results if r['category'] == 'PARTIAL']
    missing_syms = [r for r in results if r['category'] == 'MISSING']
    stripped = [r for r in results if r['category'] == 'STRIPPED']
    errors = [r for r in results if r['category'] == 'ERROR']

    # Print Tables
    print_table("FULL SYMBOLS (DWARF / Matching PDB Found)", full_syms, args.dir)
    print_table("PARTIAL SYMBOLS (Symtab / Local Functions)", partial_syms, args.dir)
    print_table("MISSING SYMBOLS (Expected PDB but not downloaded)", missing_syms, args.dir)
    print_table("FULLY STRIPPED", stripped, args.dir)
    print_table("ERRORS", errors, args.dir)

    # --- Write to Log Files ---
    success_log = os.path.join(args.dir, "symbols_found.log")
    missing_log = os.path.join(args.dir, "symbols_missing.log")
    error_log = os.path.join(args.dir, "analysis_errors.log")

    with open(success_log, "w", encoding="utf-8") as f_succ, \
         open(missing_log, "w", encoding="utf-8") as f_miss, \
         open(error_log, "w", encoding="utf-8") as f_err:
        
        for res in results:
            rel_path = os.path.relpath(res['file'], args.dir)
            line = f"{res['category']:<10} | {res['details']:<40} | {rel_path}\n"
            
            if res['category'] == 'ERROR':
                f_err.write(line)
            elif res['category'] in ('FULL', 'PARTIAL'):
                f_succ.write(line)
            else:
                f_miss.write(line)

    print("\n" + "-" * 100)
    print(f"Log files generated in '{args.dir}':")
    print(f" -> symbols_found.log")
    print(f" -> symbols_missing.log")
    print(f" -> analysis_errors.log")


if __name__ == "__main__":
    main()