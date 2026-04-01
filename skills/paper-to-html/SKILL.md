---
name: paper-to-html
description: Generate a self-contained, beautifully styled HTML analysis of an academic paper. Use when the user provides an arXiv link, paper URL, PDF, or asks to analyze a research paper. Produces a standalone HTML file with structured sections (Problem, Translation/Analogy, Architecture, Key Results, Verdict), embedded figures, and responsive design. Trigger words include 读论文, 分析论文, paper analysis, paper review.
---

# Paper to HTML

Generate a self-contained HTML analysis of an academic paper. The output is a single `.html` file with embedded CSS — no external dependencies, ready to deploy or share.

## Output Structure

The HTML analysis must follow this structure:

### Header
- Paper title (original)
- Authors and affiliations
- Source (arXiv ID, venue)
- Tags (topic tags as colored badges)

### Sections

1. **问题** (Problem)
   - What problem does this paper solve?
   - Why is it hard? What existing approaches fall short?
   - Use plain language, no jargon in the first paragraph

2. **翻译** (Translation / Analogy)
   - Explain the core idea using a real-world analogy
   - Make it accessible to a non-specialist
   - This is the most important section for readability

3. **架构** (Architecture / Method)
   - Technical details of the proposed approach
   - Use `.architecture` code blocks for diagrams (ASCII art)
   - Use `.concept` cards for key definitions
   - Include paper figures when available

4. **关键结果** (Key Results)
   - Performance numbers, benchmarks, comparisons
   - Use tables for quantitative results
   - Highlight surprising or noteworthy findings

5. **评价** (Verdict)
   - Use `.verdict` box: one-sentence assessment
   - Strengths and limitations
   - Who should read this paper?

6. **博导审稿** (PhD Supervisor Review)
   - **Identity**: Switch to a PhD supervisor who has mentored graduate students for 20 years in this exact research direction
   - **Scene**: A student brings you this paper in your office. You judge whether it's worth taking seriously
   - **Tone**: Plain language, like chatting with a student — not formal review language
   - **Five evaluation axes** (each gets a one-sentence assessment):
     - 选题眼光 (Topic Selection): Is this a real problem or a manufactured one?
     - 方法成熟度 (Method Maturity): Is this engineering polish or genuine methodological innovation?
     - 实验诚意 (Experimental Sincerity): Did they test on hard cases or cherry-pick easy ones?
     - 写作功力 (Writing Craft): Clear thinking or jargon smokescreen?
     - 影响力预判 (Impact Forecast): Will anyone cite this in 3 years?
   - **Verdict**: strong accept / weak accept / borderline / weak reject / strong reject + one-sentence justification
   - Use `.supervisor` CSS class (dark green left border, light green background)

7. **一句话总结** (One-line Summary)
   - The elevator pitch version

### Footer
- Generation metadata
- Link to original paper

## Math Rendering

All HTML output MUST include KaTeX for LaTeX math rendering. Add these lines in `<head>`:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}]})"></script>
```

Use standard LaTeX delimiters in text:
- `$$...$$` for display math (centered, own line)
- `$...$` for inline math

Example: `The complexity is $O(N_c^2)$` renders as proper math.

## HTML Template

Use this CSS design system (warm stone palette, purple accent):

```css
:root {
  --bg: #fafaf9;
  --fg: #1c1917;
  --muted: #78716c;
  --accent: #7c3aed;
  --accent-light: #ede9fe;
  --border: #e7e5e4;
  --code-bg: #f5f5f4;
  --verdict-bg: #fef3c7;
  --verdict-border: #f59e0b;
}
```

Key CSS classes:
- `.architecture` — monospace code/diagram blocks
- `.concept` — definition cards with labeled fields
- `.insight` — purple left-border highlight blocks
- `.verdict` — amber warning-style assessment box
- `.supervisor` — dark green left-border review box (for 博导审稿)
- `.score-grid` — 2-column grid for evaluation axes
- `.paper-figure` — centered image with caption
- `.tag` — purple badge for topic tags

## Figure Handling

When paper figures are available (from PDF extraction or provided by user):
1. Save figures to `assets/<paper_id>/` directory
2. Reference with relative paths: `assets/<paper_id>/fig1.png`
3. Add descriptive figcaptions

## File Naming Convention

```
<timestamp>--paper-<short-name>__paper.html
```

Example: `20260326T133200--paper-nonlinearsolve-jl__paper.html`

## Quality Requirements

- **Self-contained**: Single HTML file with embedded CSS, no external dependencies
- **Responsive**: Readable on mobile (max-width: 760px centered layout)
- **Chinese by default**: All analysis text in Chinese, technical terms in original language
- **Accessible**: Non-specialists should understand sections 1-2; specialists get value from 3-4
- **Honest**: Don't oversell the paper. Use the verdict box for balanced assessment
