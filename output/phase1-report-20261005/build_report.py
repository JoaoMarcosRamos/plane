"""Build docs/radar/PHASE_1_REPORT.html: embeds screenshots as JPEG data URIs and draws the test charts to scale.

    python3 output/phase1-report-20261005/build_report.py
"""

import base64
import html
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "output"
E2E = OUT / "e2e-symbiosis-20261005"
CLEAN = E2E / "radar-e2e-clean"

IMAGES = {
    "shell_today": CLEAN / "01-login-today.png",
    "e2e_created": CLEAN / "02-risk-created.png",
    "e2e_context": CLEAN / "03-context-selected.png",
    "e2e_proposals": CLEAN / "03-proposals.png",
    "e2e_conflict": CLEAN / "04-action-conflict.png",
    "e2e_risk_page": CLEAN / "06-risk-object-page.png",
    "e2e_action_page": CLEAN / "07-action-object-page.png",
    "e2e_member": CLEAN / "08-member-risk-review.png",
    "e2e_outsider": CLEAN / "10-outsider-object.png",
    "e2e_revoked": CLEAN / "12-authority-revoked.png",
    "prov_proposals": E2E / "13-proposals.png",
    "prov_after": E2E / "15-risk-after-provider.png",
    "config": OUT / "agent-config-20261004" / "ui-saved.png",
    "review_fixture": OUT / "risk-review-20261005" / "ui-review.jpg",
    "today_desktop": OUT / "today-20261005" / "today-desktop.png",
    "today_mobile": OUT / "today-20261005" / "today-mobile.png",
    "collab_author": OUT / "collaboration-20261005" / "ui-author.png",
    "collab_activity": OUT / "collaboration-20261005" / "ui-collaboration.png",
}

# Backend RADAR / frontend RADAR tests reported by each delivery (historical, overlapping scopes).
DELIVERIES = [
    ("0.5/0.6", 130, 42, "fim da Fase 0"),
    ("1.1/1.2", 149, 49, "Command Layer e provenance"),
    ("1.3", 177, None, "Agent Runtime; sem suíte frontend própria"),
    ("1.4", 199, 58, "Agent Config"),
    ("Val. geral", 202, 58, "passe geral de 04/10"),
    ("1.5", 229, 72, "Risk Review"),
    ("1.6", 234, 77, "Today; casos únicos"),
    ("1.7", 263, 92, "Colaboração; 4 integrações opt-in desativadas"),
    ("Bancada", 267, 92, "bancada da Fase 1; integrações ativas"),
    ("1.8", 272, 92, "E2E; inclui 5 testes de CORS"),
]


def dimensions(path: Path) -> tuple[int, int]:
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)], check=True, capture_output=True, text=True).stdout
    return int(re.search(r"pixelWidth: (\d+)", out).group(1)), int(re.search(r"pixelHeight: (\d+)", out).group(1))


def image_attrs(path: Path) -> str:
    """JPEG data URI, downscaled (never upscaled) to keep the page small, plus its real width/height."""
    limit = 1200 if path.name in {"ui-author.png", "ui-review.jpg"} else 1440
    width, _ = dimensions(path)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "image.jpg"
        command = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82"]
        if width > limit:
            command += ["--resampleWidth", str(limit)]
        subprocess.run([*command, str(path), "--out", str(target)], check=True, capture_output=True)
        out_w, out_h = dimensions(target)
        uri = "data:image/jpeg;base64," + base64.b64encode(target.read_bytes()).decode()
    return f'src="{uri}" width="{out_w}" height="{out_h}"'


def chart(kind: str) -> str:
    index = 1 if kind == "backend" else 2
    ymax, ticks = (300, [0, 100, 200, 300]) if kind == "backend" else (100, [0, 25, 50, 75, 100])
    left, right, top, base = 48, 904, 18, 196
    band = (right - left) / len(DELIVERIES)
    scale = (base - top) / ymax
    label = "testes backend RADAR" if kind == "backend" else "testes frontend RADAR"
    parts = [
        f'<svg class="ch" viewBox="0 0 920 236" role="img" aria-label="Barras: {label} aprovados por entrega, de {DELIVERIES[0][index]} na Fase 0 a {DELIVERIES[-1][index]} na 1.8.">'
    ]
    for tick in ticks:
        y = base - tick * scale
        cls = "base" if tick == 0 else "grid"
        parts.append(f'<line class="{cls}" x1="{left}" x2="{right}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="tick" x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">{tick}</text>')
    last = len(DELIVERIES) - 1
    for i, row in enumerate(DELIVERIES):
        name, value, note = row[0], row[index], row[3]
        cx = left + band * (i + 0.5)
        parts.append(f'<text class="cat" x="{cx:.1f}" y="{base + 20}" text-anchor="middle">{html.escape(name)}</text>')
        if value is None:
            parts.append(f'<text class="none" x="{cx:.1f}" y="{base - 6}" text-anchor="middle">—</text>')
            tip = f"{name} · sem suíte registrada"
        else:
            x, w, y = cx - 12, 24, base - value * scale
            parts.append(
                f'<path class="bar" data-i="{i}" d="M{x:.1f},{base} V{y + 4:.1f} Q{x:.1f},{y:.1f} {x + 4:.1f},{y:.1f} '
                f'H{x + w - 4:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + 4:.1f} V{base} Z"/>'
            )
            if i in (0, last):
                parts.append(f'<text class="val" x="{cx:.1f}" y="{y - 7:.1f}" text-anchor="middle">{value}</text>')
            tip = f"{name} · {value} {label} · {note}"
        parts.append(
            f'<rect class="hit" x="{cx - band / 2:.1f}" y="{top}" width="{band:.1f}" height="{base - top}" '
            f'tabindex="0" data-i="{i}" data-tip="{html.escape(tip, quote=True)}" aria-label="{html.escape(tip, quote=True)}"/>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def table() -> str:
    rows = "".join(
        f"<tr><td>{html.escape(n)}</td><td class=\"num\">{b}</td><td class=\"num\">{'—' if f is None else f}</td><td>{html.escape(note)}</td></tr>"
        for n, b, f, note in DELIVERIES
    )
    return (
        '<table><thead><tr><th scope="col">Entrega</th><th scope="col" class="num">Backend RADAR</th>'
        '<th scope="col" class="num">Frontend RADAR</th><th scope="col">Nota</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


def main():
    source = (HERE / "report.template.html").read_text(encoding="utf-8")
    source = re.sub(r'src="\{\{IMG:(\w+)\}\}"', lambda m: image_attrs(IMAGES[m.group(1)]), source)
    source = source.replace("{{CHART:backend}}", chart("backend")).replace("{{CHART:frontend}}", chart("frontend"))
    source = source.replace("{{CHART:table}}", table())
    missing = re.findall(r"\{\{[A-Z]+:\w+\}\}", source)
    if missing:
        raise SystemExit(f"Unresolved placeholders: {missing}")
    target = ROOT / "docs" / "radar" / "PHASE_1_REPORT.html"
    target.write_text(source, encoding="utf-8")
    print(f"{target} {target.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
