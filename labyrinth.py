import json
import os
import time
from collections import Counter
from google.cloud import bigquery, storage
from dotenv import load_dotenv
import anthropic
from concurrent.futures import ThreadPoolExecutor, as_completed
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

load_dotenv()

_sa_info = json.loads(os.environ["GCS_SERVICE_ACCOUNT"])
bq_client = bigquery.Client.from_service_account_info(_sa_info)
gcs_client = storage.Client.from_service_account_info(_sa_info)
ai_client = anthropic.Anthropic(api_key=os.environ["ANTROPIC_API_KEY"])

BUCKET = "transcripts-json"
ADVERTISER = "Calgary Ear Centre"


def run_query(sql):
    return list(bq_client.query(sql).result())


# --- Schema inspection (run once to discover column names) ---
def inspect_schema():
    rows = run_query("""
        SELECT column_name, data_type
        FROM `project-demo-2-482101.ClinicData.INFORMATION_SCHEMA.COLUMNS`
        WHERE table_name = 'transactions'
        ORDER BY ordinal_position
    """)
    print("\n=== transactions schema ===")
    for r in rows:
        print(f"  {r.column_name}: {r.data_type}")


# --- Analysis ---
def total_calls():
    rows = run_query("""
        SELECT COUNT(*) AS total_calls
        FROM `project-demo-2-482101.ClinicData.transactions`
        WHERE advertiser_name = 'Calgary Ear Center'
        AND during_hours = 'Yes'
    """)
    print("\n=== Total Calls ===")
    print(f"  {rows[0].total_calls}")


def converted_calls():
    rows = run_query("""
        SELECT
            COUNTIF(Appointment_Booked__Conversion_ = 1)         AS appt_booked,
            COUNTIF(Service_Appointment_Booked__Conversion_ = 1) AS service_appt_booked,
            COUNTIF(AI_Appointment_Booked = 1)                   AS ai_appt_booked,
            COUNTIF(
                Appointment_Booked__Conversion_ = 1
                OR Service_Appointment_Booked__Conversion_ = 1
                OR AI_Appointment_Booked = 1
            ) AS any_conversion
        FROM `project-demo-2-482101.ClinicData.transactions`
        WHERE advertiser_name = 'Calgary Ear Centre'
          AND during_hours = 'Yes'
    """)
    r = rows[0]
    print("\n=== Converted Calls ===")
    print(f"  Appointment Booked:                {r.appt_booked}")
    print(f"  Service Appointment Booked:        {r.service_appt_booked}")
    print(f"  AI Appointment Booked:             {r.ai_appt_booked}")
    print(f"  Any Conversion (union of above):   {r.any_conversion}")


def keywords_by_conversion():
    rows = run_query("""
        SELECT
            AC.click_view_keyword_info_text AS keyword,
            COUNT(*) AS total_calls,
            COUNTIF(
                T.Appointment_Booked__Conversion_ = 1
                OR T.Service_Appointment_Booked__Conversion_ = 1
                OR T.AI_Appointment_Booked = 1
            ) AS converted_calls,
            ROUND(COUNTIF(
                T.Appointment_Booked__Conversion_ = 1
                OR T.Service_Appointment_Booked__Conversion_ = 1
                OR T.AI_Appointment_Booked = 1
            ) / COUNT(*) * 100, 2) AS conversion_rate_pct
        FROM `project-demo-2-482101.ClinicData.transactions` AS T
        INNER JOIN `project-demo-2-482101.ClinicData.ad_clicks` AS AC
            ON T.gclid = AC.click_view_gclid
        WHERE T.advertiser_name = 'Calgary Ear Center'
          AND T.during_hours = "Yes"
          AND AC.click_view_keyword_info_text IS NOT NULL
        GROUP BY keyword
        ORDER BY converted_calls DESC
    """)
    print("\n=== Keywords by Conversion ===")
    print(f"  {'Keyword':<50} {'Total':>8} {'Converted':>10} {'Conv%':>8}")
    print("  " + "-" * 80)
    for r in rows:
        print(f"  {r.keyword:<50} {r.total_calls:>8} {r.converted_calls:>10} {r.conversion_rate_pct:>7}%")


