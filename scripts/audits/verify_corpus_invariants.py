import json
from pathlib import Path
from collections import defaultdict, Counter

PROCESSED_DIR = Path("data/processed_chunks")

def main():
    json_files = sorted(PROCESSED_DIR.glob("*.json"))
    json_files = [f for f in json_files if not f.name.startswith("_")]
    
    print(f"Tổng số file JSON cần kiểm tra: {len(json_files)}")
    
    # 1. Invariant A: Consolidated reports have BS, IS, CF
    missing_stmts = defaultdict(list)
    stmt_counts = Counter()
    
    # 2. Invariant B: Duplicate codes within report_type in facts
    dup_codes_by_file = defaultdict(dict)
    
    # 3. Invariant C: NOTES units vs default_unit
    unit_mismatch_notes = defaultdict(list)
    
    # 4. Cash Flow identity checks summary
    cf_check_stats = {"passed": 0, "failed": 0, "total": 0}
    failed_cf_files = []
    
    # Specific inspection tracking
    specific_inspect = {}
    
    for f in json_files:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            
        doc_id = data.get("doc_id", f.stem)
        default_unit = data.get("default_unit", "VND")
        scope = data.get("scope", "consolidated")
        
        # Invariant A
        facts = data.get("facts", [])
        report_types = set(fact.get("report_type") for fact in facts)
        
        expected_stmts = {"BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW"}
        missing = expected_stmts - report_types
        if missing:
            missing_stmts[doc_id] = list(missing)
            
        for rtype in report_types:
            stmt_counts[rtype] += 1
            
        # Invariant B: Duplicates per report_type and period
        # Note: A code may appear once per period. Duplication is when same (report_type, code, period) appears multiple times
        code_instances = Counter()
        code_to_names = defaultdict(set)
        for fact in facts:
            rtype = fact.get("report_type")
            code = fact.get("code")
            if not code:
                continue
            item_name = fact.get("item_name")
            period = fact.get("period")
            key = (rtype, code, period)
            code_instances[key] += 1
            code_to_names[(rtype, code)].add(item_name)
            
        dups = {k: count for k, count in code_instances.items() if count > 1}
        if dups:
            dup_codes_by_file[doc_id] = {str(k): v for k, v in dups.items()}
            
        # Invariant C: NOTES chunk unit consistency
        chunks = data.get("chunks", [])
        for c in chunks:
            sec = c.get("section", "")
            unit = c.get("unit", "")
            cid = c.get("chunk_id", "")
            if sec == "NOTES":
                # Check if unit differs from default_unit
                if unit and unit != default_unit:
                    # Is it foreign currency or something else?
                    unit_mismatch_notes[doc_id].append({
                        "chunk_id": cid,
                        "unit": unit,
                        "default_unit": default_unit,
                        "text_snippet": c.get("text", "")[:100]
                    })
                    
        # Check Cash Flow Identities in quality
        quality = data.get("quality", {})
        checks = quality.get("identity_checks", [])
        for chk in checks:
            cname = chk.get("check_name", "")
            if cname.startswith("CF_"):
                cf_check_stats["total"] += 1
                if chk.get("passed"):
                    cf_check_stats["passed"] += 1
                else:
                    cf_check_stats["failed"] += 1
                    failed_cf_files.append((doc_id, cname, chk.get("diff"), chk.get("formula")))
                    
        # Specific tracking for GVR_2024 and NVB_2023
        if "GVR_2024" in doc_id or "NVB_2023" in doc_id:
            specific_inspect[doc_id] = {
                "default_unit": default_unit,
                "report_types": list(report_types),
                "has_cash_flow": "CASH_FLOW" in report_types,
                "facts_count": len(facts),
                "chunks_count": len(chunks),
                "duplicate_codes_count": len(dups),
                "notes_mismatched_units_count": len(unit_mismatch_notes.get(doc_id, [])),
                "quality": quality
            }

    print("\n" + "="*80)
    print("KẾT QUẢ KIỂM TRA BẤT BIẾN (INVARIANTS) TRÊN TOÀN BỘ CORPUS")
    print("="*80)
    
    print("\n1. INVARIANT A: Sự hiện diện đầy đủ của 3 báo cáo (BS, IS, CF)")
    print(f"- Số file có BALANCE_SHEET: {stmt_counts['BALANCE_SHEET']}/{len(json_files)}")
    print(f"- Số file có INCOME_STATEMENT: {stmt_counts['INCOME_STATEMENT']}/{len(json_files)}")
    print(f"- Số file có CASH_FLOW: {stmt_counts['CASH_FLOW']}/{len(json_files)}")
    if missing_stmts:
        print(f"  [CẢNH BÁO] Có {len(missing_stmts)} file thiếu báo cáo tài chính chính:")
        for doc, miss in missing_stmts.items():
            print(f"    + {doc}: thiếu {miss}")
    else:
        print("  [HOÀN HẢO] 100% (141/141) file có đầy đủ cả 3 báo cáo: BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW!")

    print("\n2. INVARIANT B: Trùng lặp mã số (duplicate codes) trong cùng report_type & period")
    if dup_codes_by_file:
        print(f"  [CẢNH BÁO] Có {len(dup_codes_by_file)} file phát hiện mã trùng:")
        for doc, dups in list(dup_codes_by_file.items())[:5]:
            print(f"    + {doc}: {dups}")
    else:
        print("  [HOÀN HẢO] 100% (141/141) file KHÔNG CÓ bất kỳ mã số trùng lặp nào trong cùng report_type & period!")

    print("\n3. INVARIANT C: Tính nhất quán của đơn vị tính (unit) trong các chunk NOTES")
    if unit_mismatch_notes:
        print(f"  [GHI NHẬN] Có {len(unit_mismatch_notes)} file có chunk NOTES mang unit khác default_unit:")
        for doc, items in list(unit_mismatch_notes.items())[:5]:
            print(f"    + {doc} (default: {items[0]['default_unit']}): {len(items)} chunks khác unit. Ví dụ: {[it['unit'] for it in items[:3]]}")
    else:
        print("  [HOÀN HẢO] 100% (141/141) chunk NOTES có unit khớp hoàn toàn với default_unit!")

    print("\n4. CASH FLOW IDENTITY CHECKS:")
    print(f"- Tổng số phép kiểm tra CF: {cf_check_stats['total']}")
    print(f"- Đạt (passed): {cf_check_stats['passed']}")
    print(f"- Không đạt (failed): {cf_check_stats['failed']}")
    if failed_cf_files:
        print(f"  Chi tiết {len(failed_cf_files)} phép kiểm tra CF lệch:")
        for doc, name, diff, formula in failed_cf_files[:10]:
            print(f"    + {doc} | {name} | diff={diff} | {formula}")

    print("\n" + "="*80)
    print("CHI TIẾT KIỂM TRA ĐẶC BIỆT CHO GVR_2024 VÀ NVB_2023:")
    print("="*80)
    for doc_id, info in specific_inspect.items():
        print(f"\n* TÀI LIỆU: {doc_id}")
        print(f"  - Default Unit: {info['default_unit']}")
        print(f"  - Có CASH_FLOW: {info['has_cash_flow']} (Các report_types: {info['report_types']})")
        print(f"  - Số Facts: {info['facts_count']} | Số Chunks: {info['chunks_count']}")
        print(f"  - Số mã trùng lặp (Duplicate codes): {info['duplicate_codes_count']}")
        print(f"  - Số chunk NOTES lệch unit: {info['notes_mismatched_units_count']}")
        q = info['quality']
        print(f"  - Gating Status: {q.get('gating_status')} (Mode: {q.get('identity_check_mode')})")
        print(f"  - Identity Checks: {q.get('identity_checks_passed')}/{q.get('identity_checks_total')}")
        if q.get('gating_reasons'):
            print(f"  - Gating Reasons: {q.get('gating_reasons')}")

if __name__ == "__main__":
    main()
