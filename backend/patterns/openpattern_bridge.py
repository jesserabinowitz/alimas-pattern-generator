"""
OpenPattern bridge
==================
Wraps fmetivier/OpenPattern (GPL-3.0) classes so they fit into our
FastAPI /generate and /preview routes.

OpenPattern renders via matplotlib. We capture that as SVG (preview)
or PDF (generate) bytes.

Measurement translation
-----------------------
OpenPattern uses French measurement keys. This module translates our
English API keys to French before calling OpenPattern.
"""

from __future__ import annotations
import io
import matplotlib
matplotlib.use("Agg")   # must be set before any other matplotlib import
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import OpenPattern as OP

A0_W_CM  = 84.1
A0_H_CM  = 118.9
MARGIN_CM  = 1.5   # breathing room inside each page edge
OVERLAP_CM = 2.0   # overlap strip between pages for alignment


# ------------------------------------------------------------------
# English → French measurement key translation
# ------------------------------------------------------------------
EN_TO_FR: dict[str, str] = {
    "bust":                 "tour_poitrine",
    "waist":                "tour_taille",
    "hip":                  "tour_bassin",
    "hip_height":           "hauteur_bassin",
    "back_length":          "longueur_dos",
    "front_length":         "longueur_devant",
    "shoulder":             "longueur_epaule",
    "across_back":          "carrure_dos",
    "across_chest":         "carrure_devant",
    "neck":                 "tour_encolure",
    "bust_span":            "ecart_poitrine",
    "hps_to_bust":          "hauteur_poitrine",
    "sleeve_length":        "longueur_manche",
    "elbow_height":         "hauteur_coude",
    "arm_circumference":    "tour_bras",
    "wrist":                "tour_poignet",
    "waist_to_floor":       "longueur_taille_terre",
    "waist_to_knee":        "hauteur_taille_genou",
    "rise":                 "montant",
    "thigh":                "tour_cuisse",
    "knee":                 "tour_genou",
    "ankle":                "tour_cheville",
    "shoulder_to_shoulder": "largeur_epaule",
    "height":               "stature",
}


def _translate(measurements: dict) -> dict:
    """Convert English measurement keys to OpenPattern French keys."""
    out = {}
    for k, v in measurements.items():
        fr = EN_TO_FR.get(k, k)   # pass through unknown keys as-is
        out[fr] = float(v)
    return out


# ------------------------------------------------------------------
# Garment registry
# ------------------------------------------------------------------
# Each entry: (OP class, default pname, gender, style, extra_kwargs)
# pname selects the base size to load — we override with user measurements.
# extra_kwargs are passed directly to the constructor (e.g. model, collar_style).
_GARMENTS: dict[str, tuple] = {
    # ── Bodice / tops ──────────────────────────────────────────────
    "op_bodice":        (OP.Basic_Bodice,     "W38G",  "w", "Gilewska",   {}),
    "op_shirt":         (OP.Shirt,            "M40mC", "m", "Chiappetta", {}),
    "op_waistcoat":     (OP.Waist_Coat,       "M44G",  "m", "Gilewska",   {}),
    # ── Skirts ────────────────────────────────────────────────────
    "op_skirt":         (OP.Basic_Skirt,      "W6C",   "w", "Chiappetta", {}),
    "op_skirt_aline":   (OP.Skirt_transform,  "W38G",  "w", "Donnanno",   {"model": "A-Line"}),
    "op_skirt_flared":  (OP.Skirt_transform,  "W38G",  "w", "Donnanno",   {"model": "Flared-A-Line"}),
    "op_culotte":       (OP.Culotte,          "W40D",  "w", "Donnanno",   {}),
    # ── Trousers / bottoms ────────────────────────────────────────
    "op_trousers":      (OP.Basic_Trousers,   "M44D",  "m", "Donnanno",   {}),
    "op_bermudas":      (OP.Bermudas,         "M44D",  "m", None,         {}),
    "op_flared_pants":  (OP.Flared_pants,     "M44D",  "m", None,         {}),
    # ── Accessories ───────────────────────────────────────────────
    "op_collar":        (OP.Collars,          "W38G",  "w", "Gilewska",   {"collar_style": "Officer"}),
    "op_cuffs":         (OP.Cuffs,            "W38G",  "w", "Gilewska",   {"cuff_style": "Simple"}),
    "op_bowtie":        (OP.Bowtie,           "M40G",  "m", "Gilewska",   {}),
}


