#!/usr/bin/env python3
"""Wind Load Generator (mini Python) — มยผ. 1311-50, low-rise building.

พอร์ตจาก index.html ให้คำนวณเหมือนกันทุกขั้น ใช้แค่ standard library
    python3 wind_load.py                      # ค่าเริ่มต้น (นครสวรรค์, B=20, L=40, ...)
    python3 wind_load.py --province ภูเก็ต --exposure A --cpi 2 --B 15 --L 30
    python3 wind_load.py --json               # ผลลัพธ์เป็น JSON
    python3 wind_load.py --list-provinces
"""
import argparse
import json
import math
import sys

# ---------- Reference data (มยผ. 1311-50) ----------
GROUPS = {
    "1": (25, 1.0), "2": (27, 1.0), "3": (29, 1.0),
    "4A": (25, 1.2), "4B": (25, 1.08),
}  # group -> (V50 m/s, T_F)

PROVINCES = {
    "นครสวรรค์": "1", "เชียงใหม่": "3", "เชียงราย": "3", "น่าน": "2", "พะเยา": "3", "แพร่": "2",
    "แม่ฮ่องสอน": "3", "ลำปาง": "2", "ลำพูน": "2", "กำแพงเพชร": "1", "พิจิตร": "1", "พิษณุโลก": "1",
    "เพชรบูรณ์": "1", "สุโขทัย": "1", "อุตรดิตถ์": "1", "อุทัยธานี": "1", "กรุงเทพมหานคร": "1",
    "นนทบุรี": "1", "ปทุมธานี": "1", "สมุทรปราการ": "1", "นครปฐม": "1", "ราชบุรี": "1", "กาญจนบุรี": "1",
    "สุพรรณบุรี": "1", "พระนครศรีอยุธยา": "1", "อ่างทอง": "1", "ลพบุรี": "1", "สระบุรี": "1",
    "ประจวบคีรีขันธ์": "4A", "เพชรบุรี": "4B", "ชลบุรี": "1", "ระยอง": "1", "จันทบุรี": "1", "ตราด": "1",
    "นครราชสีมา": "1", "ขอนแก่น": "1", "อุดรธานี": "1", "อุบลราชธานี": "2", "หนองคาย": "2", "บึงกาฬ": "2",
    "ภูเก็ต": "4B", "สงขลา": "4A", "สุราษฎร์ธานี — บริเวณอื่นๆ": "4B", "นครศรีธรรมราช — บริเวณอื่นๆ": "4B",
    "กระบี่": "4B", "ตรัง": "4B", "ยะลา": "4A", "ปัตตานี": "4A", "นราธิวาส": "4A", "พัทลุง": "4A",
}

# Exposure -> (formula text, Ce(z) unclamped, lo, hi)
EXPOSURE = {
    "A": ("(z/10)^0.28", lambda z: (z / 10) ** 0.28, 1.0, 2.5),
    "B": ("0.5*(z/12.7)^0.5", lambda z: 0.5 * (z / 12.7) ** 0.5, 0.5, 2.5),
    "C": ("0.4*(z/30)^0.72", lambda z: 0.4 * (z / 30) ** 0.72, 0.4, 2.5),
}

IMPORTANCE = {"low": 0.8, "normal": 1.0, "high": 1.15, "very-high": 1.15}  # ตาราง 2-2 ด้านกำลัง
IW_SERVICEABILITY = 0.75

CPI_CASES = {"1": (-0.15, 0.0), "2": (-0.45, 0.3), "3": (-0.7, 0.7)}

CGI, RHO, GRAV = 2.0, 1.25, 9.81

CASE1_ZONES = ["1", "1E", "2", "2E", "3", "3E", "4", "4E"]
CASE1_TABLE = {
    "0-5":   [0.75, 1.15, -1.3, -2.0, -0.7, -1.0, -0.55, -0.8],
    "20":    [1.0, 1.5, -1.3, -2.0, -0.9, -1.3, -0.8, -1.2],
    "30-45": [1.05, 1.3, 0.4, 0.5, -0.8, -1.0, -0.7, -0.9],
    "90":    [1.05, 1.3, 1.05, 1.3, -0.7, -0.9, -0.7, -0.9],
}
CASE2_ZONES = ["1", "1E", "2", "2E", "3", "3E", "4", "4E", "5", "5E", "6", "6E"]
CASE2_VALUES = [-0.85, -0.9, -1.3, -2.0, -0.7, -1.0, -0.85, -0.9, 0.75, 1.15, -0.55, -0.8]