# --- Non-conversion transcript analysis ---
def fetch_non_converting_calls():
    """Return list of (complete_call_id, duration, during_hours, call_sentiment) for non-converting calls."""
    rows = run_query(f"""
        SELECT
            complete_call_id,
            duration,
            during_hours,
            call_sentiment_overall_label,
            Opportunity,
            Non_Converting_Opportunity,
            Answered_by_Voicemail,
            Short_Call
        FROM `project-demo-2-482101.ClinicData.transactions`
        WHERE advertiser_name = '{ADVERTISER}'
          AND during_hours = 'Yes'
          AND COALESCE(Appointment_Booked__Conversion_, 0) != 1
          AND COALESCE(Service_Appointment_Booked__Conversion_, 0) != 1
          AND COALESCE(AI_Appointment_Booked, 0) != 1
          AND complete_call_id IS NOT NULL
          AND complete_call_id != ''
    """)
    return rows


def fetch_transcript(complete_call_id):
    """Download transcript JSON from GCS. Returns parsed dict or None."""
    try:
        bucket = gcs_client.bucket(BUCKET)
        blob = bucket.blob(f"{complete_call_id}.json")
        data = blob.download_as_text()
        return json.loads(data)
    except Exception:
        return None


def extract_transcript_text(transcript_json):
    """Pull readable text out of the transcript JSON regardless of exact schema."""
    if not transcript_json:
        return None
    # Try common transcript shapes
    if isinstance(transcript_json, str):
        return transcript_json
    if "transcript" in transcript_json:
        t = transcript_json["transcript"]
        if isinstance(t, str):
            return t
        if isinstance(t, list):
            lines = []
            for turn in t:
                speaker = turn.get("speaker", turn.get("role", "?"))
                text = turn.get("text", turn.get("content", ""))
                lines.append(f"{speaker}: {text}")
            return "\n".join(lines)
    if "turns" in transcript_json:
        lines = []
        for turn in transcript_json["turns"]:
            speaker = turn.get("speaker", "?")
            text = turn.get("text", "")
            lines.append(f"{speaker}: {text}")
        return "\n".join(lines)
    # Fallback: dump entire JSON as string
    return json.dumps(transcript_json)[:3000]


def analyze_batch(batch):
    """Send a batch of transcripts to Claude and get structured reasons for non-conversion."""
    numbered = "\n\n".join(
        f"--- Call {i+1} (id: {call_id}) ---\n{text[:2000]}"
        for i, (call_id, text) in enumerate(batch)
    )
    prompt = f"""You are analyzing call transcripts for an audiology clinic ({ADVERTISER}).
Each call below did NOT result in a booked appointment.

For each call, identify the PRIMARY reason it did not convert. Use one of these categories:
- VOICEMAIL: Call went to voicemail or was not answered
- SHORT_CALL: Call was too brief for a real conversation
- WRONG_NUMBER: Caller reached wrong business or wrong department
- PRICE_CONCERN: Caller expressed concern about cost or insurance
- NOT_READY: Caller was gathering information, not ready to book
- EXISTING_PATIENT: Already has an appointment or is an existing patient calling for another reason
- CALL_BACK_NEEDED: Staff said they would call back / follow-up needed
- COMPETITOR: Caller mentioned going elsewhere
- STAFF_HANDLING: Opportunity missed due to how staff handled the call
- OTHER: Any other reason (briefly explain)

Return a JSON array, one object per call, in this format:
{{"call_id": "...", "category": "...", "brief_reason": "one sentence"}}

Transcripts:
{numbered}"""

    for attempt in range(5):
        try:
            response = ai_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except anthropic.InternalServerError:
            if attempt == 4:
                raise
            wait = 2 ** (attempt + 1)
            print(f"  API error, retrying in {wait}s...")
            time.sleep(wait)
    text = response.content[0].text.strip()
    # Extract JSON array from response
    start = text.find("[")
    end = text.rfind("]") + 1
    return json.loads(text[start:end])


