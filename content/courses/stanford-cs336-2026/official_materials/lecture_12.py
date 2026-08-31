from edtrace import text, link, image
from lecture_util import post_link
from references import mmlu_2021

def main():
    text("## Lecture 12: evaluation")
    text("- So far: we've covered everything for training an LM (architecture, training, systems, scaling).")
    text("- Missing piece: what **data** do you train on?")
    text("- Data shapes model behavior (code? multilingual? DNA?).")
    text("- Before talking about data, need to talk about what behavior we want from a model.")

    text("**Evaluation**: given a model, how \"**good**\" is it?")

    what_is_good()

    perplexity()
    exam_benchmarks()
    chat_benchmarks()
    agentic_benchmarks()
    pure_reasoning_benchmarks()
    safety_benchmarks()

    realism()
    validity()
    how_to_think_about_evaluation()

    text("Takeaways:")
    text("- There is no one true evaluation; choose the evaluation depending on what you're trying to measure.")
    text("- Clearly state the rules of the game (methods versus models versus agents).")
    text("- Considerations: difficulty, realism, validity.")


def what_is_good():
    text("Evaluation might appear to be a mechanical process:")
    text("1. Define some prompts")
    text("2. Send prompts to a model and get back responses")
    text("3. Compute accuracy")

    text("But actually, evaluation is a deep and important topic...")
    text("...which shapes the development of AI.")

    text("**Core challenge**: <font color=\"red\">abstract construct</font> → <font color=\"blue\">concrete metric</font>")

    text("Maybe a model is good if it does well on benchmarks...")
    link(title="Artificial Analysis", url="https://artificialanalysis.ai/")
    image("images/artificial-analysis.png", width=800)

    text("Maybe a model is good if it does well on benchmarks and is cheap to run...")
    image("images/artificial-analysis-cost.png", width=800)

    text("Maybe a model is good if people prefer its responses...")
    link(title="Arena AI (formerly Chatbot Arena)", url="https://arena.ai/leaderboard")
    image("images/lmarena-leaderboard.png", width=400)

    text("Maybe a model is good if people simply choose to use (and pay for) it...")
    link(title="OpenRouter", url="https://openrouter.ai/rankings")
    image("images/openrouter.png", width=600)


def perplexity():
    text("- Recall: that a language model is a probability distribution **p(x)** over sequences of tokens.")
    text("- Perplexity (1/p(D))^(1/|D|) measures whether p assigns high probability to some dataset D.")

    text("- In pre-training, you minimize perplexity on the training set.")
    text("- The obvious thing is to measure perplexity on the test set.")
    text("- This is what people did traditionally in language modeling research.")

    text("Standard datasets:")
    text("- Penn Treebank (WSJ)")
    text("- WikiText-103 (Wikipedia)")
    text("- One Billion Word Benchmark (from machine translation WMT11 - EuroParl, UN, news)")
    text("Classic paradigm: in-distribution evaluation: train on train split and evaluate on test split of some dataset.")
    text("Pure CNNs+LSTMs on the One Billion Word Benchmark (perplexity 51.3 → 30.0) "), link("https://arxiv.org/abs/1602.02410")

    text("GPT-2:")
    text("- Trained on WebText (40GB text, websites linked from Reddit)")
    text("- Zero-shot on standard datasets (**out-of-distribution** evaluation)")
    image("images/gpt2-perplexity.png", width=800)
    text("- Works better on small datasets (PTB) where transfer is helpful, but not larger datasets (1BW)")

    text("Perplexity is all you need (more faith than science):")
    text("- True distribution is t, model is p.")
    text("- Best possible perplexity is H(t) obtained iff p = t.")
    text("- If p = t, then solve all the tasks: p(solution | problem)")
    text("- So by pushing down on perplexity, we will eventually \"reach AGI\".")

    text("Perplexity is maybe more than you need:")
    text("- Example: *Stanford was founded in 1885*")
    text("- Perplexity penalizes prediction on all tokens, some (e.g., *founded*) of which might not be relevant")
    text("- Solution: measure conditional perplexity p(response | prompt)^(1/|response|)")

    text("Some benchmarks are perplexity in disguise:")
    text("- Cloze tasks (fill in the blank): LAMBADA "), link("https://arxiv.org/abs/1606.06031")
    image("images/lambada.png", width=700)
    text("- Multiple choice sentence completion: HellaSwag "), link("https://arxiv.org/pdf/1905.07830")
    image("images/hellaswag.png", width=500)

    text("**Warning** (if you're running a perplexity leaderboard):")
    text("- People submit `LM` and you compute `log_prob = LM(test_data)`")
    text("- You need to trust that the probabilities are valid (sum to 1)")
    text("- For downstream tasks, `response = LM(prompt)` and compute accuracy on `response`")

    text("Summary:")
    text("- Perplexity is still used heavily in language model development (smooth scaling laws)")
    text("- Still need benchmarks that capture real-world situations (for the non-believers)...")