def _make_pattern(garment_id: str, measurements: dict):
    """Instantiate an OpenPattern object with user measurements.

    OpenPattern calculates geometry inside __init__, so we must supply the
    correct measurements *before* construction.  We do this by temporarily
    patching get_measurements_sql so it merges the user's values on top of
    the base-size dict, then restoring the original method.
    """
    cls, pname, gender, style, extra = _GARMENTS[garment_id]
    fr_m = _translate(measurements)

    original_get = OP.Pattern.get_measurements_sql

    def _patched_get(self, pname_arg=None):
        base = original_get(self, pname)
        base.update(fr_m)
        return base

    OP.Pattern.get_measurements_sql = _patched_get
    try:
        kwargs = {"pname": pname, "gender": gender, **extra}
        if style is not None:
            kwargs["style"] = style
        obj = cls(**kwargs)
    finally:
        OP.Pattern.get_measurements_sql = original_get

    return obj


_INFO_PREFIXES = ("Style:", "Gender:", "Measurements:", "Pattern:")


def _strip_info_text() -> None:
    """Remove OpenPattern's built-in info block (Style/Gender/Measurements/Pattern labels)."""
    for ax in plt.gcf().get_axes():
        for txt in ax.texts[:]:
            if any(txt.get_text().startswith(p) for p in _INFO_PREFIXES):
                txt.remove()


def render_svg(garment_id: str, measurements: dict) -> bytes:
    """Return SVG bytes for browser preview."""
    obj = _make_pattern(garment_id, measurements)
    obj.draw(save=False)
    _strip_info_text()
    buf = io.BytesIO()
    plt.savefig(buf, format="svg", bbox_inches="tight")
    plt.close("all")
    buf.seek(0)
    return buf.read()


def _save_page(pdf: PdfPages, fig, ax, x0, x1, y0, y1,
               page_label: str | None = None,
               paper_size: str = "A0",
               garment_name: str = "") -> None:
    """Crop the axes to the given viewport and append one PDF page."""
    w_cm = abs(x1 - x0)
    h_cm = abs(y1 - y0)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_axis_off()
    fig.set_size_inches(w_cm / 2.54, h_cm / 2.54)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    if page_label:
        ax.text(
            x0 + 0.5, y1 - 0.5, page_label,
            fontsize=5, color="#888888", va="top", ha="left",
            transform=ax.transData,
        )
    # Prominent paper size + garment name in top-left corner
    label_x = x0 + 0.8
    ax.text(
        label_x, y1 - 0.8, paper_size,
        fontsize=48, color="#111111", va="top", ha="left",
        fontweight="bold", transform=ax.transData,
    )
    if garment_name:
        ax.text(
            label_x, y1 - 4.0, garment_name,
            fontsize=20, color="#333333", va="top", ha="left",
            transform=ax.transData,
        )
    pdf.savefig(fig)


