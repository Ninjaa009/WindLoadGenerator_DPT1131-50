"""Wind Load Generator — มยผ. 1311-50 (Streamlit)

รัน:  streamlit run streamlit_app.py
ใช้ตรรกะคำนวณจาก wind_load.py (ตัวเดียวกับ CLI)
"""
from pathlib import Path

import pandas as pd
import streamlit as st

from wind_load import (CASE1_TABLE, CASE1_ZONES, CASE2_VALUES, CASE2_ZONES, CGI, CPI_CASES,
                       EXPOSURE, GRAV, GROUPS, IMPORTANCE, PROVINCES, calculate, report)

DOCS = Path(__file__).parent / "docs"

EXPOSURE_LABELS = {
    "A": "A — เมืองใหญ่หนาแน่น / ชายฝั่งคลื่นลมแรง",
    "B": "B — ชานเมือง / ศูนย์กลางเมืองขนาดเล็ก",
    "C": "C — ศูนย์กลางเมืองใหญ่ ตึกสูงหนาแน่น",
}
IMPORTANCE_LABELS = {
    "low": "น้อย — เกษตร/ชั่วคราว/เก็บของเล็กๆ",
    "normal": "ปกติ — อาคารทั่วไป",
    "high": "มาก — ชุมนุมคน/โรงเรียน/เรือนจำ",
    "very-high": "สูงมาก — โรงพยาบาล/สถานีดับเพลิง/โรงไฟฟ้า",
}
CPI_LABELS = {
    "1": "กรณีที่ 1 — ช่องเปิดรวม < 0.1% ของผิวทั้งหมด",
    "2": "กรณีที่ 2 — รั่วซึมไม่สม่ำเสมอ ปิดสนิทได้เมื่อมีพายุ",
    "3": "กรณีที่ 3 — ช่องเปิดขนาดใหญ่ ต้านพายุไม่ได้",
}
SLOPE_LABELS = {"0-5": "0° ถึง 5°", "20": "20°", "30-45": "30° ถึง 45°", "90": "90°"}

POS, NEG = "#A6402F", "#1E7A66"


def kg(v):
    return v / GRAV


def sign(v):
    return "กด" if v >= 0 else "ดูด"


def color_net(v):
    if isinstance(v, (int, float)):
        return f"color: {POS if v >= 0 else NEG}; font-weight: 600"
    return ""


def lc_frame(rows, key):
    return pd.DataFrame([{
        "โซน": r["zone"],
        "Cg·Cp": r["cgcp"],
        "p (kg/m²)": round(kg(r["p"]), 1),
        "p_net (kg/m²)": round(kg(r[key]), 1),
        "": sign(r[key]),
    } for r in rows])


def show_lc(title, rows, key):
    st.markdown(f"**{title}**")
    df = lc_frame(rows, key)
    st.dataframe(
        df.style.map(color_net, subset=["p (kg/m²)", "p_net (kg/m²)"]).format(
            {"Cg·Cp": "{:.2f}", "p (kg/m²)": "{:.1f}", "p_net (kg/m²)": "{:.1f}"}),
        hide_index=True, width="stretch")


def crit_frame(crit):
    out = []
    for c in crit:
        p, s = c["pressure"], c["suction"]
        out.append({
            "โซน": c["zone"],
            "แรงกดวิกฤต (kg/m²)": round(kg(p["net"]), 1) if p else None,
            "จาก LC (กด)": p["lc"] if p else "—",
            "แรงดูดวิกฤต (kg/m²)": round(kg(s["net"]), 1) if s else None,
            "จาก LC (ดูด)": s["lc"] if s else "—",
        })
    return pd.DataFrame(out)


def all_lc_csv(r):
    rows = []
    for lc, case, key in [("LC1", "case1", "net_pos"), ("LC2", "case1", "net_neg"),
                          ("LC3", "case2", "net_pos"), ("LC4", "case2", "net_neg")]:
        for z in r[case]:
            rows.append({"LC": lc, "zone": z["zone"], "CgCp": z["cgcp"],
                         "p_kg_m2": round(kg(z["p"]), 2), "p_net_kg_m2": round(kg(z[key]), 2)})
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")


# ---------------- page ----------------
st.set_page_config(page_title="Wind Load Generator — มยผ. 1311-50", page_icon="🌬️", layout="wide")
st.caption("WIND LOAD GENERATOR · มยผ. 1311-50 · LOW-RISE BUILDING")
st.title("เครื่องคำนวณแรงลมสถิตเทียบเท่า")
st.write("คำนวณ q, Cₑ, pᵢ, p, p_net ครบ 8 โซน (ลมตั้งฉากสันหลังคา) และ 12 โซน (ลมขนานสันหลังคา) พร้อม calculation sheet")