def calculate(province="นครสวรรค์", limit_state="strength", exposure="B", importance="normal",
              cpi_case="3", use_tf=None, H_eave=6.0, H_ridge=7.5, B=20.0, L=40.0, roof_slope="0-5"):
    """คืน dict ผลลัพธ์ทั้งหมด หน่วยแรงเป็น N/m² (หาร GRAV ได้ kg/m²)"""
    group = PROVINCES[province]
    v50, tf = GROUPS[group]
    if use_tf is None:  # ค่าเริ่มต้นเหมือนเว็บ: บังคับ T_F เมื่ออาคารสำคัญสูงมาก
        use_tf = importance == "very-high"
    Vbar = tf * v50 if use_tf else v50
    q = 0.5 * RHO * Vbar ** 2

    slope_deg = math.degrees(math.atan((H_ridge - H_eave) / (B / 2))) if B > 0 else 0.0
    h_raw = (H_eave + H_ridge) / 2
    h = max(h_raw, 6.0)

    ce_text, ce_fn, lo, hi = EXPOSURE[exposure]
    Ce_raw = ce_fn(h)
    Ce = min(max(Ce_raw, lo), hi)

    iw = IW_SERVICEABILITY if limit_state == "serviceability" else IMPORTANCE[importance]

    narrow = min(B, L)
    z_raw = min(0.1 * narrow, 0.4 * h)
    z = max(z_raw, 0.04 * narrow, 1.0)
    y = max(6.0, 2 * z)

    cpi_lo, cpi_hi = CPI_CASES[cpi_case]
    pi_lo = iw * q * Ce * CGI * cpi_lo  # LC ภายในลบ
    pi_hi = iw * q * Ce * CGI * cpi_hi  # LC ภายในบวก
    p_factor = iw * q * Ce  # ตาราง Cg·Cp รวม Cg ไว้แล้ว

    def zones(names, coeffs):
        out = []
        for zone, cgcp in zip(names, coeffs):
            p = p_factor * cgcp
            out.append({"zone": zone, "cgcp": cgcp, "p": p, "net_pos": p - pi_hi, "net_neg": p - pi_lo})
        return out

    case1 = zones(CASE1_ZONES, CASE1_TABLE[roof_slope])
    case2 = zones(CASE2_ZONES, CASE2_VALUES)

    def critical(rows, lc_pos, lc_neg):
        crit = []
        for r in rows:
            cands = [(r["net_pos"], lc_pos), (r["net_neg"], lc_neg)]
            press = max(cands)
            suction = min(cands)
            crit.append({
                "zone": r["zone"],
                "pressure": {"net": press[0], "lc": press[1]} if press[0] >= 0 else None,
                "suction": {"net": suction[0], "lc": suction[1]} if suction[0] < 0 else None,
            })
        return crit

    return {
        "input": dict(province=province, group=group, limit_state=limit_state, exposure=exposure,
                      importance=importance, cpi_case=cpi_case, use_tf=use_tf, H_eave=H_eave,
                      H_ridge=H_ridge, B=B, L=L, roof_slope=roof_slope),
        "V50": v50, "TF": tf, "Vbar": Vbar, "q": q, "slope_deg": slope_deg, "h_raw": h_raw, "h": h,
        "Ce_text": ce_text, "Ce_raw": Ce_raw, "Ce": Ce, "Iw": iw, "narrow": narrow, "z_raw": z_raw,
        "z": z, "y": y, "cpi": (cpi_lo, cpi_hi), "pi_neg": pi_lo, "pi_pos": pi_hi, "p_factor": p_factor,
        "case1": case1, "case2": case2,
        "crit_trans": critical(case1, "LC1", "LC2"),
        "crit_parallel": critical(case2, "LC3", "LC4"),
    }


def kg(v):
    return v / GRAV


def sign(v):
    return "กด" if v >= 0 else "ดูด"