def render_pdf(garment_id: str, measurements: dict) -> bytes:
    """Return a 1:1 scale PDF.

    Patterns that fit within A0 (84.1 × 118.9 cm) are single-page.
    Larger patterns are split into two pages with a 2 cm overlap strip
    and a dashed registration line so the sheets can be aligned and taped.
    """
    garment_name = next(
        (g["label"] for g in OPENPATTERN_GARMENTS if g["id"] == garment_id),
        garment_id,
    )

    obj = _make_pattern(garment_id, measurements)
    obj.draw(save=False)
    _strip_info_text()

    ax  = plt.gca()
    fig = plt.gcf()
    ax.set_aspect("equal", adjustable="datalim")

    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    w_cm = abs(x1 - x0)
    h_cm = abs(y1 - y0)

    # Add a small margin so content isn't flush with the page edge
    x0 -= MARGIN_CM; x1 += MARGIN_CM
    y0 -= MARGIN_CM; y1 += MARGIN_CM
    w_cm += 2 * MARGIN_CM
    h_cm += 2 * MARGIN_CM

    buf = io.BytesIO()

    if w_cm <= A0_W_CM and h_cm <= A0_H_CM:
        # ── Single A0 page ────────────────────────────────────────────────
        with PdfPages(buf) as pdf:
            _save_page(pdf, fig, ax, x0, x1, y0, y1,
                       paper_size="A0", garment_name=garment_name)
    else:
        # ── Split into two pages ──────────────────────────────────────────
        # Always split vertically (x-axis) so each sheet gets one side.
        with PdfPages(buf) as pdf:
            mid = (x0 + x1) / 2
            ax.axvline(mid, color="#cc0000", linewidth=0.4,
                       linestyle=(0, (4, 3)), zorder=10)
            ax.text(mid + 0.3, (y0 + y1) / 2, "▲ align here ▲",
                    fontsize=4.5, color="#cc0000", rotation=90,
                    va="center", ha="left", zorder=10)
            _save_page(pdf, fig, ax,
                       x0, mid + OVERLAP_CM, y0, y1,
                       "Sheet 1 of 2 — overlap at red line",
                       paper_size="A1", garment_name=garment_name)
            _save_page(pdf, fig, ax,
                       mid - OVERLAP_CM, x1, y0, y1,
                       "Sheet 2 of 2 — overlap at red line",
                       paper_size="A1", garment_name=garment_name)

    plt.close("all")
    buf.seek(0)
    return buf.read()


# ------------------------------------------------------------------
# Garment metadata for /garments endpoint
# ------------------------------------------------------------------
_SKIRT_MEASUREMENTS = [
    {"key": "waist",          "label": "Waist circumference",    "unit": "cm", "required": True},
    {"key": "hip",            "label": "Hip circumference",      "unit": "cm", "required": True},
    {"key": "hip_height",     "label": "Hip height (waist→hip)", "unit": "cm", "required": True},
    {"key": "waist_to_floor", "label": "Waist to floor",         "unit": "cm", "required": True},
]

_TROUSER_MEASUREMENTS = [
    {"key": "waist",          "label": "Waist circumference",    "unit": "cm", "required": True},
    {"key": "hip",            "label": "Hip circumference",      "unit": "cm", "required": True},
    {"key": "hip_height",     "label": "Hip height (waist→hip)", "unit": "cm", "required": True},
    {"key": "rise",           "label": "Rise (waist→crotch)",    "unit": "cm", "required": True},
    {"key": "waist_to_floor", "label": "Waist to floor",         "unit": "cm", "required": True},
    {"key": "thigh",          "label": "Thigh circumference",    "unit": "cm", "required": False},
]

_BODICE_MEASUREMENTS = [
    {"key": "bust",           "label": "Bust/chest circumference",    "unit": "cm", "required": True},
    {"key": "waist",          "label": "Waist circumference",         "unit": "cm", "required": True},
    {"key": "hip",            "label": "Hip circumference",           "unit": "cm", "required": True},
    {"key": "back_length",    "label": "Back length (nape→waist)",    "unit": "cm", "required": True},
    {"key": "shoulder",       "label": "Shoulder length",             "unit": "cm", "required": False},
    {"key": "across_back",    "label": "Across back",                 "unit": "cm", "required": False},
    {"key": "across_chest",   "label": "Across chest",                "unit": "cm", "required": False},
    {"key": "neck",           "label": "Neck circumference",          "unit": "cm", "required": False},
]