# ---------------- inputs (sidebar) ----------------
with st.sidebar:
    st.header("1. ที่ตั้งโครงการ")
    provinces = list(PROVINCES)
    province = st.selectbox("จังหวัด", provinces, index=provinces.index("นครสวรรค์"))
    group = PROVINCES[province]
    v50, tf = GROUPS[group]
    st.caption(f"กลุ่ม **{group}** · V₅₀ = **{v50}** m/s · T_F = **{tf}**")
    limit_state = st.selectbox("สภาวะจำกัด", ["strength", "serviceability"],
                               format_func=lambda k: {"strength": "ด้านกำลัง (Strength)",
                                                      "serviceability": "ด้านการใช้งาน (Serviceability)"}[k],
                               help="ด้านการใช้งานใช้ Iw = 0.75 ทุกประเภท")

    st.header("2. ภูมิประเทศและอาคาร")
    exposure = st.selectbox("Exposure Category", list(EXPOSURE), index=1, format_func=EXPOSURE_LABELS.get)
    importance = st.selectbox("ประเภทความสำคัญของอาคาร", list(IMPORTANCE), index=1,
                              format_func=IMPORTANCE_LABELS.get)
    use_tf = st.checkbox(f"รวมค่าประกอบไต้ฝุ่น T_F (กลุ่ม {group}: T_F = {tf:.2f})",
                         value=(importance == "very-high"), key=f"tf_{importance}",
                         help="อาคารสูงมาก: มาตรฐานบังคับให้คูณ T_F · อาคารทั่วไป: ผู้ออกแบบพิจารณาเอง")
    cpi_case = st.selectbox("ลักษณะช่องเปิด (Cpi)", list(CPI_CASES), index=2, format_func=CPI_LABELS.get)

    st.header("3. เรขาคณิตอาคาร (m)")
    c1, c2 = st.columns(2)
    B = c1.number_input("B (กว้าง)", min_value=0.1, value=20.0, step=1.0)
    L = c2.number_input("L (ยาว)", min_value=0.1, value=40.0, step=1.0)
    H_eave = c1.number_input("H eave", min_value=0.0, value=6.0, step=0.5)
    H_ridge = c2.number_input("H ridge", min_value=0.0, value=7.5, step=0.5)

r0 = calculate(province, limit_state, exposure, importance, cpi_case, use_tf, H_eave, H_ridge, B, L)
with st.sidebar:
    roof_slope = st.selectbox("ความลาดชันหลังคา (ตาราง Cg·Cp กรณีที่ 1)", list(CASE1_TABLE),
                              format_func=SLOPE_LABELS.get,
                              help=f"คำนวณจากเรขาคณิต ≈ {r0['slope_deg']:.1f}° — เลือก bin ใกล้เคียงสุด")
    st.caption(f"มุมจากเรขาคณิต ≈ {r0['slope_deg']:.1f}°")

r = calculate(province, limit_state, exposure, importance, cpi_case, use_tf,
              H_eave, H_ridge, B, L, roof_slope)
cpi_lo, cpi_hi = r["cpi"]

tab_calc, tab_design, tab_ref = st.tabs(["เครื่องคำนวณ", "สรุปค่าออกแบบ", "เอกสารอ้างอิงสูตร"])