def exam_benchmarks():
    text("Exams are a useful way to test language models (as with humans):")
    text("- Have control over the subject and difficulty")
    text("- Design to have unambiguous correct answer, easy to grade")

    text("**Massive Multitask Language Understanding (MMLU)** "), link(mmlu_2021)
    text("- 57 subjects (e.g., math, US history, law, morality), multiple-choice")
    text("- \"collected by graduate and undergraduate students from freely available sources online\"")
    text("- Despite the name, MMLU is really about testing knowledge, not language understanding")
    text("- Evaluated on GPT-3 using few-shot prompting")
    image("images/mmlu.png", width=700)
    link("https://llm-stats.com/benchmarks/mmlu")
    link(title="HELM MMLU for visualizing predictions", url="https://crfm.stanford.edu/helm/mmlu/latest/")

    text("**MMLU-Pro** "), link("https://arxiv.org/abs/2406.01574")
    text("- Removed noisy/trivial questions from MMLU")
    text("- Expanded 4 choices to 10 choices")
    text("- Evaluated using chain of thought (gives model more of a chance)")
    text("- Accuracy of models drop by 16% to 33% (not as saturated)")
    image("images/mmlu-pro.png", width=700)
    link("https://llm-stats.com/benchmarks/mmlu-pro")
    link(title="HELM MMLU-Pro for visualizing predictions", url="https://crfm.stanford.edu/helm/capabilities/latest/#/leaderboard/mmlu_pro")

    text("**Graduate-Level Google-Proof Q&A (GPQA)** "), link("https://arxiv.org/abs/2311.12022")
    text("- Questions written by 61 PhD contractors from Upwork")
    image("images/gpqa.png", width=700)
    text("- PhD experts achieve 65% accuracy")
    text("- Non-experts achieve 34% over 30 minutes with access to Google")
    text("- GPT-4 achieves 39%")
    link("https://llm-stats.com/benchmarks/gpqa")
    link(title="HELM GPQA for visualizing predictions", url="https://crfm.stanford.edu/helm/capabilities/latest/#/leaderboard/gpqa")

    text("**Humanity's Last Exam (HLE)** "), link("https://arxiv.org/abs/2501.14249")
    text("- 2500 questions: multimodal, many subjects, multiple-choice + short-answer")
    image("images/hle-examples.png", width=700)
    text("- Awarded $500K prize pool + co-authorship to question creators")
    text("- Filtered by frontier LLMs, multiple stages of review")
    image("images/hle-pipeline.png", width=700)
    image("images/hle-results.png", width=600)
    link("https://llm-stats.com/benchmarks/hle")

    text("Summary:")
    text("- Trend towards harder questions as models improve and saturate existing benchmarks")
    text("- Multiple-choice format can be as difficult as one wants")
    text("- Does not capture real usage (open-ended, doesn't necessarily exist correct answer)")


