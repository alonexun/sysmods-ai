# -*- coding: utf-8 -*-
"""PMHT .mh 材料文件解析器 + ReadThermo/ReadProps/GetTypeProperty 等价逻辑。

逐项对应 MATLAB @MetalHydride/{ReadThermo,ReadProps,GetTypeProperty}.m：
- WtPct / H/M → wMax
- Dehydriding dH/dS/slope→A、多平台 centers/widths/minSpans
- Hydriding 9 种数据组合（Tc/ln(Pa/Pd)/dH/dS）补全 + Tc 计算 + 滞后假定
- Omega = 2·R·Tc（正则溶液）
- Assumed 标志全套（与 UQ 置信度分级同构）
"""
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

R_GAS = 8.314          # J/mol.K
TREF = 298.0           # K
M_H2_G_PER_MOL = 2.016  # g/mol
MH2_KG_PER_MOL = M_H2_G_PER_MOL / 1000.0

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..",
                        "kb", "materials", "pmht")

# ---------------- GetTypeProperty 默认值表（MATLAB 原版逐值） ----------------
TYPE_DEFAULTS = {
    "tc": {"AB": 502, "AB2": 451, "AB3": 343, "AB5": 586, "COMPLEX": 2330,
           "MG": 663, "SS": 473, "OTHER": 600},
    "slope": {"AB": 0.92, "AB2": 1.25, "AB3": 1.2, "AB5": 0.43, "MG": 0.02,
              "SS": 0.33, "OTHER": 0.0},
    "hysteresis": {"AB": 0.51, "AB2": 0.54, "AB3": 0.29, "AB5": 0.39,
                   "SS": 0.80, "OTHER": 0.0},
    "ca hydriding": {"AB": 7523, "AB2": 473, "AB3": 24.4, "AB5": 620,
                     "COMPLEX": 2e9, "MG": 9.8e9, "OTHER": 57},
    "ca dehydriding": {"AB": 99, "AB2": 58, "AB5": 90, "COMPLEX": 1.8e9,
                       "MG": 10, "AB3": None, "OTHER": 9.57},
    "ea hydriding": {"AB": 40038, "AB2": 24900, "AB3": 25730, "AB5": 30867,
                     "MG": 132000, "COMPLEX": 91520, "OTHER": 20000},
    "ea dehydriding": {"AB": 30161, "AB2": 22100, "AB5": 28250, "AB3": None,
                       "COMPLEX": 93070, "MG": 41000, "OTHER": 16420},
    "keff": {"AB2": 1.6, "AB5": 1.6, "COMPLEX": 0.42, "MG": 0.48, "OTHER": 1.0},
    "cp": {"AB": 502, "AB2": 419, "AB5": 419, "COMPLEX": 1075, "MG": 889,
           "OTHER": 500},
    "rho": {"AB": 6500, "AB2": 6700, "AB5": 8200, "COMPLEX": 1800, "MG": 1750,
            "OTHER": 6600},
}

# AB3 的两个缺省在 MATLAB 表中缺失，落到 OTHER
for k in ("ca dehydriding", "ea dehydriding"):
    if TYPE_DEFAULTS[k].get("AB3") is None:
        TYPE_DEFAULTS[k]["AB3"] = TYPE_DEFAULTS[k]["OTHER"]


def get_type_default(prop: str, hydride_type: str) -> float:
    t = (hydride_type or "").upper()
    table = TYPE_DEFAULTS[prop.lower()]
    return float(table.get(t, table.get("OTHER", table.get("OTHER"))))


# ---------------- 文本解析 ----------------
@dataclass
class Zone:
    name: str
    entries: Dict[str, object] = field(default_factory=dict)
    children: List["Zone"] = field(default_factory=list)