# ---------------- calculator ----------------
with tab_calc:
    st.subheader("ค่าคำนวณกลาง (Intermediate values)")
    m = st.columns(3)
    m[0].metric("V̄", f"{r['Vbar']:.1f} m/s")
    m[1].metric(f"q ({r['q'] / 1000:.3f} kPa)", f"{kg(r['q']):.1f} kg/m²")
    m[2].metric("h (mean roof)", f"{r['h']:.2f} m")
    m = st.columns(3)
    m[0].metric("Cₑ", f"{r['Ce']:.3f}")
    m[1].metric("Cgi (ภายใน)", f"{CGI:.1f}", help="Cg ภายนอกรวมอยู่ในตาราง Cg·Cp แล้ว")
    m[2].metric("Iw", f"{r['Iw']:.2f}")
    m = st.columns(3)
    m[0].metric(f"pᵢ (Cpi {cpi_lo})", f"{kg(r['pi_neg']):.1f} kg/m²")
    m[1].metric(f"pᵢ (Cpi {cpi_hi})", f"{kg(r['pi_pos']):.1f} kg/m²")
    m[2].metric("z / y (edge)", f"{r['z']:.2f} / {r['y']:.2f} m")

    st.divider()
    a, b = st.columns(2)
    with a:
        show_lc(f"LC1 · ลมตั้งฉากสันหลังคา · ภายในบวก (Cpi = {cpi_hi:.2f})", r["case1"], "net_pos")
    with b:
        show_lc(f"LC2 · ลมตั้งฉากสันหลังคา · ภายในลบ (Cpi = {cpi_lo:.2f})", r["case1"], "net_neg")
    a, b = st.columns(2)
    with a:
        show_lc(f"LC3 · ลมขนานสันหลังคา · ภายในบวก (Cpi = {cpi_hi:.2f})", r["case2"], "net_pos")
    with b:
        show_lc(f"LC4 · ลมขนานสันหลังคา · ภายในลบ (Cpi = {cpi_lo:.2f})", r["case2"], "net_neg")
    st.caption("แต่ละ Load Case คือชุดแรงลมสุทธิพร้อมใช้ — ป้อนลงโปรแกรมวิเคราะห์แยกเป็นคนละ case · "
               "บวก (+) = แรงกด (แดง) · ลบ (−) = แรงดูด/ยก (เขียว)")

    d1, d2 = st.columns(2)
    d1.download_button("ดาวน์โหลด LC1–LC4 (CSV)", all_lc_csv(r), "wind_load_cases.csv", "text/csv")
    d2.download_button("ดาวน์โหลดรายงาน (TXT)", report(r).encode("utf-8"), "wind_load_report.txt", "text/plain")

    st.divider()
    st.subheader("แผ่นแสดงการคำนวณ (Calculation Sheet)")
    i = r["input"]
    pf = kg(r["p_factor"])
    vline = (f"V̄ = {tf} × {v50} = {r['Vbar']:.2f} m/s" if i["use_tf"] else f"V̄ = {v50} = {r['Vbar']:.2f} m/s")
    hline = (f"h = ({H_eave} + {H_ridge})/2 = {r['h_raw']:.2f} m"
             + ("  → ใช้ h = 6.00 m (ขั้นต่ำ)" if r["h_raw"] < 6 else f"  → ใช้ h = {r['h']:.2f} m"))
    ce_note = "  → เกินขอบเขต ใช้" if abs(r["Ce_raw"] - r["Ce"]) > 1e-12 else "  → ใช้"
    sheet = f"""ขั้นที่ 1 — หน่วยแรงลมอ้างอิง q
  จังหวัด {province} → กลุ่ม {group}:  V₅₀ = {v50} m/s,  T_F = {tf}
  {vline}
  q = 0.5 × 1.25 × {r['Vbar']:.2f}² = {r['q']:.1f} N/m² = {r['q']:.1f} ÷ 9.81 = {kg(r['q']):.2f} kg/m²

ขั้นที่ 2 — ความสูงอ้างอิง h และ Cₑ
  θ = atan(({H_ridge} − {H_eave}) / ({B}/2)) = {r['slope_deg']:.2f}°
  {hline}
  Cₑ (Exposure {exposure}: {r['Ce_text']}) = {r['Ce_raw']:.3f}{ce_note} Cₑ = {r['Ce']:.3f}

ขั้นที่ 3 — ระยะโซนขอบ z, y
  ด้านแคบ = min({B}, {L}) = {r['narrow']} m
  z = min(0.10×{r['narrow']}, 0.40×{r['h']:.2f}) = {r['z_raw']:.2f} m → ≥ max(0.04×{r['narrow']}, 1.00) → z = {r['z']:.2f} m
  y = max(6, 2×{r['z']:.2f}) = {r['y']:.2f} m

ขั้นที่ 4 — pᵢ = Iw · q · Cₑ · Cgi · Cpi
  pᵢ(Cpi={cpi_lo}) = {r['Iw']} × {kg(r['q']):.2f} × {r['Ce']:.3f} × {CGI} × ({cpi_lo}) = {kg(r['pi_neg']):.2f} kg/m²
  pᵢ(Cpi={cpi_hi}) = {r['Iw']} × {kg(r['q']):.2f} × {r['Ce']:.3f} × {CGI} × ({cpi_hi}) = {kg(r['pi_pos']):.2f} kg/m²

ขั้นที่ 5 — p = Iw · q · Cₑ · (Cg·Cp),  p_net = p − pᵢ
  ตัวคูณร่วม = {r['Iw']} × {kg(r['q']):.2f} × {r['Ce']:.3f} = {pf:.2f} kg/m²
"""

    def zone_lines(rows):
        return "\n".join(
            f"  Zone {z['zone']:<3}: p = {pf:.1f}×({z['cgcp']:.2f}) = {kg(z['p']):7.1f} ({sign(z['p'])})"
            f"  |  p_net = {kg(z['net_neg']):7.1f} ({sign(z['net_neg'])}) / {kg(z['net_pos']):7.1f} ({sign(z['net_pos'])})"
            for z in rows)

    sheet += f"\n  กรณีที่ 1 (Transverse) — มุมหลังคา {SLOPE_LABELS[roof_slope]}\n" + zone_lines(r["case1"])
    sheet += "\n\n  กรณีที่ 2 (Longitudinal) — ทุกมุมหลังคาใช้ค่าเดียว\n" + zone_lines(r["case2"])
    st.code(sheet, language=None)
    st.caption(f"p_net สองค่าคือผลจาก Cpi = {cpi_lo} / {cpi_hi} · หน่วย kg/m²")

