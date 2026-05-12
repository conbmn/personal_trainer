"""
Unit conversion for blood test biomarkers.

Each entry maps a canonical_name → (canonical_unit, {alt_unit: multiplier}).
Multiplier converts alt_unit → canonical_unit:  canonical_value = raw_value * multiplier
"""

# canonical_name → (canonical_unit, {alt_unit: factor_to_canonical})
_TABLE: dict[str, tuple[str, dict[str, float]]] = {
    # Iron stores
    "ferritin":          ("µg/L",   {"ng/mL": 1.0, "ng/dl": 0.01, "pmol/L": 0.44966}),
    "iron":              ("µmol/L", {"µg/dL": 0.17905, "mg/dL": 179.05, "µg/L": 0.17905}),
    "transferrin":       ("g/L",    {"mg/dL": 0.01}),
    "tibc":              ("µmol/L", {"µg/dL": 0.17905}),
    "transferrin_sat":   ("%",      {}),

    # Complete blood count
    "hemoglobin":        ("g/dL",   {"g/L": 0.1, "mmol/L": 1.6113}),
    "hematocrit":        ("%",      {"L/L": 100.0}),
    "erythrocytes":      ("T/L",    {"10^6/µL": 1.0, "10^12/L": 1.0, "M/µL": 1.0}),
    "leukocytes":        ("G/L",    {"10^3/µL": 1.0, "10^9/L": 1.0, "K/µL": 1.0}),
    "thrombocytes":      ("G/L",    {"10^3/µL": 1.0, "10^9/L": 1.0, "K/µL": 1.0}),
    "mcv":               ("fL",     {}),
    "mch":               ("pg",     {}),
    "mchc":              ("g/dL",   {"g/L": 0.1}),
    "reticulocytes":     ("%",      {}),

    # Lipids
    "cholesterol":       ("mmol/L", {"mg/dL": 0.025856}),
    "ldl":               ("mmol/L", {"mg/dL": 0.025856}),
    "hdl":               ("mmol/L", {"mg/dL": 0.025856}),
    "triglycerides":     ("mmol/L", {"mg/dL": 0.011299}),
    "vldl":              ("mmol/L", {"mg/dL": 0.025856}),

    # Metabolic
    "glucose":           ("mmol/L", {"mg/dL": 0.055506}),
    "hba1c":             ("%",      {"mmol/mol": 0.10929}),
    "creatinine":        ("µmol/L", {"mg/dL": 88.402}),
    "urea":              ("mmol/L", {"mg/dL": 0.16653}),
    "uric_acid":         ("µmol/L", {"mg/dL": 59.485}),
    "alt":               ("U/L",    {}),
    "ast":               ("U/L",    {}),
    "ggt":               ("U/L",    {}),
    "alkaline_phosphatase": ("U/L", {}),
    "bilirubin":         ("µmol/L", {"mg/dL": 17.104}),
    "albumin":           ("g/L",    {"g/dL": 10.0}),
    "total_protein":     ("g/L",    {"g/dL": 10.0}),
    "ldh":               ("U/L",    {}),
    "ck":                ("U/L",    {}),

    # Thyroid
    "tsh":               ("mU/L",   {"mIU/L": 1.0, "µIU/mL": 1.0}),
    "ft3":               ("pmol/L", {"pg/mL": 1.5361}),
    "ft4":               ("pmol/L", {"ng/dL": 12.871}),
    "t3":                ("nmol/L", {"ng/dL": 0.015391}),
    "t4":                ("nmol/L", {"µg/dL": 12.871}),

    # Vitamins & minerals
    "vitamin_d":         ("nmol/L", {"ng/mL": 2.4966}),
    "vitamin_b12":       ("pmol/L", {"pg/mL": 0.73778, "ng/L": 0.73778}),
    "folate":            ("nmol/L", {"ng/mL": 2.2653, "µg/L": 2.2653}),
    "zinc":              ("µmol/L", {"µg/dL": 0.15295, "mg/L": 15.295}),
    "magnesium":         ("mmol/L", {"mg/dL": 0.41133, "mEq/L": 0.5}),
    "calcium":           ("mmol/L", {"mg/dL": 0.24953}),
    "phosphate":         ("mmol/L", {"mg/dL": 0.32290}),
    "sodium":            ("mmol/L", {"mEq/L": 1.0}),
    "potassium":         ("mmol/L", {"mEq/L": 1.0}),
    "chloride":          ("mmol/L", {"mEq/L": 1.0}),

    # Hormones
    "testosterone":      ("nmol/L", {"ng/dL": 0.034669, "ng/mL": 3.4669}),
    "cortisol":          ("nmol/L", {"µg/dL": 27.588, "µg/L": 2.7588}),
    "insulin":           ("pmol/L", {"µIU/mL": 6.9444, "mIU/L": 6.9444}),
    "igf1":              ("nmol/L", {"ng/mL": 0.13100, "µg/L": 0.13100}),

    # Inflammation / immunity
    "crp":               ("mg/L",   {"mg/dL": 10.0}),
    "hs_crp":            ("mg/L",   {"mg/dL": 10.0}),
    "esr":               ("mm/h",   {}),
}


def to_canonical(canonical_name: str, value: float, unit: str) -> tuple[float, str]:
    """
    Convert value/unit to canonical form.
    Returns (canonical_value, canonical_unit).
    Falls back to (value, unit) unchanged if the marker or unit is not in the table.
    """
    entry = _TABLE.get(canonical_name.lower())
    if entry is None:
        return (value, unit)

    canon_unit, conversions = entry

    # Already in canonical unit (case-insensitive, ignore unicode variants)
    if _units_match(unit, canon_unit):
        return (round(value, 4), canon_unit)

    # Try to find a conversion
    for alt, factor in conversions.items():
        if _units_match(unit, alt):
            return (round(value * factor, 4), canon_unit)

    # Unknown unit — store as-is so we don't silently corrupt data
    return (value, unit)


def _units_match(a: str, b: str) -> bool:
    """Case-insensitive unit comparison, ignoring common unicode/ascii variants."""
    def norm(s: str) -> str:
        return s.lower().replace("μ", "µ").replace(" ", "").strip()
    return norm(a) == norm(b)
