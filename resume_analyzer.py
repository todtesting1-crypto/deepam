"""
AI Resume Analyzer
==================
Requirements (install before running):
    pip install openai pdfplumber python-docx reportlab

Optional faster PDF fallback:
    pip install PyPDF2
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import json
import re
import csv
from datetime import datetime

# ─── Optional dependency detection ─────────────────────────────────────────────
_PDF_READER = None
try:
    import pdfplumber
    _PDF_READER = "pdfplumber"
except ImportError:
    pass

if _PDF_READER is None:
    try:
        import PyPDF2
        _PDF_READER = "pypdf2"
    except ImportError:
        pass

try:
    from docx import Document as DocxDocument
    _DOCX_OK = True
except ImportError:
    _DOCX_OK = False

_OPENAI_OK = False
_OPENAI_NEW_API = False   # True = v1.x (OpenAI class),  False = v0.28 (openai.ChatCompletion)
try:
    import openai as _openai_module
    _OPENAI_OK = True
    # v1.x exposes the OpenAI class; v0.28 does not
    _OPENAI_NEW_API = hasattr(_openai_module, "OpenAI")
except ImportError:
    pass

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    _REPORTLAB_OK = True
except ImportError:
    _REPORTLAB_OK = False


# ─── File Extraction ────────────────────────────────────────────────────────────

def extract_text_from_file(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".pdf":
        if _PDF_READER == "pdfplumber":
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                return "\n".join(p.extract_text() or "" for p in pdf.pages)
        elif _PDF_READER == "pypdf2":
            import PyPDF2
            text = []
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text.append(page.extract_text() or "")
            return "\n".join(text)
        else:
            raise ImportError(
                "No PDF library found.\nRun:  pip install pdfplumber"
            )

    elif ext in (".doc", ".docx"):
        if not _DOCX_OK:
            raise ImportError(
                "python-docx not installed.\nRun:  pip install python-docx"
            )
        doc = DocxDocument(filepath)
        return "\n".join(p.text for p in doc.paragraphs)

    elif ext == ".txt":
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    else:
        raise ValueError(f"Unsupported file type: {ext}")


# ─── OpenAI Analysis ────────────────────────────────────────────────────────────

def analyze_resume(api_key_or_client, resume_text: str, job_desc: str, filename: str) -> dict:
    prompt = f"""You are an expert HR recruiter. Analyze this resume against the job description.

RESUME FILE: {filename}
RESUME CONTENT:
{resume_text[:4500]}

JOB DESCRIPTION:
{job_desc[:2000]}