def chat_benchmarks():
    text("- So far, we've been evaluating on well-defined multiple-choice tasks.")
    text("- Most people don't ask multiple-choice exam questions to their AI assistant.")
    
    text("Example:")
    text("Prompt: *I would like to make a beet salad with goat cheese. What kind of herbs would work well and what would not work well?*")
    text("Response: *Here’s a breakdown of herbs that work well (and some that don’t) in a beet + goat cheese salad, based on how their flavors interact with the sweet-earthiness of beets and the tangy creaminess of goat cheese...")

    text("**Challenge**: how to evaluate an open-ended response?")

    text("**Chatbot Arena** "), link("https://arxiv.org/abs/2403.04132")
    text("Data collection:")
    text("- Random person from the Internet types in prompt")
    text("- They get response from two random (anonymized) models")
    text("- They rate which one is better")
    image("images/arena-beets.png", width=700)
    text("Compute ELO rankings based on pairwise comparisons:")
    text("- Define model: p(A wins against B) = 1 / (1 + 10^((ELO_B - ELO_A)/400))")
    text("- Fit this model to maximize probability of pairwise comparisons")
    link(title="Arena AI (formerly Chatbot Arena)", url="https://arena.ai/leaderboard")
    image("images/lmarena-leaderboard.png", width=400)
    text("Properties:")
    text("- Real-world prompts (free for users, incentives to actually use it)")
    text("- But who are these people? biases? spammers?")
    text("- Binary preference but conflates style and correctness")
    text("- How does the human even assess correctness?  Prone to sycophancy?")
    text("- Feature: don't need to feed same prompts to all models (important because human is rating)")
    text("- Dynamic: incorporates new prompts and models over time")

    text("**AlpacaEval** (2023)"), link(title="leaderboard", url="https://tatsu-lab.github.io/alpaca_eval/")
    text("- 805 instructions from various sources")
    text("- Metric: win rate against baseline model (GPT-4 preview) as judged by GPT-4 preview (potential bias?)")
    text("- Problem: LLM judges favor longer responses, resulted in leaderboard gaming")
    text("- Alpaca Eval 2.0 used regression to debias the metric "), link("https://arxiv.org/pdf/2404.04475")
    text("- How do we evaluate the metric?")
    text("- Correlation with Chatbot Arena (humans) is high:")
    image("https://github.com/tatsu-lab/alpaca_eval/raw/main/figures/chat_correlations_no_ae.png", width=500)
    image("images/alpacaeval-leaderboard.png", width=400)

    text("**WildBench** "), link("https://arxiv.org/pdf/2406.04770")
    text("- Sourced 1024 examples from 1M human-chatbot conversations")
    text("- Uses GPT-4 turbo as a judge with a checklist (like CoT for judging) + GPT-4 as a judge")
    text("- Well-correlated with Chatbot Arena (seems to be the de facto sanity check)")
    image("images/wildbench.png", width=700)
    link(title="HELM WildBench for visualizing predictions", url="https://crfm.stanford.edu/helm/capabilities/latest/#/leaderboard/wildbench")

    text("Summary:")
    text("- Challenge: how to evaluate open-ended responses?")
    text("- Pairwise comparisons between similar responses provide higher signal")
    text("- Beware of biases (both from humans and LLM judges)")
    text("- Checklist/rubric improves reliability (regardless of human or LLM judge)")


def agentic_benchmarks():
    text("Previously: evaluate what LMs say (chat)")
    text("Now: evaluate what LMs do (agents)")

    text("Agent = language model + agent scaffold (logic for deciding how to use the LM)")
    
    text("Consider tasks that require tool use (e.g., running code) and iterating over a period of time")

    text("**SWEBench** "), link("https://arxiv.org/abs/2310.06770")
    text("- 2294 tasks across 12 Python repositories")
    text("- Given codebase + issue description, submit a PR")
    text("- Evaluation metric: unit tests")
    image("images/swebench.png", width=800)
    link("https://llm-stats.com/benchmarks/swe-bench-verified")

    text("**TerminalBench** "), link("https://arxiv.org/abs/2601.11868"), link(title="website", url="https://www.tbench.ai/")
    image("images/terminal-bench.png", width=700)
    text("- Computer terminal environments: simple and universal")
    text("- 229 tasks crowdsourced from 93 contributors, 89 tasks constitute Terminal-Bench 2.0")
    image("images/terminal-bench-human-time.png", width=600)
    image("images/terminal-bench-results.png", width=600)
    link("https://llm-stats.com/benchmarks/terminal-bench")

    text("**CyBench** "), link("https://arxiv.org/abs/2408.08926")
    image("images/cybench.png", width=700)
    text("- 40 Capture the Flag (CTF) tasks")
    text("- Use first-solve time as a measure of difficulty")
    image("images/cybench-agent.png", width=700)
    image("images/cybench-results.png", width=600)
    link("https://llm-stats.com/benchmarks/cybench")

    text("**MLEBench** "), link("https://arxiv.org/abs/2410.07095")
    text("- 75 Kaggle competitions (require training models, processing data, etc.)")
    image("images/mlebench.png", width=800)
    image("images/mlebench-results.png", width=700)

    text("Agent scaffolds "), post_link("https://www.philschmid.de/agents-2.0-deep-agents")
    image("https://www.philschmid.de/static/blog/agents-2.0-deep-agents/overview.png", width=400)
    text("- Explicit planning: keep a todo list that gets checked off")
    text("- Hierarchical delegation: agents calling other sub-agents (clean context)")
    text("- Persistent memory: read/write files")
    text("- Extreme context engineering: explicit more instructions on process")

    text("Summary:")
    text("- Agents dramatically enhance the capability surface of language models")
    text("- Agent scaffolds are very important")
    text("- Evaluating agents = evaluating agent scaffold + language model")


