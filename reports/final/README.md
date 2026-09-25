# Final reports (course LaTeX template)

One report per team member, generated from the course template:

| File | Author |
|---|---|
| `SP_Final_Report_Akshay_Rukade.tex` / `.pdf` | Akshay Ajit Rukade |
| `SP_Final_Report_J_Krithika.tex` / `.pdf` | J Krithika |
| `SP_Final_Report_Ritesh_Gajanan_Sonar.tex` / `.pdf` | Ritesh Gajanan Sonar |

The body is shared; only the author and the Individual Contribution chapter differ.
All fields are filled in. The two-device results are from simulation
(`experiments/run_two_device_sim.py`); a test on two physical devices was not
carried out, and the reports say so.

Edit `make_final_reports.py` (not the `.tex` files, which it overwrites), then:

```bash
python3 reports/final/make_final_reports.py
cd reports/final
for f in SP_Final_Report_*.tex; do pdflatex $f; pdflatex $f; done   # twice for the contents
```

On Overleaf: upload one `.tex` file together with the `figures/` folder.
`make_block_diagram.py` regenerates `figures/fig0_block_diagram.png`; figures 1–6
are copies of `reports/figures/`, and 7–8 are dashboard screenshots.