_ENTRY_RE = re.compile(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$")


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def _parse_value(raw: str):
    s = raw.strip()
    if not s:
        return ""
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    s2 = s.strip("[]").strip()
    parts = [p for p in re.split(r"[,\s]+", s2) if p]
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return s  # 字符串值
    if len(nums) == 1:
        return nums[0]
    return nums  # 数组（多平台 dH/dS/centers/widths/minSpans）


def parse_zones(lines: List[str]) -> Zone:
    """递归解析大括号分区（ReadZones 等价）。顶层行为一个虚拟根 Zone。"""
    root = Zone(name="__root__")

    def feed(zone: Zone, idx: int, depth: int) -> int:
        i = idx
        while i < len(lines):
            raw = _strip_comment(lines[i])
            s = raw.strip()
            if not s:
                i += 1
                continue
            if s == "{":
                i = feed(pending_child, i + 1, depth + 1)
                pending_child = None
                continue
            if s == "}":
                return i + 1
            m = _ENTRY_RE.match(s)
            if m and not s.endswith("{"):
                zone.entries[m.group(1).strip().lower()] = _parse_value(m.group(2))
                i += 1
                continue
            # 裸名（可能是子区名）
            pending_child = Zone(name=s)
            zone.children.append(pending_child)
            i += 1
        return i

    pending_child = None
    i = 0
    while i < len(lines):
        raw = _strip_comment(lines[i])
        s = raw.strip()
        if not s:
            i += 1
            continue
        if s == "{":
            i = feed(pending_child, i + 1, 1) if pending_child is not None else i + 1
            pending_child = None
            continue
        if s == "}":
            i += 1
            continue
        m = _ENTRY_RE.match(s)
        if m and not s.endswith("{"):
            root.entries[m.group(1).strip().lower()] = _parse_value(m.group(2))
            i += 1
            continue
        pending_child = Zone(name=s)
        root.children.append(pending_child)
        i += 1
    return root


def _child(zone: Zone, name: str) -> Optional[Zone]:
    name_l = name.lower()
    for c in zone.children:
        if c.name.strip().lower() == name_l:
            return c
    return None


def _entries(zone: Zone, name: str) -> Dict[str, object]:
    c = _child(zone, name)
    return c.entries if c else {}


def _as_list(v) -> List[float]:
    if v is None:
        return []
    if isinstance(v, list):
        return [float(x) for x in v]
    return [float(v)]


# ---------------- 数据结构 ----------------
@dataclass
class ModeThermo:
    dH: List[float] = field(default_factory=list)   # J/mol H2（负值，文件约定）
    dS: List[float] = field(default_factory=list)   # J/mol.K（负值）
    from_isotherms: bool = False


@dataclass
class KineticsSide:
    assumed: bool = True
    Ca: float = 0.0
    Ea: float = 0.0
    pFcn: str = "log"          # log | linear | normalized linear
    wFcn: str = "1st order"    # 1st order | 0th order


@dataclass
class HydrideSpec:
    """解析后的材料卡（ReadThermo/ReadProps 完成态）。"""
    name: str
    filename: str
    hydride_type: str
    elements: Dict[str, float]
    molar_mass_g_per_mol: float          # W（金属部分）
    w_max: float                          # kg_H/kg_M（质量分数 0-1）
    hm: float                             # H/金属原子比
    des: ModeThermo
    abss: ModeThermo
    A: List[float]                        # 平台斜率（J/mol），abs=des
    centers: List[float]
    widths: List[float]
    min_spans: List[float]
    Tc: List[float]
    omega: List[float]                   # 正则溶液 = 2·R·Tc
    n_plateaus: int
    thermo_level: int                     # 0/1/2（MATLAB Level）
    tc_assumed: List[bool]
    hysteresis_assumed: List[bool]
    slope_assumed: bool
    kEff: float; kEff_assumed: bool
    Cp: float; Cp_assumed: bool           # J/kg.K（金属骨架）
    rho: float; rho_assumed: bool          # kg/m3
    kin_abs: KineticsSide
    kin_des: KineticsSide
    references: Dict[str, Dict] = field(default_factory=dict)


# ---------------- ReadThermo 等价 ----------------
def _read_thermo(thermo_zone: Zone, elements, w_metal_g: float, name: str,
                 hydride_type: str) -> dict:
    ents = thermo_zone.entries
    out = {}
    # —— 容量 ——
    if "weight percent" in ents:
        wt_pct = float(ents["weight percent"]) / 100.0
        hm = None
        if "h/m" in ents:
            hm = float(ents["h/m"])
    elif "h/m" in ents:
        hm = float(ents["h/m"])
        wt_pct = hm * 1.008 / (hm * 1.008 + w_metal_g)
    else:
        raise ValueError(f"{name}: hydride capacity not provided (ReadThermo 等价)")
    if hm is None:
        hm = wt_pct * w_metal_g / (1.008 * (1.0 - wt_pct))
    out["w_max"], out["hm"] = wt_pct, hm

    # —— Dehydriding（必填）——
    des_e = _entries(thermo_zone, "Dehydriding")
    if not des_e:
        raise ValueError(f"{name}: Dehydriding section missing")
    des = ModeThermo(dH=_as_list(des_e.get("dh")), dS=_as_list(des_e.get("ds")),
                     from_isotherms=bool(des_e.get("from isotherms", False)))
    if len(des.dH) == 0 or len(des.dS) == 0:
        raise ValueError(f"{name}: Dehydriding DH/DS required")
    n = len(des.dH)
    if n != len(des.dS):
        raise ValueError(f"{name}: DH/DS 长度不一致")
    centers = _as_list(des_e.get("centers", [0.5]))
    widths = _as_list(des_e.get("widths", [1.0]))
    min_spans = _as_list(des_e.get("minspans", []))
    if n > 1 and ("centers" not in des_e or "widths" not in des_e or "minspans" not in des_e):
        raise ValueError(f"{name}: 多平台需 centers/widths/minSpans")
    if n == 1 and not centers:
        centers, widths = [0.5], [1.0]
    if len(centers) != n or len(widths) != n:
        raise ValueError(f"{name}: centers/widths 长度与平台数不符")
    if min(c - w / 2 for c, w in zip(centers, widths)) < -1e-12 or \
       max(c + w / 2 for c, w in zip(centers, widths)) > 1 + 1e-12:
        raise ValueError(f"{name}: centers/widths 越出 [0,1]")
    # 斜率 A = slope·R·Ts（缺省按类型）
    slope_assumed = False
    if "slope" in des_e:
        slope_l = _as_list(des_e["slope"])
        if len(slope_l) == 1 and n > 1:
            slope_l = slope_l * n
        ts = _as_list(des_e.get("ts", [])) or [TREF] * n
        if len(ts) == 1 and n > 1:
            ts = ts * n
        A = [s * R_GAS * t for s, t in zip(slope_l, ts)]
        slope_assumed = any(s != s for s in slope_l)  # NaN 支持
        A = [get_type_default("slope", hydride_type) * R_GAS * TREF
             if s != s else a for s, a in zip(slope_l, A)]
    else:
        A = [get_type_default("slope", hydride_type) * R_GAS * TREF] * n
        slope_assumed = True
    out.update(des=des, centers=centers, widths=widths, min_spans=min_spans,
               A=A, slope_assumed=slope_assumed)

    # —— Hydriding（9 组合逻辑）——
    abs_e = _entries(thermo_zone, "Hydriding")
    Tc = [None] * n
    hyst_assumed = [True] * n
    tc_assumed = [True] * n
    level = 0
    if abs_e:
        ab_dH = _as_list(abs_e.get("dh", []))
        ab_dS = _as_list(abs_e.get("ds", []))
        ab_Tc = _as_list(abs_e.get("tc", []))
        ab_ln = _as_list(abs_e.get("ln(pa/pd)", []))
        T_meas = _as_list(abs_e.get("t", [])) or [TREF] * n
        if len(T_meas) == 1 and n > 1:
            T_meas = T_meas * n          # 标量 T 广播到每平台（MATLAB .*basis 语义）
        if len(ab_dH) == 1 and n > 1: ab_dH = ab_dH * n
        if len(ab_dS) == 1 and n > 1: ab_dS = ab_dS * n
        if not ab_Tc: ab_Tc = [float("nan")] * n
        if len(ab_Tc) == 1 and n > 1: ab_Tc = ab_Tc * n
        if not ab_ln: ab_ln = [float("nan")] * n
        if len(ab_ln) == 1 and n > 1: ab_ln = ab_ln * n
        hyst_default = get_type_default("hysteresis", hydride_type)
        tc_default = get_type_default("tc", hydride_type)
        hyst = [h if h == h else hyst_default for h in ab_ln]
        hyst_assumed = [h != h for h in ab_ln]
        for p in range(n):
            has_h = len(ab_dH) > p and ab_dH[p] == ab_dH[p]
            has_s = len(ab_dS) > p and ab_dS[p] == ab_dS[p]
            if has_h and has_s:            # ID 3
                hyst_assumed[p] = False
                level = max(level, 2)
                Tc[p] = None  # 稍后由 dH/dS 差计算
                tc_assumed[p] = True
            elif has_h:                     # ID 6/2
                ab_dS_p = des.dS[p] + (ab_dH[p] - des.dH[p]) / T_meas[p] - R_GAS * hyst[p]
                if len(ab_dS) <= p:
                    ab_dS.append(ab_dS_p)
                level = max(level, 1)
            elif has_s:                     # ID 5/1
                ab_dH_p = des.dH[p] + T_meas[p] * (R_GAS * hyst[p] + ab_dS[p] - des.dS[p])
                if len(ab_dH) <= p:
                    ab_dH.append(ab_dH_p)
                level = max(level, 1)
            elif ab_Tc[p] == ab_Tc[p]:      # 有 Tc（或 Tc+ln）→ ID 12/8
                Tc[p] = ab_Tc[p]
                tc_assumed[p] = False
                dh = des.dH[p] + R_GAS * hyst[p] / (1.0 / T_meas[p] - 1.0 / Tc[p])
                ds = des.dS[p] + (dh - des.dH[p]) / Tc[p]
                if len(ab_dH) <= p: ab_dH.append(dh)
                if len(ab_dS) <= p: ab_dS.append(ds)
            else:                           # ID 4/0：仅 ln(Pa/Pd) 或全无
                Tc[p] = tc_default
                dh = des.dH[p] + R_GAS * hyst[p] / (1.0 / T_meas[p] - 1.0 / Tc[p])
                ds = des.dS[p] + (dh - des.dH[p]) / Tc[p]
                if len(ab_dH) <= p: ab_dH.append(dh)
                if len(ab_dS) <= p: ab_dS.append(ds)
        # Tc 更新（可计算时）
        for p in range(n):
            if (Tc[p] is None) and tc_assumed[p]:
                dS_diff = ab_dS[p] - des.dS[p]
                if abs(dS_diff) > 1e-15:
                    Tc[p] = (ab_dH[p] - des.dH[p]) / dS_diff
                    tc_assumed[p] = False
                else:
                    Tc[p] = tc_default
        ab = ModeThermo(dH=ab_dH[:n], dS=ab_dS[:n],
                        from_isotherms=bool(abs_e.get("from isotherms", False)))
    else:
        # 完全假定（按类型默认）
        hyst_default = get_type_default("hysteresis", hydride_type)
        tc_default = get_type_default("tc", hydride_type)
        Tc = [tc_default] * n
        ab_dH, ab_dS = [], []
        for p in range(n):
            dh = des.dH[p] + R_GAS * hyst_default / (1.0 / TREF - 1.0 / tc_default)
            ab_dH.append(dh)
            ab_dS.append(des.dS[p] + (dh - des.dH[p]) / tc_default)
        ab = ModeThermo(dH=ab_dH, dS=ab_dS, from_isotherms=False)
        hyst_assumed = [True] * n
        level = 0
    # Tc 兜底
    Tc = [tc_default if (t is None or t != t) else t for t in Tc]
    out.update(abss=ab, Tc=Tc, tc_assumed=tc_assumed,
               hysteresis_assumed=hyst_assumed, level=level,
               omega=[2.0 * R_GAS * t for t in Tc])
    return out


_ATOMIC_MASS = {  # 常用元素（解析 Elements 用）
    "La": 138.905, "Ce": 140.116, "Pr": 140.908, "Nd": 144.242, "Pm": 145,
    "Sm": 150.36, "Eu": 151.964, "Gd": 157.25, "Tb": 158.925, "Dy": 162.5,
    "Ho": 164.93, "Er": 167.259, "Tm": 168.934, "Yb": 173.045, "Lu": 174.967,
    "Y": 88.906, "Ti": 47.867, "Zr": 91.224, "Hf": 178.49, "V": 50.942,
    "Nb": 92.906, "Ta": 180.948, "Cr": 51.996, "Mo": 95.95, "W": 183.84,
    "Mn": 54.938, "Fe": 55.845, "Co": 58.933, "Ni": 58.693, "Cu": 63.546,
    "Zn": 65.38, "Al": 26.982, "Mg": 24.305, "Ca": 40.078, "Sr": 87.62,
    "Ba": 137.327, "Si": 28.085, "Sn": 118.71, "Ge": 72.63, "Ga": 69.723,
    "In": 114.818, "B": 10.81, "C": 12.011, "N": 14.007, "O": 15.999,
    "S": 32.06, "Se": 78.971, "Te": 127.6, "Bi": 208.98, "Sb": 121.76,
    "Pd": 106.42, "Rh": 102.906, "Ru": 101.07, "Pt": 195.084, "Ir": 192.217,
    "Os": 190.23, "Re": 186.207, "Ag": 107.868, "Au": 196.967,
    "Li": 6.94, "Na": 22.99, "K": 39.098, "Rb": 85.468, "Cs": 132.905,
    "Be": 9.012, "Mm": 140.0,  # Mm=混合稀土近似
}


def parse_mh_file(path: str) -> HydrideSpec:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    lines = text.splitlines()
    root = parse_zones(lines)

    ents = root.entries
    name = os.path.splitext(os.path.basename(path))[0]

    # Elements
    el_raw = str(ents.get("elements", ""))
    elements: Dict[str, float] = {}
    for m in re.finditer(r"([A-Za-z]{1,2})\s*:\s*([\d.]+)", el_raw):
        sym = m.group(1)
        if sym in _ATOMIC_MASS or sym not in ("H",):
            elements[sym] = float(m.group(2))
    if not elements:
        raise ValueError(f"{name}: No 'Elements' entry")
    w_metal = sum(_ATOMIC_MASS.get(s, 100.0) * v for s, v in elements.items())
    hydride_type = str(ents.get("type", "Other"))

    thermo_zone = _child(root, "Thermodynamics")
    if thermo_zone is None:
        raise ValueError(f"{name}: Thermodynamics section missing")
    th = _read_thermo(thermo_zone, elements, w_metal, name, hydride_type)

    # Properties（Assumed 标志 = ReadProps 等价）
    props_e = _entries(root, "Properties")
    keff = float(props_e.get("keff", float("nan")))
    keff_a = keff != keff
    if keff_a:
        keff = get_type_default("keff", hydride_type)
    cp = float(props_e.get("cp", float("nan")))
    cp_a = cp != cp
    if cp_a:
        cp = get_type_default("cp", hydride_type)
    rho = float(props_e.get("rho", float("nan")))
    rho_a = rho != rho
    if rho_a:
        rho = get_type_default("rho", hydride_type)

    # Kinetics（KineticsModel 构造等价：缺失侧按类型默认/镜像）
    kin_zone = _child(root, "Kinetics")
    abs_e = _entries(kin_zone, "Hydriding") if kin_zone else {}
    des_e = _entries(kin_zone, "Dehydriding") if kin_zone else {}

    def make_side(e: Dict, other: Optional[Dict], which: str) -> KineticsSide:
        need = ("ca", "ea", "pfcn", "wfcn")
        if all(k in e for k in need):
            return KineticsSide(assumed=False, Ca=float(e["ca"]), Ea=float(e["ea"]),
                                pFcn=str(e["pfcn"]).lower(), wFcn=str(e["wfcn"]).lower())
        if other and all(k in other for k in need):
            return KineticsSide(assumed=True, Ca=float(other["ca"]), Ea=float(other["ea"]),
                                pFcn=str(other["pfcn"]).lower(), wFcn=str(other["wfcn"]).lower())
        # 完全默认（按类型）
        if which == "hydriding":
            ca, ea = (get_type_default("ca hydriding", hydride_type),
                      get_type_default("ea hydriding", hydride_type))
        else:
            ca, ea = (get_type_default("ca dehydriding", hydride_type),
                      get_type_default("ea dehydriding", hydride_type))
        return KineticsSide(assumed=True, Ca=ca, Ea=ea, pFcn="log", wFcn="1st order")

    kin_abs = make_side(abs_e, des_e, "hydriding")
    kin_des = make_side(des_e, abs_e, "dehydriding")

    # References
    refs_zone = _child(root, "References")
    refs = {}
    if refs_zone:
        for c in refs_zone.children:
            refs[c.name] = {k: v for k, v in c.entries.items()}

    return HydrideSpec(
        name=name, filename=os.path.basename(path), hydride_type=hydride_type,
        elements=elements, molar_mass_g_per_mol=w_metal,
        w_max=th["w_max"], hm=th["hm"],
        des=th["des"], abss=th["abss"], A=th["A"],
        centers=th["centers"], widths=th["widths"], min_spans=th["min_spans"],
        Tc=th["Tc"], omega=th["omega"], n_plateaus=len(th["des"].dH),
        thermo_level=th["level"], tc_assumed=th["tc_assumed"],
        hysteresis_assumed=th["hysteresis_assumed"], slope_assumed=th["slope_assumed"],
        kEff=keff, kEff_assumed=keff_a, Cp=cp, Cp_assumed=cp_a,
        rho=rho, rho_assumed=rho_a,
        kin_abs=kin_abs, kin_des=kin_des, references=refs,
    )


def list_materials(data_dir: str = None) -> List[str]:
    d = data_dir or os.path.abspath(DATA_DIR)
    return sorted(f for f in os.listdir(d) if f.endswith(".mh"))


def parse_mh_name(material_or_path: str, data_dir: str = None) -> str:
    """'La[1]Ni[5]' → 完整路径。"""
    d = data_dir or os.path.abspath(DATA_DIR)
    if os.path.isfile(material_or_path):
        return material_or_path
    p = os.path.join(d, material_or_path if material_or_path.endswith(".mh")
                     else material_or_path + ".mh")
    if not os.path.isfile(p):
        raise FileNotFoundError(f"材料文件不存在: {p}")
    return p


def load_hydride(material: str, data_dir: str = None) -> "Hydride":
    from .hydride import Hydride
    return Hydride(parse_mh_file(parse_mh_name(material, data_dir)))