def pure_reasoning_benchmarks():
    text("- All of the tasks so far require linguistic and world knowledge.")
    text("- Can we isolate **reasoning** from knowledge?")
    text("- Arguably, reasoning captures a more pure form of intelligence (isn't just about memorizing facts).")

    text("**ARC-AGI** "), link(title="website", url="https://arcprize.org/arc-agi")
    text("- 100\% solvable by humans, but challenging for AI")
    text("- Each task is unique, so memorization doesn't help.")

    text("- ARC-AGI-1 (2019): first iteration")
    image("https://arcprize.org/media/images/arc-task-grids.jpg", width=800)

    text("- ARC-AGI-2 (March 2025): more multi-step reasoning")
    image("https://arcprize.org/media/images/blog/arc-agi-2-unsolved-1.png", width=800)

    image("images/arc-agi-results.png", width=700)
    text("- Pretrained language models didn't move the needle")
    text("- Reasoning models (o1, o3) started making things take off")

    text("- ARC-AGI-3 (March 2026): interactive environments "), post_link("https://arcprize.org/media/ARC_AGI_3_Technical_Report.pdf")
    image("images/arc-agi-3.png", width=300)
    image("images/arc-agi-3-results.png", width=500)

    text("Summary:")
    text("- Goal is to disentangle reasoning from knowledge (difficult to do!)")
    text("- Constrained to human reasoning (not superhuman reasoning)")
    text("- Clearly exposes gaps in current models")


def safety_benchmarks():
    image("https://www.team-bhp.com/forum/attachments/road-safety/2173645d1625144681-will-crash-test-rating-change-if-higher-variant-chosen-images-30.jpeg", width=400)
    text("What does safety mean for AI?")

    text("**HarmBench** "), link("https://arxiv.org/abs/2402.04249")
    text("- Based on 510 harmful behaviors that violate laws or norms")
    link(title="HarmBench on HELM", url="https://crfm.stanford.edu/helm/safety/latest/#/leaderboard/harm_bench")
    link(title="Example of safety failure", url="https://crfm.stanford.edu/helm/safety/latest/#/runs/harm_bench:model=anthropic_claude-3-7-sonnet-20250219?instancesPage=4")

    text("**AIR-Bench** "), link("https://arxiv.org/abs/2407.17436")
    text("- Based on regulatory frameworks and company policies")
    text("- Taxonomized into 314 risk categories, 5694 prompts")
    image("https://crfm.stanford.edu/helm/assets/air-overview-DpBbyagA.png", width=800)
    link(title="HELM AIR-Bench", url="https://crfm.stanford.edu/helm/air-bench/latest/#/leaderboard")

    text("Jailbreaking:")
    text("- Language models are trained to refuse harmful instructions")
    text("- Greedy Coordinate Gradient (GCG) automatically optimizes prompts to bypass safety "), link("https://arxiv.org/pdf/2307.15043")
    text("- Transfers from open-weight models (Llama) to closed models (GPT-4)")
    image("images/gcg-examples.png", width=800)

    text("What is safety?")
    text("- Many aspects of safety are strongly contextual (politics, law, social norms - which vary across countries)")
    text("- Many risks are quite varied (hallucinations, sycophancy, abetting crimes, inequality, losing critical thinking)")

    text("**Dual-use**: capable cybersecurity agents (Mythos) can be used to hack into a system or to do penetration testing")


