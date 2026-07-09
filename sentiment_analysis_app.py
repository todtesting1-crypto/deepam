import sys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

try:
    from transformers import pipeline
except ImportError:
    pipeline = None


class SentimentAnalysisApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Hugging Face Sentiment Analysis")
        self.root.geometry("760x520")
        self.root.resizable(True, True)

        self._build_ui()
        self.pipeline = None

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(frame, text="Hugging Face Sentiment Analysis", font=("Segoe UI", 14, "bold"))
        title_label.pack(anchor=tk.W)

        subtitle = ttk.Label(frame, text="Enter text below and click Analyze to see sentiment predictions with detailed percentages.", font=("Segoe UI", 10))
        subtitle.pack(anchor=tk.W, pady=(0, 12))

        input_label = ttk.Label(frame, text="Input Text:", font=("Segoe UI", 10, "bold"))
        input_label.pack(anchor=tk.W)

        self.input_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, height=10, font=("Segoe UI", 10))
        self.input_text.pack(fill=tk.BOTH, expand=False, pady=(6, 12))

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X)

        self.load_model_btn = ttk.Button(button_frame, text="Load Model", command=self.on_load_model)
        self.load_model_btn.pack(side=tk.LEFT)

        self.analyze_btn = ttk.Button(button_frame, text="Analyze Sentiment", command=self.on_analyze)
        self.analyze_btn.pack(side=tk.LEFT, padx=(10, 0))

        clear_btn = ttk.Button(button_frame, text="Clear", command=self.on_clear)
        clear_btn.pack(side=tk.LEFT, padx=(10, 0))

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill=tk.X, pady=(10, 6))
        self.progress.pack_forget()

        interpreter_path = sys.executable
        self.status_label = ttk.Label(
            frame,
            text=f"Ready to analyze. Interpreter: {interpreter_path}",
            font=("Segoe UI", 9),
            foreground="#555"
        )
        self.status_label.pack(anchor=tk.W, pady=(0, 6))

        result_label = ttk.Label(frame, text="Detailed Results:", font=("Segoe UI", 10, "bold"))
        result_label.pack(anchor=tk.W)

        self.results_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, height=12, font=("Segoe UI", 10), state="disabled")
        self.results_text.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

    def _load_pipeline(self):
        if self.pipeline is not None:
            return
        if pipeline is None:
            raise RuntimeError("The transformers library is not installed. Install it with: pip install transformers")

        self.status_label.config(text="Loading sentiment-analysis model...")
        self.root.update_idletasks()
        self.pipeline = pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english",
            return_all_scores=True,
        )

    def on_analyze(self):
        raw_text = self.input_text.get("1.0", tk.END).strip()
        if not raw_text:
            messagebox.showwarning("Input Required", "Please enter some text to analyze.")
            return

        try:
            self._load_pipeline()
        except Exception as exc:
            messagebox.showerror("Model Load Failed", str(exc))
            return

        self.analyze_btn.config(state=tk.DISABLED)
        self.load_model_btn.config(state=tk.DISABLED)
        self.progress.pack(fill=tk.X, pady=(10, 6))
        self.progress.start(10)
        self.status_label.config(text="Analyzing sentiment...")
        self.root.update_idletasks()

        try:
            results = self.pipeline(raw_text)
        except Exception as exc:
            messagebox.showerror("Analysis Failed", f"Sentiment analysis failed:\n{exc}")
            self.status_label.config(text="Analysis failed.")
            return

        self._display_results(raw_text, results)
        self.progress.stop()
        self.progress.pack_forget()
        self.analyze_btn.config(state=tk.NORMAL)
        self.load_model_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Analysis complete.")

    def _display_results(self, raw_text, results):
        if not isinstance(results, list) or len(results) == 0:
            messagebox.showwarning("No Results", "The sentiment model returned no predictions.")
            return

        top_prediction = None
        if isinstance(results[0], list):
            # Return-all-scores mode returns a list of label-score dicts for each input
            predictions = results[0]
        else:
            predictions = results

        sorted_predictions = sorted(predictions, key=lambda item: item["score"], reverse=True)
        top_prediction = sorted_predictions[0]

        labeled_lines = []
        labeled_lines.append("Top Sentiment:")
        labeled_lines.append(f"  • {top_prediction['label']} ({top_prediction['score'] * 100:.2f}%)")
        labeled_lines.append("")
        labeled_lines.append("Detailed Scores:")
        for item in sorted_predictions:
            labeled_lines.append(f"  • {item['label']}: {item['score'] * 100:.2f}%")

        if len(sorted_predictions) > 1:
            confidence_gap = sorted_predictions[0]["score"] - sorted_predictions[1]["score"]
            labeled_lines.append("")
            labeled_lines.append("Confidence Analysis:")
            labeled_lines.append(f"  • Highest confidence: {sorted_predictions[0]['score'] * 100:.2f}%")
            labeled_lines.append(f"  • Second highest: {sorted_predictions[1]['score'] * 100:.2f}%")
            labeled_lines.append(f"  • Margin: {confidence_gap * 100:.2f}%")

        explanation = self._generate_explanation(top_prediction, sorted_predictions)
        labeled_lines.append("")
        labeled_lines.append("Interpretation:")
        labeled_lines.extend([f"  • {line}" for line in explanation.split("\n")])

        self.results_text.config(state="normal")
        self.results_text.delete("1.0", tk.END)
        self.results_text.insert(tk.END, "\n".join(labeled_lines))
        self.results_text.config(state="disabled")

    def on_load_model(self):
        try:
            self._load_pipeline()
            self.load_model_btn.config(state=tk.DISABLED)
        except Exception as exc:
            messagebox.showerror("Model Load Failed", str(exc))

    def _generate_explanation(self, top_prediction, predictions):
        label = top_prediction["label"].lower()
        score = top_prediction["score"]
        lines = []

        if label in ["positive", "5 stars", "4 stars"]:
            lines.append("The text is generally positive and the model is confident in an upbeat sentiment.")
        elif label in ["negative", "1 star", "2 stars"]:
            lines.append("The text is generally negative and the model detected unfavorable sentiment.")
        elif label in ["neutral", "3 stars"]:
            lines.append("The text is neutral, indicating balanced sentiment or lack of strong emotional tone.")
        else:
            lines.append(f"The model identified the main sentiment as {top_prediction['label']}.")

        if score >= 0.90:
            lines.append("The prediction is very strong with high confidence.")
        elif score >= 0.70:
            lines.append("The prediction is moderately confident.")
        else:
            lines.append("The prediction is weaker, so consider verifying with additional context.")

        if len(predictions) > 1:
            second = predictions[1]
            lines.append(f"The next most likely sentiment is {second['label']} at {second['score'] * 100:.2f}%.")

        return "\n".join(lines)

    def on_clear(self):
        self.input_text.delete("1.0", tk.END)
        self.results_text.config(state="normal")
        self.results_text.delete("1.0", tk.END)
        self.results_text.config(state="disabled")
        self.status_label.config(text="Ready to analyze.")
        self.pipeline = None
        self.analyze_btn.config(state=tk.NORMAL)
        self.progress.stop()
        self.progress.pack_forget()


def main():
    interpreter_path = sys.executable
    print(f"Starting SentimentAnalysisApp with interpreter: {interpreter_path}")
    root = tk.Tk()
    app = SentimentAnalysisApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
