import json
import os
import math
from collections import Counter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE, "non_conversion_analysis.json")
CHART_PATH = os.path.join(BASE, "non_conversion_pie_chart.png")

CATEGORY_DESCRIPTIONS = {
    "EXISTING_PATIENT":    "Existing Patient — caller already has a relationship with the clinic; not seeking a new appointment",
    "OTHER":               "Other — vendor solicitations, referral requirements, record requests, or miscellaneous calls",
    "WRONG_NUMBER":        "Wrong Number — caller intended to reach a different business (e.g. Costco, Beltone, AudioNova)",
    "CALL_BACK_NEEDED":    "Call Back Needed — staff promised to follow up; appointment not booked during the call",
    "PRICE_CONCERN":       "Price Concern — caller deterred by out-of-pocket costs or lack of insurance coverage",
    "NOT_READY":           "Not Ready — caller gathering information for themselves or a family member; not ready to book",
    "VOICEMAIL":           "Voicemail — call went to voicemail with no live conversation",
    "SHORT_CALL":          "Short Call — connection or audio issues prevented a real conversation",
    "STAFF_HANDLING":      "Staff Handling — opportunity missed due to inflexibility or failure to book during the call",
    "COMPETITOR":          "Competitor — caller mentioned going to or returning to a competing provider",
}

COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
    "#1abc9c", "#e67e22", "#34495e", "#e91e63", "#00bcd4",
]


def generate_pie_chart(json_path=JSON_PATH):
    with open(json_path) as f:
        results = json.load(f)

    category_counts = Counter(r["category"] for r in results)
    total = len(results)

    categories = [cat for cat, _ in category_counts.most_common()]
    sizes = [category_counts[cat] for cat in categories]
    colors = COLORS[: len(categories)]

    fig, ax = plt.subplots(figsize=(16, 10))
    fig.patch.set_facecolor("#f9f9f9")
    ax.set_facecolor("#f9f9f9")

    wedges, _ = ax.pie(
        sizes,
        labels=None,
        colors=colors,
        startangle=140,
        radius=1.0,
        wedgeprops={"linewidth": 1.5, "edgecolor": "white"},
    )

    # --- Pointer annotations on each wedge ---
    for wedge, cat, count in zip(wedges, categories, sizes):
        pct = count / total * 100
        angle = (wedge.theta1 + wedge.theta2) / 2
        angle_rad = math.radians(angle)

        # Point on wedge edge
        x_inner = 0.72 * math.cos(angle_rad)
        y_inner = 0.72 * math.sin(angle_rad)

        # Label anchor outside the pie
        x_outer = 1.28 * math.cos(angle_rad)
        y_outer = 1.28 * math.sin(angle_rad)

        ha = "left" if math.cos(angle_rad) >= 0 else "right"
        x_text = 1.32 * math.cos(angle_rad)
        y_text = 1.32 * math.sin(angle_rad)

        # Only annotate slices large enough to be readable
        if pct >= 2.0:
            ax.annotate(
                f"{cat}\n{count} calls ({pct:.1f}%)",
                xy=(x_inner, y_inner),
                xytext=(x_text, y_text),
                ha=ha,
                va="center",
                fontsize=7.5,
                fontweight="bold",
                color="#222222",
                arrowprops=dict(
                    arrowstyle="-",
                    color="#888888",
                    lw=0.9,
                    connectionstyle="arc3,rad=0.0",
                ),
            )

    # --- Legend with full descriptions ---
    legend_labels = [
        f"{cat}:  {CATEGORY_DESCRIPTIONS.get(cat, cat).split('—', 1)[-1].strip()}"
        for cat in categories
    ]
    legend = ax.legend(
        wedges,
        legend_labels,
        title="Category Descriptions",
        title_fontsize=9,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.30),
        ncol=2,
        fontsize=8,
        frameon=True,
        framealpha=0.9,
        edgecolor="#cccccc",
    )
    legend.get_title().set_fontweight("bold")

    ax.set_title(
        f"Labyrinth Audiology Missed Call Conversion\n{total} non-converting calls analyzed",
        fontsize=15,
        fontweight="bold",
        pad=24,
        color="#1a1a1a",
    )

    plt.tight_layout()
    plt.savefig(CHART_PATH, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"Chart saved to: {CHART_PATH}")


if __name__ == "__main__":
    generate_pie_chart()