Respond ONLY with a valid JSON object — no markdown, no extra text:
{{
  "name": "Full candidate name, or 'Unknown'",
  "email": "Email address, or 'Not found'",
  "phone": "Phone number, or 'Not found'",
  "match_percentage": <integer 0-100>,
  "fit_status": "Fit" or "Not Fit",
  "strengths": ["point 1", "point 2", "point 3"],
  "weaknesses": ["point 1", "point 2"],
  "summary": "2-3 sentence summary of suitability for this role"
}}"""

    messages = [{"role": "user", "content": prompt}]

    if _OPENAI_NEW_API:
        # openai >= 1.x  — api_key_or_client is an OpenAI() instance
        response = api_key_or_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.2,
        )
        raw = response.choices[0].message.content.strip()
    else:
        # openai == 0.28.x  — api_key_or_client is the raw API key string
        _openai_module.api_key = api_key_or_client
        response = _openai_module.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.2,
        )
        raw = response["choices"][0]["message"]["content"].strip()

    # Strip markdown code fences if model adds them
    raw = re.sub(r"^```[^\n]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw.strip())
    return json.loads(raw)


# ─── Main Application ───────────────────────────────────────────────────────────

# Catppuccin Mocha color palette
C = {
    "base":    "#1e1e2e",
    "mantle":  "#181825",
    "surface0":"#313244",
    "surface1":"#45475a",
    "overlay0":"#6c7086",
    "text":    "#cdd6f4",
    "subtext": "#a6adc8",
    "blue":    "#89b4fa",
    "green":   "#a6e3a1",
    "red":     "#f38ba8",
    "yellow":  "#f9e2af",
    "peach":   "#fab387",
    "mauve":   "#cba6f7",
    "sky":     "#89dceb",
}


class ResumeAnalyzerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Resume Analyzer")
        self.geometry("1080x780")
        self.minsize(860, 650)
        self.configure(bg=C["base"])

        self.selected_files: list[str] = []
        self.results: list[dict] = []

        self._build_styles()
        self._build_ui()

    # ── Styles ──────────────────────────────────────────────────────────────────

    def _build_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure("TNotebook", background=C["base"], borderwidth=0)
        s.configure("TNotebook.Tab",
                    background=C["surface0"], foreground=C["text"],
                    font=("Segoe UI", 10, "bold"), padding=[16, 7])
        s.map("TNotebook.Tab",
              background=[("selected", C["blue"])],
              foreground=[("selected", C["base"])])

        s.configure("Treeview",
                    background=C["surface0"], foreground=C["text"],
                    fieldbackground=C["surface0"],
                    rowheight=28, font=("Segoe UI", 10))
        s.configure("Treeview.Heading",
                    background=C["surface1"], foreground=C["blue"],
                    font=("Segoe UI", 10, "bold"))
        s.map("Treeview",
              background=[("selected", C["blue"])],
              foreground=[("selected", C["base"])])

        s.configure("Green.Horizontal.TProgressbar",
                    troughcolor=C["surface0"], background=C["green"],
                    borderwidth=0)

        s.configure("TScrollbar",
                    background=C["surface1"], troughcolor=C["surface0"],
                    arrowcolor=C["text"])

    # ── Widget helpers ───────────────────────────────────────────────────────────

    def _lbl(self, parent, text, **kw):
        cfg = dict(font=("Segoe UI", 10), fg=C["text"], bg=C["base"], anchor="w")
        cfg.update(kw)
        return tk.Label(parent, text=text, **cfg)

    def _entry(self, parent, **kw):
        cfg = dict(font=("Segoe UI", 10), bg=C["surface0"], fg=C["text"],
                   insertbackground=C["text"], relief="flat",
                   highlightthickness=1, highlightcolor=C["blue"],
                   highlightbackground=C["surface1"])
        cfg.update(kw)
        return tk.Entry(parent, **cfg)

    def _btn(self, parent, text, command, color=None, **kw):
        color = color or C["blue"]
        return tk.Button(
            parent, text=text, command=command,
            font=("Segoe UI", 10, "bold"),
            bg=color, fg=C["base"], relief="flat",
            activebackground=C["sky"], activeforeground=C["base"],
            cursor="hand2", padx=14, pady=6, **kw
        )

    def _textarea(self, parent, height=6, font_size=10):
        frame = tk.Frame(parent, bg=C["surface0"],
                         highlightthickness=1, highlightbackground=C["surface1"])
        text = tk.Text(
            frame, height=height,
            font=("Segoe UI", font_size),
            bg=C["surface0"], fg=C["text"],
            insertbackground=C["text"],
            relief="flat", wrap="word", padx=8, pady=6
        )
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return frame, text

    # ── UI Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header bar
        hdr = tk.Frame(self, bg=C["surface0"], pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="AI Resume Analyzer",
                 font=("Segoe UI", 20, "bold"),
                 fg=C["blue"], bg=C["surface0"]).pack()
        tk.Label(hdr, text="Upload resumes · Add job description · Get AI-powered match analysis",
                 font=("Segoe UI", 9), fg=C["subtext"], bg=C["surface0"]).pack()

        # Tabs
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=10)

        self.tab_analysis   = tk.Frame(self.nb, bg=C["base"])
        self.tab_candidates = tk.Frame(self.nb, bg=C["base"])

        self.nb.add(self.tab_analysis,   text="  Analysis  ")
        self.nb.add(self.tab_candidates, text="  Candidates  ")

        self._build_analysis_tab()
        self._build_candidates_tab()

    # ── Analysis Tab ─────────────────────────────────────────────────────────────

    def _build_analysis_tab(self):
        t = self.tab_analysis
        PAD = {"padx": 16, "pady": 5}

        # API Key row
        row1 = tk.Frame(t, bg=C["base"])
        row1.pack(fill="x", **PAD)
        self._lbl(row1, "OpenAI API Key:").pack(side="left")
        self.api_var = tk.StringVar()
        self.api_entry = self._entry(row1, textvariable=self.api_var, show="*", width=52)
        self.api_entry.pack(side="left", padx=(8, 4), ipady=5)
        self._btn(row1, "Show", self._toggle_api, color=C["surface1"]).pack(side="left")
        # Missing library warning
        missing = []
        if not _OPENAI_OK:   missing.append("openai")
        if not _PDF_READER:  missing.append("pdfplumber")
        if not _DOCX_OK:     missing.append("python-docx")
        if missing:
            tk.Label(row1, text=f"  Missing: pip install {' '.join(missing)}",
                     font=("Segoe UI", 8), fg=C["red"], bg=C["base"]).pack(side="left", padx=8)

        # File upload row
        row2 = tk.Frame(t, bg=C["base"])
        row2.pack(fill="x", **PAD)
        self._lbl(row2, "Resume Files:  ").pack(side="left")
        self.file_lbl = tk.Label(
            row2, text="  No files selected",
            font=("Segoe UI", 9), fg=C["subtext"],
            bg=C["surface0"], anchor="w",
            highlightthickness=1, highlightbackground=C["surface1"],
            width=48
        )
        self.file_lbl.pack(side="left", padx=(8, 4), ipady=5)
        self._btn(row2, "Browse", self._browse_files, color=C["green"]).pack(side="left")
        self._btn(row2, "Clear", self._clear_files, color=C["red"]).pack(side="left", padx=(4, 0))

        # Job description
        self._lbl(t, "Job Description:").pack(fill="x", padx=16, pady=(6, 2))
        jd_outer, self.jd_text = self._textarea(t, height=7)
        jd_outer.pack(fill="x", padx=16, pady=(0, 6))

        # Analyze button + progress
        ctrl = tk.Frame(t, bg=C["base"])
        ctrl.pack(fill="x", padx=16, pady=4)
        self.analyze_btn = self._btn(ctrl, "  Analyze Resumes  ",
                                     self._start_analysis, color=C["green"])
        self.analyze_btn.pack(side="left")
        self.status_lbl = tk.Label(ctrl, text="", font=("Segoe UI", 9),
                                   fg=C["subtext"], bg=C["base"])
        self.status_lbl.pack(side="left", padx=12)
        self.progress = ttk.Progressbar(ctrl, style="Green.Horizontal.TProgressbar",
                                        orient="horizontal", length=220, mode="determinate")
        self.progress.pack(side="right")

        # Results
        self._lbl(t, "Analysis Results:").pack(fill="x", padx=16, pady=(8, 2))
        res_outer = tk.Frame(t, bg=C["mantle"],
                             highlightthickness=1, highlightbackground=C["surface1"])
        res_outer.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        self.result_text = tk.Text(
            res_outer, font=("Cascadia Code", 9),
            bg=C["mantle"], fg=C["text"],
            insertbackground=C["text"],
            relief="flat", wrap="word", padx=10, pady=8,
            state="disabled"
        )
        res_sb = ttk.Scrollbar(res_outer, orient="vertical",
                               command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=res_sb.set)
        self.result_text.pack(side="left", fill="both", expand=True)
        res_sb.pack(side="right", fill="y")

        # Text color tags
        self.result_text.tag_configure("divider",  foreground=C["surface1"])
        self.result_text.tag_configure("header",   foreground=C["blue"],
                                       font=("Cascadia Code", 10, "bold"))
        self.result_text.tag_configure("fit",      foreground=C["green"],
                                       font=("Cascadia Code", 9, "bold"))
        self.result_text.tag_configure("notfit",   foreground=C["red"],
                                       font=("Cascadia Code", 9, "bold"))
        self.result_text.tag_configure("label",    foreground=C["yellow"],
                                       font=("Cascadia Code", 9, "bold"))
        self.result_text.tag_configure("value",    foreground=C["text"])
        self.result_text.tag_configure("error",    foreground=C["red"])

    # ── Candidates Tab ────────────────────────────────────────────────────────────

    def _build_candidates_tab(self):
        t = self.tab_candidates

        # Info bar
        info = tk.Frame(t, bg=C["surface0"], pady=6)
        info.pack(fill="x")
        tk.Label(info, text="Click any column header to sort  ·  Fit candidates highlighted in green",
                 font=("Segoe UI", 9), fg=C["subtext"], bg=C["surface0"]).pack()

        # Table frame
        tbl_frame = tk.Frame(t, bg=C["base"])
        tbl_frame.pack(fill="both", expand=True, padx=16, pady=10)

        cols = ("name", "email", "phone", "match", "status")
        heads = {"name": "Candidate Name", "email": "Email",
                 "phone": "Phone", "match": "Match %", "status": "Status"}
        widths = {"name": 195, "email": 220, "phone": 145, "match": 90, "status": 95}

        self.tree = ttk.Treeview(tbl_frame, columns=cols, show="headings",
                                  selectmode="browse")
        for col in cols:
            self.tree.heading(col, text=heads[col],
                               command=lambda c=col: self._sort_tree(c))
            self.tree.column(col, width=widths[col], anchor="center",
                             minwidth=60)

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tbl_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tbl_frame.rowconfigure(0, weight=1)
        tbl_frame.columnconfigure(0, weight=1)

        self.tree.tag_configure("fit_row",    foreground=C["green"])
        self.tree.tag_configure("notfit_row", foreground=C["red"])

        # Download buttons
        dl_bar = tk.Frame(t, bg=C["base"])
        dl_bar.pack(fill="x", padx=16, pady=(0, 12))

        self._btn(dl_bar, "  Download CSV Report  ",
                  self._download_csv, color=C["sky"]).pack(side="left")
        self._btn(dl_bar, "  Download PDF Report  ",
                  self._download_pdf, color=C["mauve"]).pack(side="left", padx=(8, 0))

        self.dl_status = tk.Label(dl_bar, text="", font=("Segoe UI", 9),
                                   fg=C["subtext"], bg=C["base"])
        self.dl_status.pack(side="left", padx=12)

        if not _REPORTLAB_OK:
            tk.Label(dl_bar,
                     text="PDF export requires:  pip install reportlab",
                     font=("Segoe UI", 8), fg=C["peach"],
                     bg=C["base"]).pack(side="right", padx=4)

    # ── Event Handlers ────────────────────────────────────────────────────────────

    def _toggle_api(self):
        self.api_entry.config(show="" if self.api_entry.cget("show") == "*" else "*")

    def _browse_files(self):
        files = filedialog.askopenfilenames(
            title="Select Resume Files",
            filetypes=[
                ("Supported Files", "*.pdf *.doc *.docx *.txt"),
                ("PDF Files", "*.pdf"),
                ("Word Documents", "*.doc *.docx"),
                ("Text Files", "*.txt"),
                ("All Files", "*.*"),
            ]
        )
        if files:
            self.selected_files = list(files)
            names = [os.path.basename(f) for f in self.selected_files]
            if len(names) <= 3:
                self.file_lbl.config(text="  " + ", ".join(names))
            else:
                self.file_lbl.config(
                    text=f"  {', '.join(names[:3])}  … +{len(names)-3} more"
                )
            self.file_lbl.config(fg=C["text"])

    def _clear_files(self):
        self.selected_files = []
        self.file_lbl.config(text="  No files selected", fg=C["subtext"])

    def _start_analysis(self):
        api_key = self.api_var.get().strip()
        jd      = self.jd_text.get("1.0", "end").strip()

        if not api_key:
            messagebox.showerror("Missing API Key", "Please enter your OpenAI API key.")
            return
        if not _OPENAI_OK:
            messagebox.showerror("OpenAI Not Found",
                                 "Install the OpenAI library:\n\npip install openai")
            return
        if not self.selected_files:
            messagebox.showerror("No Files Selected",
                                 "Please select at least one resume file.")
            return
        if not jd:
            messagebox.showerror("No Job Description",
                                 "Please paste the job description.")
            return

        self.analyze_btn.config(state="disabled")
        self.results = []
        self._clear_results()
        self._clear_tree()
        self.progress.config(value=0)

        threading.Thread(target=self._run_analysis,
                         args=(api_key, jd), daemon=True).start()

    def _run_analysis(self, api_key: str, jd: str):
        try:
            if _OPENAI_NEW_API:
                # v1.x: create a client object once
                client_or_key = _openai_module.OpenAI(api_key=api_key)
            else:
                # v0.28: just pass the key string; the module handles the rest
                client_or_key = api_key
        except Exception as e:
            self._set_status(f"OpenAI init error: {e}")
            self.after(0, lambda: self.analyze_btn.config(state="normal"))
            return

        total = len(self.selected_files)
        for i, filepath in enumerate(self.selected_files):
            fname = os.path.basename(filepath)
            self._set_status(f"Analyzing {i+1}/{total}: {fname}")
            self._set_progress(int(i / total * 100))
            try:
                text = extract_text_from_file(filepath)
                if not text.strip():
                    raise ValueError("Could not extract text — file may be image-based PDF.")
                data = analyze_resume(client_or_key, text, jd, fname)
                data["_file"] = fname
                self.results.append(data)
                self.after(0, self._append_result, data)
                self.after(0, self._add_tree_row, data)
            except Exception as e:
                err = {"_file": fname, "_error": str(e)}
                self.results.append(err)
                self.after(0, self._append_error, fname, str(e))

        self._set_status(f"Completed — {total} resume(s) analyzed.")
        self._set_progress(100)
        self.after(0, lambda: self.analyze_btn.config(state="normal"))
        self.after(0, lambda: self.nb.select(1))   # switch to Candidates tab

    # ── Result Text Helpers ───────────────────────────────────────────────────────

    def _clear_results(self):
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.config(state="disabled")

    def _append_result(self, data: dict):
        rt = self.result_text
        rt.config(state="normal")

        fname  = data.get("_file", "")
        name   = data.get("name", "Unknown")
        match  = data.get("match_percentage", 0)
        fit    = data.get("fit_status", "?")
        fit_tag = "fit" if fit == "Fit" else "notfit"

        rt.insert("end", f"\n{'─' * 74}\n", "divider")
        rt.insert("end", f" {fname}", "header")
        rt.insert("end", f"   →   {name}\n", "value")

        rt.insert("end", " Match:     ", "label")
        rt.insert("end", f"{match}%    ", "value")
        rt.insert("end", "Status: ", "label")
        rt.insert("end", f"{fit}\n", fit_tag)

        rt.insert("end", " Strengths: ", "label")
        rt.insert("end", "  ·  ".join(data.get("strengths", [])) + "\n", "value")

        rt.insert("end", " Weaknesses:", "label")
        rt.insert("end", "  ·  ".join(data.get("weaknesses", [])) + "\n", "value")

        rt.insert("end", " Summary:   ", "label")
        rt.insert("end", data.get("summary", "") + "\n", "value")

        rt.config(state="disabled")
        rt.see("end")

    def _append_error(self, fname: str, err: str):
        rt = self.result_text
        rt.config(state="normal")
        rt.insert("end", f"\n{'─' * 74}\n", "divider")
        rt.insert("end", f" ERROR — {fname}\n", "error")
        rt.insert("end", f" {err}\n", "value")
        rt.config(state="disabled")
        rt.see("end")

    # ── Tree Helpers ──────────────────────────────────────────────────────────────

    def _clear_tree(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

    def _add_tree_row(self, data: dict):
        if "_error" in data:
            return
        fit   = data.get("fit_status", "?")
        match = data.get("match_percentage", 0)
        tag   = "fit_row" if fit == "Fit" else "notfit_row"
        self.tree.insert("", "end", values=(
            data.get("name", "Unknown"),
            data.get("email", "Not found"),
            data.get("phone", "Not found"),
            f"{match}%",
            fit,
        ), tags=(tag,))

    def _sort_tree(self, col: str):
        rows = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        try:
            rows.sort(key=lambda x: int(x[0].replace("%", "")), reverse=True)
        except ValueError:
            rows.sort(key=lambda x: x[0].lower())
        for idx, (_, k) in enumerate(rows):
            self.tree.move(k, "", idx)

    # ── Status / Progress Helpers ─────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self.after(0, lambda: self.status_lbl.config(text=msg))

    def _set_progress(self, val: int):
        self.after(0, lambda: self.progress.config(value=val))

    # ── Download Handlers ─────────────────────────────────────────────────────────

    def _clean_results(self):
        return [r for r in self.results if "_error" not in r]

    def _download_csv(self):
        if not self._clean_results():
            messagebox.showinfo("No Data", "Run an analysis first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save CSV Report",
            defaultextension=".csv",
            filetypes=[("CSV File", "*.csv")],
            initialfile=f"resume_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["File", "Name", "Email", "Phone",
                        "Match %", "Status", "Strengths", "Weaknesses", "Summary"])
            for d in self.results:
                if "_error" in d:
                    w.writerow([d["_file"], "ERROR", "", "", "", "",
                                "", "", d["_error"]])
                else:
                    w.writerow([
                        d.get("_file", ""),
                        d.get("name", ""),
                        d.get("email", ""),
                        d.get("phone", ""),
                        d.get("match_percentage", ""),
                        d.get("fit_status", ""),
                        " | ".join(d.get("strengths", [])),
                        " | ".join(d.get("weaknesses", [])),
                        d.get("summary", ""),
                    ])
        self.dl_status.config(text=f"Saved: {os.path.basename(path)}")
        messagebox.showinfo("CSV Saved", f"Report saved to:\n{path}")

    def _download_pdf(self):
        clean = self._clean_results()
        if not clean:
            messagebox.showinfo("No Data", "Run an analysis first.")
            return
        if not _REPORTLAB_OK:
            messagebox.showerror(
                "ReportLab Not Found",
                "Install ReportLab for PDF export:\n\npip install reportlab"
            )
            return
        path = filedialog.asksaveasfilename(
            title="Save PDF Report",
            defaultextension=".pdf",
            filetypes=[("PDF File", "*.pdf")],
            initialfile=f"resume_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )
        if not path:
            return

        doc    = SimpleDocTemplate(path, pagesize=letter,
                                   topMargin=40, bottomMargin=40,
                                   leftMargin=40, rightMargin=40)
        styles = getSampleStyleSheet()
        elems  = []

        # Title
        title_p = Paragraph(
            "<b>Resume Analysis Report</b>",
            styles["Title"]
        )
        elems.append(title_p)
        elems.append(Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
            f"{len(clean)} candidate(s) analyzed",
            styles["Normal"]
        ))
        elems.append(Spacer(1, 16))

        # Summary table
        tbl_data = [["Name", "Email", "Phone", "Match %", "Status"]]
        for d in clean:
            tbl_data.append([
                d.get("name", ""),
                d.get("email", ""),
                d.get("phone", ""),
                f"{d.get('match_percentage', '')}%",
                d.get("fit_status", ""),
            ])

        tbl = Table(tbl_data, repeatRows=1,
                    colWidths=[120, 160, 110, 60, 60])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0),  colors.HexColor("#313244")),
            ("TEXTCOLOR",      (0, 0), (-1, 0),  colors.HexColor("#89b4fa")),
            ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#f0f0f0"), colors.white]),
            ("GRID",           (0, 0), (-1, -1), 0.4, colors.grey),
            ("ALIGN",          (3, 0), (4, -1),  "CENTER"),
            ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",     (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ]))
        elems.append(tbl)
        elems.append(Spacer(1, 20))

        # Detailed cards
        elems.append(Paragraph("<b>Detailed Analysis</b>", styles["Heading1"]))
        elems.append(Spacer(1, 8))

        for d in clean:
            fit_color = "#2e7d32" if d.get("fit_status") == "Fit" else "#c62828"
            elems.append(Paragraph(
                f'<font color="#1565c0"><b>{d.get("name", "Unknown")}</b></font>'
                f' &nbsp; <font size="8" color="#555">{d.get("_file", "")}</font>',
                styles["Heading2"]
            ))
            elems.append(Paragraph(
                f'<b>Match:</b> {d.get("match_percentage", "")}%'
                f' &nbsp;&nbsp; '
                f'<b>Status:</b> <font color="{fit_color}">{d.get("fit_status", "")}</font>',
                styles["Normal"]
            ))
            elems.append(Paragraph(
                "<b>Email:</b> " + d.get("email", "Not found") +
                " &nbsp;&nbsp; <b>Phone:</b> " + d.get("phone", "Not found"),
                styles["Normal"]
            ))
            elems.append(Paragraph(
                "<b>Strengths:</b> " + " · ".join(d.get("strengths", [])),
                styles["Normal"]
            ))
            elems.append(Paragraph(
                "<b>Weaknesses:</b> " + " · ".join(d.get("weaknesses", [])),
                styles["Normal"]
            ))
            elems.append(Paragraph(
                "<b>Summary:</b> " + d.get("summary", ""),
                styles["Normal"]
            ))
            elems.append(Spacer(1, 14))

        doc.build(elems)
        self.dl_status.config(text=f"Saved: {os.path.basename(path)}")
        messagebox.showinfo("PDF Saved", f"Report saved to:\n{path}")


# ─── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ResumeAnalyzerApp()
    app.mainloop()