def analyze_non_conversions():
    print("\n=== Non-Conversion Transcript Analysis ===")

    print("  Fetching non-converting calls from BigQuery...")
    calls = fetch_non_converting_calls()
    print(f"  Found {len(calls)} non-converting calls.")

    print("  Downloading transcripts from GCS...")
    transcripts = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(fetch_transcript, r.complete_call_id): r.complete_call_id for r in calls}
        for future in as_completed(futures):
            call_id = futures[future]
            transcripts[call_id] = future.result()

    available = [
        (r.complete_call_id, text)
        for r in calls
        for text in [extract_transcript_text(transcripts.get(r.complete_call_id))]
        if text is not None
    ]
    missing = len(calls) - len(available)
    print(f"  Transcripts found: {len(available)}  |  Missing: {missing}")

    if not available:
        print("  No transcripts available to analyze.")
        return

    # Send to Claude in batches of 3
    batch_size = 3
    all_results = []
    skipped = 0
    for i in range(0, len(available), batch_size):
        batch = available[i:i + batch_size]
        print(f"  Analyzing calls {i+1}–{min(i+batch_size, len(available))} of {len(available)}...")
        try:
            results = analyze_batch(batch)
            all_results.extend(results)
        except Exception as e:
            print(f"  Skipping batch after repeated failures: {e}")
            skipped += len(batch)
    if skipped:
        print(f"  Warning: {skipped} calls skipped due to API errors.")

    # Aggregate by category
    category_counts = Counter(r["category"] for r in all_results)
    reasons_by_category = {}
    for r in all_results:
        reasons_by_category.setdefault(r["category"], []).append(r["brief_reason"])

    print("\n  --- Results by Category ---")
    for category, count in category_counts.most_common():
        pct = round(count / len(all_results) * 100, 1)
        print(f"\n  {category} ({count} calls, {pct}%)")
        for reason in reasons_by_category[category][:3]:
            print(f"    • {reason}")
        if len(reasons_by_category[category]) > 3:
            print(f"    ... and {len(reasons_by_category[category]) - 3} more")

    # Save full results to file
    base = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base, "non_conversion_analysis.json")
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n  Full results saved to: {json_path}")

    # Pie chart
    generate_pie_chart(category_counts, len(all_results), base)


def generate_pie_chart(category_counts, total, base):
    labels = []
    sizes = []
    for category, count in category_counts.most_common():
        pct = count / total * 100
        labels.append(f"{category}\n({count} calls, {pct:.1f}%)")
        sizes.append(count)

    colors = [
        "#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
        "#1abc9c", "#e67e22", "#34495e", "#e91e63", "#00bcd4",
    ]

    fig, ax = plt.subplots(figsize=(12, 8))
    wedges, texts = ax.pie(
        sizes,
        labels=None,
        colors=colors[: len(sizes)],
        startangle=140,
        wedgeprops={"linewidth": 1.5, "edgecolor": "white"},
    )

    ax.legend(
        wedges,
        labels,
        title="Categories",
        loc="center left",
        bbox_to_anchor=(1, 0, 0.5, 1),
        fontsize=10,
    )

    ax.set_title(
        f"{ADVERTISER} — Why Calls Didn't Convert\n({total} calls analyzed)",
        fontsize=14,
        fontweight="bold",
        pad=20,
    )

    chart_path = os.path.join(base, "non_conversion_pie_chart.png")
    plt.tight_layout()
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Pie chart saved to: {chart_path}")


if __name__ == "__main__":
    converted_calls()
    analyze_non_conversions()
    keywords_by_conversion()