# app/utils/validators.py

VALID_SHADE_CODES = {"7015", "1099", "4013", "2000", "7016"} 

def validate_inward(data):
    items = data.get('items', [])
    summary = data.get('summary', {})
    
    # 1. Serial sequence check
    extracted_srs = [item.get('sr_no') for item in items if item.get('sr_no') is not None]
    if len(extracted_srs) != len(set(extracted_srs)):
        return False, "Duplicate rows detected. Hallucinated serial number."
    
    if len(extracted_srs) > 0:
        expected_srs = list(range(1, int(summary.get('total_thaans', 0)) + 1))
        missing = set(expected_srs) - set(extracted_srs)
        if missing: return False, f"Missing rows detected. Skipped SRs: {missing}"

    # 2. Math check
    calc_sum = sum(float(item.get('meters', 0) or 0) for item in items)
    reported_sum = float(summary.get('total_meters', 0) or 0)
    if abs(calc_sum - reported_sum) > 0.1:
        return False, f"Math Mismatch: Missing {round(reported_sum - calc_sum, 2)} meters."
        
    # 3. Shade check
    for item in items:
        shd = str(item.get('shade_code', ''))
        if shd and shd.lower() not in ['none', 'null', ''] and shd not in VALID_SHADE_CODES:
            return False, f"Invalid Shade '{shd}' on Row {item.get('sr_no')}"
            
    return True, "Inward Data Verified ✅"

def validate_outward(data):
    items = data.get('items', [])
    summary = data.get('summary', {})
    
    # 1. Thaan Check
    calc_thaans = sum(float(item.get('thaans', 0) or 0) for item in items)
    reported_thaans = float(summary.get('total_thaans', 0) or 0)
    if abs(calc_thaans - reported_thaans) > 0.1:
        return False, f"Thaan Mismatch: Calculated {calc_thaans}, Document says {reported_thaans}"
        
    # 2. Meter Check
    calc_meters = sum(float(item.get('meters', 0) or 0) for item in items)
    reported_meters = float(summary.get('total_meters', 0) or 0)
    if abs(calc_meters - reported_meters) > 0.1:
        return False, f"Meter Mismatch: Calculated {calc_meters}, Document says {reported_meters}"
    
    # 3. Price is optional in the Omni-Parser schema; defaults to 0 when absent.
    return True, "Outward Data Verified ✅"