import streamlit as st
import subprocess
import sys
import os
import shutil
import time
import re
import copy
import pandas as pd

import config

st.set_page_config(
    page_title="Prompt Evaluator · Indium",
    page_icon="https://www.indium.tech/wp-content/uploads/2025/04/favicon-3.png",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── THEME ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; }

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background: #0A0A0A !important;
    color: #7d7f7c !important;
    font-family: 'DM Sans', sans-serif !important;
}

[data-testid="stSidebar"]    { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }
footer { display: none !important; }
#MainMenu { display: none !important; }
header[data-testid="stHeader"] { display: none !important; }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: #111; }
::-webkit-scrollbar-thumb { background: #F4610A; border-radius: 2px; }

/* ── Topbar ── */
.indium-topbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 18px 48px;
    background: #0D0D0D;
    border-bottom: 1px solid #1E1E1E;
    position: sticky; top: 0; z-index: 999;
}
.indium-topbar img { height: 36px; }
.indium-topbar-badge {
    font-family: 'Syne', sans-serif; font-size: 11px; font-weight: 700;
    letter-spacing: 0.15em; text-transform: uppercase;
    color: #F4610A; background: rgba(244,97,10,0.1);
    border: 1px solid rgba(244,97,10,0.3);
    padding: 5px 14px; border-radius: 20px;
}

