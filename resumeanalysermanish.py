import streamlit as st
import json, io
from datetime import datetime
from openai import OpenAI
import pypdf
import docx

st.set_page_config(page_title="AI Resume Screener", page_icon="🤖", layout="wide")

st.markdown("""
<style>
.stProgress > div > div > div > div { background-image: linear-gradient(90deg,#3b82f6,#8b5cf6); }
.candidate-card { border-radius: 10px; padding: 18px 20px; margin-bottom: 14px; border-left: 6px solid #475569; background: #1e1e2e; }
.score-pill { font-weight: 800; font-size: 1.4rem; padding: 6px 18px; border-radius: 30px; color: #0f172a; display:inline-block; }
.badge { padding: 3px 10px; border-radius: 6px; font-size: .75rem; font-weight: 700; color: #0f172a; margin-left: 8px; }
.tag { background:#334155; color:#e2e8f0; padding: 2px 10px; border-radius: 12px; font-size: .78rem; margin: 2px; display:inline-block;}
.tag.missing { background: #4c1d1d; color: #fca5a5; }
</style>
""", unsafe_allow_html=True)

st.title("🤖 AI Resume Screener")
st.caption("Upload resumes, paste a job description, get an AI-ranked, color-coded fit report.")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")
    model = st.selectbox("Model", ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"], index=0)
    st.caption("Your key is used only for this session and never stored.")
    st.divider()
    st.markdown("**Steps:**\n1. Enter API key\n2. Upload resumes\n3. Paste job description\n4. Click Analyze")

# ---------- Helpers ----------
def extract_text(file) -> str:
    name = file.name.lower()
    data = file.read()
    if name.endswith(".pdf"):
        reader = pypdf.PdfReader(io.BytesIO(data))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    if name.endswith(".docx"):
        d = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs)
    return data.decode("utf-8", errors="ignore")


def analyze_resume(client, model, resume_text, jd_text, filename):
    prompt = f"""You are an expert technical recruiter. Compare the RESUME against the JOB DESCRIPTION.
Return ONLY valid JSON (no markdown fences) with this exact schema:
{{
  "candidate_name": "string (extract from resume, or filename if not found)",
  "match_score": integer 0-100,
  "verdict": "Strong Fit" | "Good Fit" | "Partial Fit" | "Not a Fit",
  "strengths": ["..."],
  "gaps": ["..."],
  "key_skills_matched": ["..."],
  "missing_skills": ["..."],
  "experience_summary": "1-2 sentence summary",
  "recommendation": "1-2 sentence hiring recommendation"
}}

JOB DESCRIPTION:
{jd_text}

RESUME ({filename}):
{resume_text[:15000]}
"""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a precise JSON-only API. Output strictly valid JSON, no extra text."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    data["filename"] = filename
    return data


def score_color(score):
    if score >= 80: return "#16a34a"
    if score >= 60: return "#65a30d"
    if score >= 40: return "#d97706"
    return "#dc2626"


def verdict_color(v):
    return {"Strong Fit": "#16a34a", "Good Fit": "#65a30d", "Partial Fit": "#d97706", "Not a Fit": "#dc2626"}.get(v, "#6b7280")