OPENPATTERN_GARMENTS = [
    # ── Bodice / tops ──────────────────────────────────────────────────────
    {
        "id": "op_bodice",
        "label": "Bodice Block",
        "description": "Fitted bodice block — Gilewska method.",
        "engine": "openpattern",
        "measurements": _BODICE_MEASUREMENTS,
    },
    {
        "id": "op_shirt",
        "label": "Shirt",
        "description": "Shirt block with collar and sleeves — Chiappetta method.",
        "engine": "openpattern",
        "measurements": [
            {"key": "bust",          "label": "Bust/chest circumference", "unit": "cm", "required": True},
            {"key": "waist",         "label": "Waist circumference",      "unit": "cm", "required": True},
            {"key": "back_length",   "label": "Back length",              "unit": "cm", "required": True},
            {"key": "shoulder",      "label": "Shoulder length",          "unit": "cm", "required": True},
            {"key": "sleeve_length", "label": "Sleeve length",            "unit": "cm", "required": True},
            {"key": "neck",          "label": "Neck circumference",       "unit": "cm", "required": False},
            {"key": "wrist",         "label": "Wrist circumference",      "unit": "cm", "required": False},
        ],
    },
    {
        "id": "op_waistcoat",
        "label": "Waistcoat",
        "description": "Waistcoat / vest block — Gilewska method.",
        "engine": "openpattern",
        "measurements": _BODICE_MEASUREMENTS,
    },
    # ── Skirts ────────────────────────────────────────────────────────────
    {
        "id": "op_skirt",
        "label": "Basic Skirt",
        "description": "Fitted straight skirt block — Chiappetta method.",
        "engine": "openpattern",
        "measurements": _SKIRT_MEASUREMENTS,
    },
    {
        "id": "op_skirt_aline",
        "label": "A-Line Skirt",
        "description": "A-line skirt transformed from the basic block — Donnanno method.",
        "engine": "openpattern",
        "measurements": _SKIRT_MEASUREMENTS,
    },
    {
        "id": "op_skirt_flared",
        "label": "Flared Skirt",
        "description": "Flared A-line skirt — Donnanno method.",
        "engine": "openpattern",
        "measurements": _SKIRT_MEASUREMENTS,
    },
    {
        "id": "op_culotte",
        "label": "Culottes",
        "description": "Wide-leg culotte trousers — Donnanno method.",
        "engine": "openpattern",
        "measurements": _TROUSER_MEASUREMENTS,
    },
    # ── Trousers / bottoms ────────────────────────────────────────────────
    {
        "id": "op_trousers",
        "label": "Basic Trousers",
        "description": "Trouser block — Donnanno method.",
        "engine": "openpattern",
        "measurements": _TROUSER_MEASUREMENTS,
    },
    {
        "id": "op_bermudas",
        "label": "Bermuda Shorts",
        "description": "Knee-length shorts block — Donnanno method.",
        "engine": "openpattern",
        "measurements": _TROUSER_MEASUREMENTS,
    },
    {
        "id": "op_flared_pants",
        "label": "Flared Trousers",
        "description": "Flared / wide-leg trouser block — Donnanno method.",
        "engine": "openpattern",
        "measurements": _TROUSER_MEASUREMENTS,
    },
    # ── Accessories ───────────────────────────────────────────────────────
    {
        "id": "op_collar",
        "label": "Officer Collar",
        "description": "Stand collar block — Gilewska method.",
        "engine": "openpattern",
        "measurements": [
            {"key": "neck",        "label": "Neck circumference", "unit": "cm", "required": True},
            {"key": "back_length", "label": "Back length",        "unit": "cm", "required": False},
        ],
    },
    {
        "id": "op_cuffs",
        "label": "Cuffs",
        "description": "Simple shirt cuff block — Gilewska method.",
        "engine": "openpattern",
        "measurements": [
            {"key": "wrist",          "label": "Wrist circumference", "unit": "cm", "required": True},
            {"key": "arm_circumference", "label": "Arm circumference","unit": "cm", "required": False},
        ],
    },
    {
        "id": "op_bowtie",
        "label": "Bow Tie",
        "description": "Butterfly bow tie block — Gilewska method.",
        "engine": "openpattern",
        "measurements": [
            {"key": "neck", "label": "Neck circumference", "unit": "cm", "required": True},
        ],
    },
]