/* ── Hero ── */
.indium-hero {
    padding: 56px 48px 40px;
    background: linear-gradient(135deg, #0D0D0D 0%, #111111 50%, #0D0D0D 100%);
    border-bottom: 1px solid #1A1A1A;
    position: relative; overflow: hidden;
}
.indium-hero::before {
    content: ''; position: absolute; top: -80px; right: -80px;
    width: 400px; height: 400px;
    background: radial-gradient(circle, rgba(244,97,10,0.08) 0%, transparent 70%);
    pointer-events: none;
}
.indium-hero-eyebrow {
    font-family: 'Syne', sans-serif; font-size: 11px; font-weight: 700;
    letter-spacing: 0.2em; text-transform: uppercase;
    color: #F4610A; margin-bottom: 12px;
}
.indium-hero h1 {
    font-family: 'Syne', sans-serif; font-size: 40px; font-weight: 800;
    color: #FFFFFF; line-height: 1.1; margin: 0 0 12px;
}
.indium-hero h1 span { color: #F4610A; }
.indium-hero-sub { font-size: 15px; color: #777; font-weight: 300; max-width: 520px; }

/* ── Content wrapper ── */
.indium-content { padding: 40px 48px; }

/* ── Cards ── */
.upload-card-title {
    font-family: 'Syne', sans-serif; font-size: 13px; font-weight: 700;
    letter-spacing: 0.12em; text-transform: uppercase;
    margin-left: 24px;
    color: #F4610A; margin-bottom: 16px;
}

/* ── API key input ── */
[data-testid="stTextInput"] input {
    background: #0D0D0D !important;
    border: 1.5px solid #2A2A2A !important;
    border-radius: 8px !important;
    color: #CCC !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 13px !important;
    padding: 12px 16px !important;
    transition: border-color 0.2s !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: rgba(244,97,10,0.6) !important;
    box-shadow: 0 0 0 2px rgba(244,97,10,0.1) !important;
}
[data-testid="stTextInput"] input::placeholder { color: #444 !important; }
[data-testid="stTextInput"] label {
    font-family: 'Syne', sans-serif !important;
    font-size: 11px !important; font-weight: 700 !important;
    letter-spacing: 0.12em !important; text-transform: uppercase !important;
    color: #F4610A !important;
}

/* ── Key status badges ── */
.key-badge {
    display: inline-flex; align-items: center; gap: 6px;
    font-family: 'Syne', sans-serif; font-size: 11px; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase;
    padding: 5px 12px; border-radius: 20px; margin-top: 8px;
}
.key-custom  { color: #F4610A; background: rgba(244,97,10,0.1);  border: 1px solid rgba(244,97,10,0.3); }
.key-default { color: #28C840; background: rgba(40,200,64,0.1);  border: 1px solid rgba(40,200,64,0.2); }
.key-missing { color: #FF5F57; background: rgba(255,95,87,0.1);  border: 1px solid rgba(255,95,87,0.25); }

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    background: #0D0D0D !important; border: 1.5px dashed #2A2A2A !important;
    border-radius: 10px !important; padding: 20px !important;
}
[data-testid="stFileUploader"]:hover { border-color: rgba(244,97,10,0.5) !important; }
[data-testid="stFileUploaderDropzone"] { background: transparent !important; }
[data-testid="stFileUploaderDropzoneInstructions"] span,
[data-testid="stFileUploaderDropzoneInstructions"] p { color: #555 !important; }

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #F4610A, #D4500A) !important;
    color: #FFFFFF !important; border: none !important;
    font-family: 'Syne', sans-serif !important; font-weight: 700 !important;
    font-size: 13px !important; letter-spacing: 0.08em !important;
    text-transform: uppercase !important; padding: 14px 32px !important;
    border-radius: 8px !important; cursor: pointer !important;
    transition: all 0.2s !important;
    box-shadow: 0 4px 20px rgba(244,97,10,0.25) !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #FF7020, #F4610A) !important;
    box-shadow: 0 6px 28px rgba(244,97,10,0.4) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:disabled {
    background: #1A1A1A !important;
    color: #444 !important; box-shadow: none !important;
    cursor: not-allowed !important; transform: none !important;
}
.stButton > button[kind="secondary"] {
    background: transparent !important; border: 1px solid #2A2A2A !important;
    color: #999 !important; box-shadow: none !important;
}
.stButton > button[kind="secondary"]:hover {
    border-color: #F4610A !important; color: #F4610A !important;
}
[data-testid="stDownloadButton"] > button {
    background: linear-gradient(135deg, #F4610A, #D4500A) !important;
    color: white !important; font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important; font-size: 13px !important;
    letter-spacing: 0.08em !important; text-transform: uppercase !important;
    border: none !important; border-radius: 8px !important;
    padding: 14px 32px !important;
    box-shadow: 0 4px 20px rgba(244,97,10,0.25) !important;
}

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: #111111 !important; border: 1px solid #1E1E1E !important;
    border-radius: 10px !important; padding: 20px 24px !important;
}
[data-testid="stMetricLabel"] p {
    font-family: 'Syne', sans-serif !important; font-size: 10px !important;
    font-weight: 700 !important; letter-spacing: 0.15em !important;
    text-transform: uppercase !important; color: #555 !important;
}
[data-testid="stMetricValue"] {
    font-family: 'Syne', sans-serif !important; font-size: 32px !important;
    font-weight: 800 !important; color: #FFFFFF !important;
}
[data-testid="stMetricDelta"] { display: none !important; }

/* ── Progress ── */
[data-testid="stProgressBar"] > div > div {
    background: linear-gradient(90deg, #F4610A, #FF8040) !important;
    border-radius: 2px !important;
}
[data-testid="stProgressBar"] > div {
    background: #1A1A1A !important;
    border-radius: 2px !important;
    height: 4px !important;
}
.stProgress {
    padding-left: 24px !important;
    padding-top: 24px;
}

/* ── Log window ── */
.log-container {
    background: #080808; border: 1px solid #1A1A1A;
    border-radius: 10px; overflow: hidden;
}
.log-header {
    background: #0F0F0F; border-bottom: 1px solid #1A1A1A;
    padding: 12px 20px; display: flex; align-items: center; gap: 8px;
}
.log-dot { width: 8px; height: 8px; border-radius: 50%; }
.log-dot-r { background: #FF5F57; }
.log-dot-y { background: #FEBC2E; }
.log-dot-g { background: #28C840; }
.log-title {
    font-family: 'Syne', sans-serif; font-size: 11px; font-weight: 700;
    letter-spacing: 0.12em; text-transform: uppercase; color: #444; margin-left: 6px;
}

/* ── Misc ── */
hr { border: none !important; border-top: 1px solid #1A1A1A !important; margin: 32px 0 !important; }

.section-header {
    font-family: 'Syne', sans-serif; font-size: 11px; font-weight: 700;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: #F4610A; margin-bottom: 20px; margin-left: 24px;
    display: flex; align-items: center; gap: 10px;
}
.section-header::after {
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, #1E1E1E, transparent);
}

.stSuccess > div {
    background: rgba(40,200,80,0.08) !important;
    border: 1px solid rgba(40,200,80,0.2) !important; border-radius: 8px !important;
}
.stInfo > div {
    background: rgba(244,97,10,0.06) !important;
    border: 1px solid #1E1E1E !important; border-radius: 8px !important; color: #666 !important;
}
[data-testid="stDataFrame"] {
    background: #0D0D0D !important; border: 1px solid #1E1E1E !important;
    border-radius: 10px !important; overflow: hidden !important;
}

.status-pill {
    display: inline-flex; align-items: center; gap: 6px;
    font-family: 'Syne', sans-serif; font-size: 11px; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase;
    padding: 5px 12px; border-radius: 20px;
}
.status-ready { color: #28C840; background: rgba(40,200,64,0.1); border: 1px solid rgba(40,200,64,0.2); }
.status-idle  { color: #555; background: rgba(255,255,255,0.04); border: 1px solid #222; }
.pulse {
    width: 6px; height: 6px; border-radius: 50%; background: #28C840;
    animation: pulse 1.5s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.4; transform: scale(0.8); }
}
/* Prevent browser save-password prompt on API key field */
[data-testid="stTextInput"] input {
    autocomplete: off;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<script>
    // Runs after Streamlit renders — finds the API key input and
    // sets autocomplete=off so browsers don't offer to save it.
    const observer = new MutationObserver(() => {
        const inputs = document.querySelectorAll('[data-testid="stTextInput"] input');
        inputs.forEach(el => {
            el.setAttribute('autocomplete', 'off');
            el.setAttribute('data-form-type', 'other');
        });
    });
    observer.observe(document.body, { childList: true, subtree: true });
</script>
""", unsafe_allow_html=True)


# ─── TOPBAR ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="indium-topbar">
    <img src="https://www.indium.tech/wp-content/uploads/2025/04/logo.svg" alt="Indium" />
    <span class="indium-topbar-badge">L&amp;D Prompt Evaluator</span>
</div>
""", unsafe_allow_html=True)

# ─── HERO ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="indium-hero">
    <div class="indium-hero-eyebrow">AI-Powered Assessment</div>
    <h1>Prompt <span>Evaluator</span><br>Dashboard</h1>
    <p class="indium-hero-sub">Upload submissions, run automated scoring, and download graded results — all in one place.</p>
</div>
""", unsafe_allow_html=True)


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def count_cached_rows(total_rows: int) -> set:
    """
    Return the set of row indices that already have a cache file.
    Used to pre-seed the progress bar on retry runs.
    """
    cache_dir = getattr(config, "CACHE_DIR", ".eval_cache")
    cached = set()
    if not os.path.exists(cache_dir):
        return cached
    for i in range(total_rows):
        if os.path.exists(os.path.join(cache_dir, f"row_{i:04d}.json")):
            cached.add(i)
    return cached


# ─── CONTENT ──────────────────────────────────────────────────────────────────
st.markdown('<div class="indium-content">', unsafe_allow_html=True)

if "eval_done" not in st.session_state:
    st.session_state.eval_done = False
    st.session_state.eval_time = ""
    st.session_state.eval_logs = ""

# ── API Key ───────────────────────────────────────────────────────────────────
st.markdown('<div class="upload-card-title">🔑 API Key</div>', unsafe_allow_html=True)

user_api_key = st.text_input(
    "Google API Key",
    type="password",
    placeholder="Paste your Gemini API key here, or leave blank to use the configured default",
    help="Your key is never stored. It is passed directly to the evaluation process and discarded after the run.",
    label_visibility="collapsed",
)

# Resolve active key — user-supplied takes priority over the env default
env_default_key  = os.environ.get("API_KEY", "").strip()
user_api_key     = user_api_key.strip()
active_api_key   = user_api_key if user_api_key else env_default_key

# Show which key source is active
if user_api_key:
    st.markdown(
        '<span class="key-badge key-custom">⚡ Using your API key</span>',
        unsafe_allow_html=True,
    )
elif env_default_key:
    st.markdown(
        '<span class="key-badge key-default">✓ Using configured default key</span>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<span class="key-badge key-missing">✗ No API key available — paste one above</span>',
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── Upload + Cache ────────────────────────────────────────────────────────────
col_upload, col_cache = st.columns([3, 1], gap="large")

with col_upload:
    st.markdown('<div class="upload-card-title">📂 Upload Submissions</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        "Drop your Excel file here",
        type=["xlsx"],
        label_visibility="collapsed",
    )

with col_cache:
    st.markdown('<div class="upload-card-title">🗄 Cache</div>', unsafe_allow_html=True)
    cache_dir = getattr(config, "CACHE_DIR", ".eval_cache")
    if os.path.exists(cache_dir):
        st.markdown('<span class="status-pill status-ready"><span class="pulse"></span>Cache Active</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-pill status-idle">No Cache</span>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑 Clear Cache", key="clear_cache", type="secondary"):
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            st.success("Cache cleared.")
        else:
            st.info("Cache is already empty.")

# ── Empty state ───────────────────────────────────────────────────────────────
if not uploaded_file:
    st.markdown("""
    <div style="text-align:center; padding:64px 0; color:#333;">
        <div style="font-size:48px; margin-bottom:16px;">⬆</div>
        <div style="font-family:'Syne',sans-serif; font-size:13px; letter-spacing:0.15em;
             text-transform:uppercase; color:#444;">Upload a file to begin evaluation</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# Save to disk
temp_input_path = "temp_submissions.xlsx"
with open(temp_input_path, "wb") as f:
    f.write(uploaded_file.getbuffer())

# ── File info strip ───────────────────────────────────────────────────────────
try:
    df_preview = pd.read_excel(temp_input_path)
    total_rows = len(df_preview)
    col_count  = len(df_preview.columns)
except Exception:
    total_rows = 1
    col_count  = 0

st.markdown(f"""
<div style="display:flex; gap:24px; align-items:center; margin-bottom:28px;
     background:#111; border:1px solid #1E1E1E; border-radius:10px; padding:16px 24px;">
    <div style="color:#F4610A; font-size:20px;">📄</div>
    <div>
        <div style="font-family:'Syne',sans-serif; font-size:12px; font-weight:700;
             color:#FFF; letter-spacing:0.05em;">{uploaded_file.name}</div>
        <div style="font-size:12px; color:#555; margin-top:2px;">{total_rows} rows &nbsp;·&nbsp; {col_count} columns</div>
    </div>
    <div style="margin-left:auto;">
        <span class="status-pill status-ready"><span class="pulse"></span>Ready</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Run button ────────────────────────────────────────────────────────────────
_, btn_col, _ = st.columns([2, 1, 2])
with btn_col:
    no_key = not active_api_key
    start  = st.button(
        "🚀 Run Evaluation",
        type="primary",
        use_container_width=True,
        disabled=no_key,
    )
    if no_key:
        st.markdown(
            '<div style="text-align:center; font-size:11px; color:#555; margin-top:8px;">'
            'Paste an API key above to enable</div>',
            unsafe_allow_html=True,
        )

if start:
    st.session_state.eval_done = False

    st.markdown('<div class="section-header" style="margin-top:32px;">Live Execution Log</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="log-container">
      <div class="log-header">
        <div class="log-dot log-dot-r"></div>
        <div class="log-dot log-dot-y"></div>
        <div class="log-dot log-dot-g"></div>
        <span class="log-title">stdout · evaluation process</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Pre-count cached rows so the progress bar starts at the right position
    completed_rows = count_cached_rows(total_rows)
    cached_count   = len(completed_rows)
    initial_pct    = min(cached_count / max(total_rows, 1), 1.0)

    if cached_count > 0:
        progress_bar = st.progress(
            initial_pct,
            text=f"Resuming · {cached_count} already cached · {cached_count} / {total_rows} rows"
        )
    else:
        progress_bar = st.progress(0, text=f"Initialising · 0 / {total_rows} rows")

    scrollable = st.container(height=380)
    log_box    = scrollable.empty()

    start_time = time.perf_counter()
    logs: list[str] = []

    # ── Build subprocess environment — inject active API key ─────────────────
    # Inherits the full current environment then overrides EVALUATOR_API_KEY.
    # config.py reads EVALUATOR_API_KEY first, falling back to API_KEY,
    # so this transparently overrides whichever key was configured by default.
    subprocess_env = copy.copy(os.environ)
    subprocess_env["EVALUATOR_API_KEY"] = active_api_key

    process = subprocess.Popen(
        [sys.executable, "-u", "-X", "utf8", "main.py", "--csv", temp_input_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        bufsize=1,
        env=subprocess_env,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    for line in iter(process.stdout.readline, ""):
        if not line:
            break
        msg = line.strip()
        if not msg:
            continue

        logs.append(msg)

        match = re.search(r"Row (\d+)", msg)
        if match and any(x in msg for x in ["Cache HIT", "total=", "FLAGGED", "Failed writing cache", "Cache read failed"]):
            completed_rows.add(int(match.group(1)))
            pct = min(len(completed_rows) / max(total_rows, 1), 1.0)
            progress_bar.progress(
                pct,
                text=f"Evaluating · {len(completed_rows)} / {total_rows} rows"
            )

        display = logs[-1000:] if len(logs) > 1000 else logs
        log_box.code("\n".join(display), language="log")

    process.wait()

    elapsed    = time.perf_counter() - start_time
    mins, secs = divmod(int(elapsed), 60)

    progress_bar.progress(1.0, text=f"✅ Completed {total_rows} rows · {mins}m {secs}s")

    st.session_state.eval_logs = "\n".join(logs)
    st.session_state.eval_time = f"{mins}m {secs}s"
    st.session_state.eval_done = True
    log_box.code(st.session_state.eval_logs, language="log")


# ── Results ───────────────────────────────────────────────────────────────────
if st.session_state.eval_done and os.path.exists(config.OUTPUT_PATH):

    st.markdown(f"""
    <div style="background:rgba(40,200,80,0.07); border:1px solid rgba(40,200,80,0.2);
         border-radius:10px; padding:16px 24px; margin:28px 0 24px;
         display:flex; align-items:center; gap:12px;">
        <span style="font-size:20px;">✅</span>
        <div>
            <div style="font-family:'Syne',sans-serif; font-weight:700; color:#28C840; font-size:13px;">
                Evaluation Complete
            </div>
            <div style="font-size:12px; color:#555; margin-top:2px;">
                Finished in {st.session_state.eval_time}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    df        = pd.read_excel(config.OUTPUT_PATH)
    grade_col = "Grade & Total Score"

    def grade_count(keyword: str) -> int:
        if grade_col in df.columns:
            return len(df[df[grade_col].astype(str).str.contains(keyword, na=False)])
        return 0

    st.markdown('<div class="section-header">Score Summary</div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Rows",  len(df))
    c2.metric("Excellent",   grade_count("Excellent"))
    c3.metric("Good",        grade_count("Good"))
    c4.metric("Needs Impr.", grade_count("Needs Imp"))
    c5.metric("Poor",        grade_count("Poor"))
    c6.metric("Flagged",     grade_count("Flagged"))

    st.markdown('<div class="section-header" style="margin-top:32px;">Results Preview</div>', unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True, height=420)

    st.markdown("<br>", unsafe_allow_html=True)
    _, dl_col, _ = st.columns([2, 1, 2])
    with dl_col:
        with open(config.OUTPUT_PATH, "rb") as f:
            st.download_button(
                label="📥 Download Results",
                data=f,
                file_name="indium_evaluated_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )

st.markdown('</div>', unsafe_allow_html=True)