def build_html_report(results, jd_text, errors):
    rows = ""
    for r in results:
        strengths = "".join(f"<li>{s}</li>" for s in r.get("strengths", []))
        gaps = "".join(f"<li>{g}</li>" for g in r.get("gaps", []))
        matched = "".join(f'<span class="tag">{s}</span>' for s in r.get("key_skills_matched", []))
        missing = "".join(f'<span class="tag missing">{s}</span>' for s in r.get("missing_skills", []))
        rows += f"""
        <div class="candidate-card" style="border-left-color:{r['score_color']}">
          <div style="display:flex;justify-content:space-between;flex-wrap:wrap;align-items:center;">
            <h3>#{r['rank']} {r['candidate_name']} <span class="badge" style="background:{r['badge_color']}">{r['verdict']}</span><br>
            <small style="color:#94a3b8">{r['filename']}</small></h3>
            <div class="score-pill" style="background:{r['score_color']}">{r['match_score']}%</div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:10px;">
            <div><h4 style="color:#93c5fd">✅ Strengths</h4><ul>{strengths}</ul></div>
            <div><h4 style="color:#93c5fd">⚠️ Gaps</h4><ul>{gaps}</ul></div>
          </div>
          <div style="margin-top:8px;"><h4 style="color:#93c5fd">🎯 Matched Skills</h4>{matched}</div>
          <div style="margin-top:8px;"><h4 style="color:#93c5fd">❌ Missing Skills</h4>{missing}</div>
          <div style="margin-top:10px;padding-top:10px;border-top:1px solid #334155;">
            <b>Summary:</b> {r.get('experience_summary','')}<br>
            <b>Recommendation:</b> {r.get('recommendation','')}
          </div>
        </div>"""

    err_html = ""
    if errors:
        err_html = "<div style='color:#f87171;margin-top:16px;'><strong>Errors:</strong><br>" + \
            "<br>".join(f"{e['filename']}: {e['error']}" for e in errors) + "</div>"

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Resume Screening Report</title>
    <style>
    *{{box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif;}}
    body{{background:#0f172a;color:#e2e8f0;padding:24px;max-width:980px;margin:0 auto;}}
    h1{{font-size:1.6rem;}} .meta{{color:#94a3b8;font-size:.85rem;margin-bottom:18px;}}
    .jd-box{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px 18px;margin-bottom:22px;font-size:.85rem;white-space:pre-wrap;max-height:200px;overflow-y:auto;}}
    .candidate-card{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:18px 20px;margin-bottom:16px;border-left:6px solid #475569;}}
    .score-pill{{font-weight:800;font-size:1.4rem;padding:6px 18px;border-radius:30px;color:#0f172a;}}
    .badge{{padding:3px 10px;border-radius:6px;font-size:.75rem;font-weight:700;color:#0f172a;margin-left:8px;}}
    .tag{{background:#334155;padding:2px 10px;border-radius:12px;font-size:.78rem;margin:2px;display:inline-block;}}
    .tag.missing{{background:#4c1d1d;color:#fca5a5;}}
    ul{{padding-left:18px;font-size:.85rem;}}
    </style></head><body>
    <h1>📊 Resume Screening Report</h1>
    <div class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &middot; Candidates: {len(results)}</div>
    <div class="jd-box"><strong>Job Description</strong><br><br>{jd_text}</div>
    {rows}
    {err_html}
    </body></html>"""


# ---------- Main UI ----------
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📄 Upload Resumes")
    uploaded_files = st.file_uploader(
        "Drag & drop resumes (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"],
        accept_multiple_files=True
    )
    if uploaded_files:
        st.success(f"{len(uploaded_files)} file(s) uploaded")
        for f in uploaded_files:
            st.write(f"📎 {f.name}")

with col2:
    st.subheader("📋 Job Description")
    jd_text = st.text_area("Paste the full job description", height=250, placeholder="Job title, responsibilities, required skills...")

st.divider()

analyze_clicked = st.button("🔍 Analyze & Rank Candidates", type="primary", use_container_width=True)

if "results" not in st.session_state:
    st.session_state.results = None
    st.session_state.errors = None
    st.session_state.jd_text = None

if analyze_clicked:
    if not api_key:
        st.error("⚠️ Please enter your OpenAI API key in the sidebar.")
    elif not jd_text or not jd_text.strip():
        st.error("⚠️ Please paste a job description.")
    elif not uploaded_files:
        st.error("⚠️ Please upload at least one resume.")
    else:
        client = OpenAI(api_key=api_key)
        results, errors = [], []
        progress = st.progress(0, text="Starting analysis...")

        for i, f in enumerate(uploaded_files):
            progress.progress((i) / len(uploaded_files), text=f"Analyzing {f.name} ({i+1}/{len(uploaded_files)})...")
            try:
                text = extract_text(f)
                if not text.strip():
                    errors.append({"filename": f.name, "error": "Could not extract text"})
                    continue
                result = analyze_resume(client, model, text, jd_text, f.name)
                results.append(result)
            except Exception as e:
                errors.append({"filename": f.name, "error": str(e)})

        progress.progress(1.0, text="Done!")
        results.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        for idx, r in enumerate(results):
            r["rank"] = idx + 1
            r["score_color"] = score_color(r.get("match_score", 0))
            r["badge_color"] = verdict_color(r.get("verdict", ""))

        st.session_state.results = results
        st.session_state.errors = errors
        st.session_state.jd_text = jd_text
        progress.empty()

# ---------- Display results ----------
if st.session_state.results:
    results = st.session_state.results
    errors = st.session_state.errors

    st.subheader("📊 Ranking Results")

    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Candidates Analyzed", len(results))
    m2.metric("Strong Fits", sum(1 for r in results if r["verdict"] == "Strong Fit"))
    m3.metric("Top Score", f"{results[0]['match_score']}%" if results else "-")
    m4.metric("Avg Score", f"{round(sum(r['match_score'] for r in results)/len(results))}%" if results else "-")

    st.markdown("---")

    for r in results:
        with st.container():
            st.markdown(f"""
            <div class="candidate-card" style="border-left-color:{r['score_color']}">
              <div style="display:flex;justify-content:space-between;flex-wrap:wrap;align-items:center;">
                <div>
                  <h3 style="margin:0;">#{r['rank']} {r['candidate_name']}
                    <span class="badge" style="background:{r['badge_color']}">{r['verdict']}</span>
                  </h3>
                  <small style="color:#94a3b8;">{r['filename']}</small>
                </div>
                <div class="score-pill" style="background:{r['score_color']}">{r['match_score']}%</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander(f"View details — {r['candidate_name']}"):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**✅ Strengths**")
                    for s in r.get("strengths", []):
                        st.markdown(f"- {s}")
                    st.markdown("**🎯 Matched Skills**")
                    st.markdown(" ".join(f'<span class="tag">{s}</span>' for s in r.get("key_skills_matched", [])), unsafe_allow_html=True)
                with c2:
                    st.markdown("**⚠️ Gaps**")
                    for g in r.get("gaps", []):
                        st.markdown(f"- {g}")
                    st.markdown("**❌ Missing Skills**")
                    st.markdown(" ".join(f'<span class="tag missing">{s}</span>' for s in r.get("missing_skills", [])), unsafe_allow_html=True)

                st.markdown("---")
                st.markdown(f"**Summary:** {r.get('experience_summary','')}")
                st.markdown(f"**Recommendation:** {r.get('recommendation','')}")

    if errors:
        st.markdown("### ⚠️ Errors")
        for e in errors:
            st.error(f"{e['filename']}: {e['error']}")

    st.divider()

    # Download buttons
    html_report = build_html_report(results, st.session_state.jd_text, errors)
    json_report = json.dumps({
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "job_description": st.session_state.jd_text,
        "results": results,
        "errors": errors,
    }, indent=2)

    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            "⬇️ Download HTML Report",
            data=html_report,
            file_name=f"resume_screening_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
            mime="text/html",
            use_container_width=True,
        )
    with d2:
        st.download_button(
            "⬇️ Download JSON Report",
            data=json_report,
            file_name=f"resume_screening_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
        )