# ---------------- design summary ----------------
with tab_design:
    direction = st.radio("ทิศทางลม", ["trans", "parallel"], horizontal=True,
                         format_func=lambda k: {"trans": "ลมตั้งฉากสันหลังคา (LC1 vs LC2)",
                                                "parallel": "ลมขนานสันหลังคา (LC3 vs LC4)"}[k])
    st.info("เทียบเฉพาะ 2 LC ของทิศที่เลือก เพื่อคงความสัมพันธ์ว่าแรงทุกโซนเกิดพร้อมกันในเฟรมเดียวกัน")
    crit = r["crit_trans"] if direction == "trans" else r["crit_parallel"]
    df = crit_frame(crit)
    st.dataframe(
        df.style.map(lambda v: f"color: {POS}; font-weight: 600", subset=["แรงกดวิกฤต (kg/m²)"])
        .map(lambda v: f"color: {NEG}; font-weight: 600", subset=["แรงดูดวิกฤต (kg/m²)"])
        .format({"แรงกดวิกฤต (kg/m²)": "{:+.1f}", "แรงดูดวิกฤต (kg/m²)": "{:.1f}"}, na_rep="—"),
        hide_index=True, width="stretch")
    st.image(str(DOCS / ("zone_case1.png" if direction == "trans" else "zone_case2.png")), width=520)

# ---------------- reference ----------------
with tab_ref:
    st.markdown("""
เอกสารอ้างอิงสูตรตามมาตรฐาน **มยผ. 1311-50** — วิธี Envelope / Static Procedure สำหรับอาคารเตี้ย

**1. หน่วยแรงลมอ้างอิง** `V̄ = V₅₀` (ทั่วไป) หรือ `V̄ = T_F · V₅₀` (รวมไต้ฝุ่น) · `q = ½ · ρ · V̄²` (ρ = 1.25 kg/m³, หาร 9.81 → kg/m²)

**2. Cₑ (หัวข้อ 3.4)** — A: `(z/10)^0.28` [1.0–2.5] · B: `0.5·(z/12.7)^0.5` [0.5–2.5] · C: `0.4·(z/30)^0.72` [0.4–2.5]
โดย `z = h = (H_eave + H_ridge)/2 ≥ 6 m`

**3. การกระโชก** — `Cg = 2.0` (รวมในตาราง Cg·Cp แล้ว), `Cgi = 2.0`

**4. Iw (ตาราง 2-2)** — น้อย 0.8 · ปกติ 1.0 · มาก 1.15 · สูงมาก 1.15 · ด้านการใช้งาน 0.75 ทุกประเภท

**5. ภายใน** `pᵢ = Iw · q · Cₑ · Cgi · Cpi` — กรณี 1: −0.15/0.0 · กรณี 2: −0.45/0.3 · กรณี 3: −0.7/0.7

**6. ภายนอก/สุทธิ** `p = Iw · q · Cₑ · (Cg·Cp)` · `p_net = p − pᵢ` (บวก = กด, ลบ = ดูด/ยก)

**9. โซนขอบ (หัวข้อ 4.1)** `z = min(0.10·ด้านแคบ, 0.40·h) ≥ max(0.04·ด้านแคบ, 1 m)` · `y = max(6 m, 2z)`
""")
    st.markdown("**7. Cg·Cp — กรณีที่ 1 ลมตั้งฉากสันหลังคา**")
    st.image(str(DOCS / "zone_case1.png"), width=520)
    st.dataframe(pd.DataFrame(CASE1_TABLE, index=CASE1_ZONES).T.rename(index=SLOPE_LABELS),
                 width="stretch")
    st.caption("1/1E = ผนังต้นลม · 2/2E = หลังคาต้นลม · 3/3E = หลังคาท้ายลม · 4/4E = ผนังท้ายลม")
    st.markdown("**8. Cg·Cp — กรณีที่ 2 ลมขนานสันหลังคา**")
    st.image(str(DOCS / "zone_case2.png"), width=520)
    st.dataframe(pd.DataFrame([CASE2_VALUES], columns=CASE2_ZONES, index=["0°–90°"]),
                 width="stretch")
    st.caption("1–4 (+E) = หลังคา · 5/5E = ผนังต้นลม (endwall) · 6/6E = ผนังท้ายลม (endwall)")

st.divider()
st.caption("เครื่องมือช่วยคำนวณเบื้องต้น — ผู้ใช้ต้องตรวจสอบตามมาตรฐาน มยผ. 1311-50 ก่อนนำไปออกแบบจริง")