def realism():
    text("**Ecological validity**: how well does an evaluation capture real-world use?")
    text("- Exam benchmarks (e.g., GPQA) are far away from real-world use.")
    text("- Chatbot Arena prompts are from real people, but distribution is uncontrolled.")

    text("**GDPVal** (OpenAI) "), link("https://arxiv.org/pdf/2510.04374")
    text("- 44 occupations from top 9 sectors according to US GDP")
    text("- Tasks come from professionals with ~14 years of experience")
    image("images/gdpval.png", width=700)

    text("**MedHELM** "), link("https://arxiv.org/abs/2505.23802")
    text("- Previous medical benchmarks were based on standardized exams")
    text("- 121 clinical tasks sourced from 29 clinicians, mixture of private and public datasets")
    image("https://crfm.stanford.edu/helm/assets/medhelm-overview-CND0EIsy.png", width=700)
    link(title="MedHELM", url="https://crfm.stanford.edu/helm/medhelm/latest/#/leaderboard")

    text("**Clio** (Anthropic) "), link("https://arxiv.org/abs/2412.13678")
    text("- Use language models to analyze real user data")
    text("- Share general patterns of what people are asking")
    image("images/clio-table4.png", width=700)

    text("Unfortunately, realism and privacy are sometimes at odds with each other.")


def validity():
    text("How do we know our evaluations are valid?")

    text("### Train-test overlap")
    text("- Machine learning 101: don't train on your test set")
    text("- Pre-foundation models (ImageNet, SQuAD): well-defined train-test splits")
    text("- Today: train on the Internet and don't tell people about your data")

    text("Route 1: try to infer train-test overlap from model")
    text("- Exploit exchangeability of data points "), link("https://arxiv.org/pdf/2310.17623")
    image("images/contamination-exchangeability.png", width=500)

    text("Route 2: encourage reporting norms (e.g., people report confidence intervals)")
    text("- Model providers should report train-test overlap "), link("https://arxiv.org/abs/2410.08385")

    text("Route 3: use fresh evals")
    text("- LiveCodeBench, UncheatableEval: scrape new webpages")
    text("- Timestamps aren't always safe due to copying either")

    text("Route 4: use private evals")
    text("- Companies use internal code bases that aren't on the Internet")
    text("- Use your personal writings")
    text("- Easiest for perplexity")

    text("### Dataset quality")
    text("- Fixed up SWE-Bench to produce SWE-Bench Verified "), post_link("https://openai.com/index/introducing-swe-bench-verified/")
    text("- Create Platinum versions of benchmarks "), link("https://arxiv.org/abs/2502.03461")
    image("https://pbs.twimg.com/media/GjICXQlWkAAYnDS?format=jpg&name=4096x4096", width=700)
    image("https://pbs.twimg.com/media/GjICcGQXYAAM4o1?format=jpg&name=4096x4096", width=800)
    text("- Problems with agentic benchmarks: insufficient test cases, trivial agent can solve task "), link("https://arxiv.org/abs/2507.02825")
    text("- Docent: use LLM to inspect agent traces to detect problems "), post_link("https://transluce.org/introducing-docent")


def how_to_think_about_evaluation():
    text("### What's the point of evaluation?")
    text("There is no one true evaluation; it depends on what question you're trying to answer.")
    text("1. User or company wants to make a purchase decision (model A or model B) for their use case (e.g., customer service chatbots).")
    text("2. Researchers want to measure the raw capabilities of a model (e.g., intelligence).")
    text("3. We want to understand the benefits + harms of a model (for business and policy reasons).")
    text("4. Model developers want to get feedback to improve the model.")

    text("### What are we evaluating?")
    text("- Pre-foundation models, we evaluated **methods** (standardized train-test splits).")
    text("- Today, we're (mostly) evaluating **models/systems** (anything goes).")

    text("There are some exceptions...")
    text("- nanogpt speedrun: fixed data, compute time to get to a particular validation loss")
    image("images/karpathy-nanogpt-speedrun.png", width=600), post_link("https://x.com/karpathy/status/1846790537262571739")

    text("Evaluating methods encourage algorithmic innovation from researchers.")
    text("Evaluating models/systems is useful for downstream users.")

    text("Either way, we need to define the rules of the game!")


if __name__ == "__main__":
    main()