def report(r):
    i = r["input"]
    L = []
    w = L.append
    w("=" * 72)
    w("WIND LOAD GENERATOR · มยผ. 1311-50 · LOW-RISE BUILDING")
    w("=" * 72)
    w(f"จังหวัด {i['province']} → กลุ่ม {i['group']}: V50 = {r['V50']} m/s, T_F = {r['TF']}")
    w(f"V̄ = {'T_F × V50' if i['use_tf'] else 'V50'} = {r['Vbar']:.2f} m/s")
    w(f"q = 0.5 × 1.25 × {r['Vbar']:.2f}² = {r['q']:.1f} N/m² = {kg(r['q']):.2f} kg/m²")
    w(f"θ ≈ {r['slope_deg']:.2f}°  (ตาราง Cg·Cp ใช้ bin {i['roof_slope']}°)")
    w(f"h = ({i['H_eave']} + {i['H_ridge']})/2 = {r['h_raw']:.2f} m → ใช้ h = {r['h']:.2f} m")
    w(f"Ce (Exposure {i['exposure']}: {r['Ce_text']}) = {r['Ce_raw']:.3f} → ใช้ {r['Ce']:.3f}")
    w(f"Iw = {r['Iw']:.2f} ({i['limit_state']}, {i['importance']})")
    w(f"z = {r['z']:.2f} m, y = {r['y']:.2f} m  (ด้านแคบ = {r['narrow']} m)")
    lo, hi = r["cpi"]
    w(f"pi (Cpi={lo}) = {kg(r['pi_neg']):.2f} kg/m²,  pi (Cpi={hi}) = {kg(r['pi_pos']):.2f} kg/m²")
    w(f"p = Iw·q·Ce·(Cg·Cp) = {kg(r['p_factor']):.2f} × (Cg·Cp) kg/m²")

    def table(title, rows, key, cpi):
        w("")
        w(f"{title} (Cpi = {cpi:.2f})")
        w(f"  {'โซน':<5}{'Cg·Cp':>8}{'p':>10}{'p_net (kg/m²)':>18}")
        for x in rows:
            n = x[key]
            w(f"  {x['zone']:<5}{x['cgcp']:>8.2f}{kg(x['p']):>10.1f}{kg(n):>12.1f} ({sign(n)})")

    table("LC1 · ลมตั้งฉากสันหลังคา · ภายในบวก", r["case1"], "net_pos", hi)
    table("LC2 · ลมตั้งฉากสันหลังคา · ภายในลบ", r["case1"], "net_neg", lo)
    table("LC3 · ลมขนานสันหลังคา · ภายในบวก", r["case2"], "net_pos", hi)
    table("LC4 · ลมขนานสันหลังคา · ภายในลบ", r["case2"], "net_neg", lo)

    def crit(title, rows):
        w("")
        w(f"ค่าวิกฤต — {title}")
        w(f"  {'โซน':<5}{'แรงกดวิกฤต':>18}{'แรงดูดวิกฤต':>22}")
        for c in rows:
            p = f"+{kg(c['pressure']['net']):.1f} ({c['pressure']['lc']})" if c["pressure"] else "—"
            s = f"{kg(c['suction']['net']):.1f} ({c['suction']['lc']})" if c["suction"] else "—"
            w(f"  {c['zone']:<5}{p:>18}{s:>22}")

    crit("ลมตั้งฉากสันหลังคา (LC1 vs LC2)", r["crit_trans"])
    crit("ลมขนานสันหลังคา (LC3 vs LC4)", r["crit_parallel"])
    w("")
    w("หน่วย kg/m² · บวก = แรงกด · ลบ = แรงดูด/ยก")
    w("เครื่องมือช่วยคำนวณเบื้องต้น — ตรวจสอบตามมาตรฐาน มยผ. 1311-50 ก่อนนำไปออกแบบจริง")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Wind load (มยผ. 1311-50) สำหรับอาคารเตี้ย")
    ap.add_argument("--province", default="นครสวรรค์")
    ap.add_argument("--limit-state", choices=["strength", "serviceability"], default="strength")
    ap.add_argument("--exposure", choices=list(EXPOSURE), default="B")
    ap.add_argument("--importance", choices=list(IMPORTANCE), default="normal")
    ap.add_argument("--cpi", choices=list(CPI_CASES), default="3", help="กรณีช่องเปิด 1/2/3")
    tf = ap.add_mutually_exclusive_group()
    tf.add_argument("--tf", dest="use_tf", action="store_true", default=None, help="บังคับคูณ T_F")
    tf.add_argument("--no-tf", dest="use_tf", action="store_false", help="ไม่คูณ T_F")
    ap.add_argument("--H-eave", type=float, default=6.0)
    ap.add_argument("--H-ridge", type=float, default=7.5)
    ap.add_argument("--B", type=float, default=20.0, help="ความกว้าง (m)")
    ap.add_argument("--L", type=float, default=40.0, help="ความยาว (m)")
    ap.add_argument("--roof-slope", choices=list(CASE1_TABLE), default="0-5")
    ap.add_argument("--json", action="store_true", help="แสดงผลเป็น JSON (หน่วย N/m²)")
    ap.add_argument("--list-provinces", action="store_true")
    a = ap.parse_args(argv)

    if a.list_provinces:
        for name, g in PROVINCES.items():
            print(f"{g:<3} {name}")
        return 0
    if a.province not in PROVINCES:
        ap.error(f"ไม่พบจังหวัด '{a.province}' (ดู --list-provinces)")

    r = calculate(a.province, a.limit_state, a.exposure, a.importance, a.cpi, a.use_tf,
                  a.H_eave, a.H_ridge, a.B, a.L, a.roof_slope)
    print(json.dumps(r, ensure_ascii=False, indent=2) if a.json else report(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
