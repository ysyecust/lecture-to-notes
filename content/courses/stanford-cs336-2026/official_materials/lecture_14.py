from dataclasses import dataclass
import numpy as np
import itertools
import mmh3
from edtrace.file_util import download_file
from edtrace import text, image, link
from lecture_13 import the_pile
from lecture_util import article_link, post_link
from references import dolma_2024, the_pile_2020, dclm_2024

def main():
    text("## Lecture 14: Data II")
    text("Last lecture:")
    text("- Live service (e.g., GitHub) → dump/crawl (e.g., GitHub Archive) → processed data (e.g., The Stack)")
    text("- Considerations: terms of service, copyright (licenses or fair use)")

    text("This lecture:")
    text("- Data pipeline: transformation, filtering, deduplication, mixing")
    text("- Mid-training + SFT: synthetic data")

    # Data pipeline
    transformation()
    filtering()
    deduplication()
    data_mixing()

    # Post-training data
    post_training_data()

    text("Summary:")
    text("- Filtering: train classifier (language id, quality, toxicity) for what good looks like")
    text("- Deduplication: hashing scales to large datasets for fuzzy matching")
    text("- Mixing: try mixtures at small scale, extrapolate to optimal mixture and large scale")
    text("- Applications: language identification, quality filtering, toxicity filtering")
    text("- Post-training data: looks like evaluations, use of synthetic data")
    text("- A lot of data work is domain-specific, looking at examples, etc.")


def transformation():
    text("Raw data does not come as text.")
    text("It is HTML, PDF (arxiv), or directories (code repositories).")

    text("HTML to text (main one):")
    text("- Remove boilerplate (e.g., navigation, ads) and extract content")
    text("- What about images, tables, etc.?")
    text("- Inherently lossy (need to linearize)")
    text("- Tools (rule-based): trafilatura, resiliparse, jusText, lynx, etc.")
    text("- Accuracy matters: "), link(dclm_2024)
    image("images/dclm-wet.png", width=300)

    text("FinePDFs "), post_link("https://huggingface.co/spaces/HuggingFaceFW/FinePDFsBlog")
    image("https://huggingfacefw-finepdfsblog.hf.space/_astro/pdf-description.Cb49jXc6_Z17eX4E.webp", width=600)
    text("- Source: Common Crawl")
    text("- Recrawl truncated PDFs (since they are big)")
    text("- OCR (RolmOCR) using a VLM or Docling (make these run fast)")
    text("- Lots of cleanup and filtering")
    text("- A lot of layout information is missing")


def filtering():
    text("Algorithmic building block:")
    text("- Given some **target data** T and lots of **raw data** R, find subset T' of R similar to T.")
    image("images/raw-target-schema.png", width=600)

    text("Applications:")
    text("- Language identification (English versus rest)")
    text("- Quality filtering (high quality versus low quality)")
    text("- Toxicity filtering (non-toxic versus toxic)")

    text("Desiderata for filtering algorithm:")
    text("- Generalize from the target data (want T and T' to be different)")
    text("- Extremely fast (have to run it on R, which is huge)")

    text("Survey paper on data selection "), link("https://arxiv.org/abs/2402.16827")

    text("General framework: Given target T and raw R, find subset of R similar to T")
    text("1. Estimate some model based on R and T and derive a scoring function")
    text("2. Keep examples in R based on their score")

    text("Types of classifiers:")
    text("- Generative model of T (KenLM): score(x) = p_T(x)")
    text("- Simple classifier (fastText): score(x) = p(T | x)")
    text("To use: keep examples x with score(x) >= threshold (stochastically)")

    text("Model-based filtering?")
    text("- Some deliberately do not use model-based filtering (C4, Gopher, RefinedWeb, FineWeb, Dolma)")
    text("- Some use model-based filtering (GPT-3, LLaMA, DCLM) [becoming the norm]")

    text("Language identification:")
    text("- Goal: find text of a specific language (e.g., English)")
    text("- fastText language identification "), article_link("https://fasttext.cc/docs/en/language-identification.html")
    text("- Off-the-shelf classifier")
    text("- Supports 176 languages")
    text("- Trained on multilingual sites: Wikipedia, Tatoeba (translation site) and SETimes (Southeast European news)")
    text("- Dolma keeps pages with p(English) >= 0.5 "), link(dolma_2024)

    text("OpenMathText "), link("https://arxiv.org/pdf/2310.06786")
    text("- Goal: curate large corpus of mathematical text from CommonCrawl")
    text("- Use rules to filter (e.g., contains latex commands)")
    text("- KenLM trained on ProofPile, keep if perplexity < 15000")
    text("- Trained fastText classifier to predict mathematical writing, threshold is 0.17 if math, 0.8 if no math")
    text("- Result: produced 14.7B tokens, used to train 1.4B models that do better than models trained on 20x data")

    text("GPT-3 "), link("https://arxiv.org/pdf/2005.14165")  # Appendix A
    text("- Positives: samples from {Wikipedia, WebText2, Books1, Books2}")
    text("- Negatives: samples from CommonCrawl")
    text("Train linear classifier based on word features "), article_link("https://spark.apache.org/docs/latest/ml-features#tokenizer")
    text("Keep documents stochastically based on score")
    def keep_document(score: float) -> bool:
        return np.random.pareto(9) > 1 - score

    text("LLaMA/RedPajama "), link("https://arxiv.org/pdf/2302.13971")
    text("- Positives: samples from pages **referenced** by Wikipedia")
    text("- Negatives: samples from CommonCrawl")
    text("- Keep documents that are classified positive")

    text("phi-1 "), link("https://arxiv.org/pdf/2306.11644")
    text("- Philosophy: really high quality data (textbooks) to train a small model (1.5B)")
    text("- Includes synthetic data from GPT 3.5 (later: GPT-4) and filtered data")
    R = "Python subset of the Stack"   # Raw data
    prompt = "determine its educational value for a student whose goal is to learn basic coding concepts"
    T = "Use GPT-4 with this prompt to classify 100K subset of R to get positive examples"
    text("- Train random forest classifier on T using output embedding from pretrained codegen model")
    text("- Select data from R that is classified positive by the classifier")
    text("Result on [HumanEval](https://huggingface.co/datasets/openai_humaneval):")
    text("- Train 1.3B LM on Python subset of The Stack (performance: 12.19% after 96K steps)")
    text("- Train 1.3B LM on new filtered subset (performance: 17.68% after 36K steps) - better!")

    text("Toxicity filtering in Dolma "), link(dolma_2024)
    text("- Dataset: Jigsaw Toxic Comments dataset (2018) "), link(title="dataset", url="https://www.kaggle.com/datasets/julian3833/jigsaw-toxic-comment-classification-challenge")
    text("- Project goal: help people have better discussions online "), article_link("https://www.kaggle.com/competitions/jigsaw-toxic-comment-classification-challenge/discussion/46064")
    text("- Data: comments on Wikipedia talk page annotated with {toxic, severe_toxic, obscene, threat, insult, identity_hate}")

    text("Scale-dependent effects of filtering:")
    text("- No single optimal threshold for filtering")
    text("- If training for longer, want more (lower quality) data")
    text("- If training for shorter, want less (higher quality) data")
    image("images/data-filtering-scale.png", width=800)

    text("Summary:")
    text("- Filtering is critical for building a good model")
    text("- Recipe: define target data (what good looks like), extrapolate to raw data")
    

def deduplication():
    text("Two types of duplicates:")
    text("- Exact duplicates (mirror sites, GitHub forks) "), link(title="Gutenberg mirrors", url="https://www.gutenberg.org/MIRRORS.ALL")
    text("- Near duplicates: same text differing by a few tokens")

    text("Examples of near duplicates:")
    text("- Terms of service and licenses "), link(title="MIT license", url="https://opensource.org/license/mit")
    text("- Formulaic writing (copy/pasted or generated from a template) "), image("https://d3i71xaburhd42.cloudfront.net/4566c0d22ebf3c31180066ab23b6c445aeec78d5/5-Table1-1.png", width=600)
    text("- Minor formatting differences in copy/pasting")

    text("Product description repeated 61,036 times in C4")
    text("'“by combining fantastic ideas, interesting arrangements, and follow the current trends in the field of that make you more inspired and give artistic touches. We’d be honored if you can apply some or all of these design in your wedding.  believe me, brilliant ideas would be perfect if it can be applied in real and make the people around you amazed!")
    link(title="example page", url="https://www.amazon.co.uk/suryagede-100-Graffiti-Gas-Mask/dp/B07CRHT3RG")

    text("Deduplication training data makes language models better "), link("https://arxiv.org/pdf/2107.06499")
    text("- Train more efficiently (because have fewer tokens)")
    text("- Avoid memorization (can mitigate copyright, privacy concerns)")

    text("Design space:")
    text("1. What is an item (sentence, paragraph, document)?")
    text("2. How to match (exact match, existence of common subitem, fraction of common subitems)?")
    text("3. What action to take (remove all, remove all but one)?")

    text("Key challenge:")
    text("- Deduplication is fundamentally about comparing items to other items")
    text("- Need linear time algorithms to scale")

    hash_functions()
    exact_deduplication()
    jaccard_minhash()
    locality_sensitive_hashing()


def hash_functions():
    text("- Hash function h maps item to a hash value (integer or string)")
    text("- Hash value much smaller than item")
    text("- Hash collision: h(x) = h(y) for x ≠ y")

    text("Tradeoff between efficiency and collision resistance "),  article_link("https://softwareengineering.stackexchange.com/questions/49550/which-hashing-algorithm-is-best-for-uniqueness-and-speed")
    text("- Cryptographic hash functions (SHA-256): collision resistant, slow (used in bitcoin)")
    text("- DJB2, MurmurHash, CityHash: not collision resistant, fast (used for hash tables)")

    text("We will use MurmurHash:")
    h = mmh3.hash("hello")  # @inspect h


def exact_deduplication():
    text("**Simple example**")
    text("1. Item: string")
    text("2. How to match: exact match")
    text("3. Action: remove all but one")

    # Original items
    items = ["Hello!", "hello", "hello there", "hello", "hi", "bye"]  # @inspect items

    # Compute hash -> list of items with that hash
    hash_items = itertools.groupby(sorted(items, key=mmh3.hash), key=mmh3.hash)

    # Keep one item from each group
    deduped_items = [next(group) for h, group in hash_items]  # @inspect deduped_items

    text("- Pro: simple, clear semantics, high precision")
    text("- Con: does not deduplicate near duplicates")
    text("- This code is written in a MapReduce way, can easily parallelize and scale")

    text("**C4** "), link("https://arxiv.org/pdf/1910.10683v4")
    text("1. Item: 3-sentence spans")
    text("2. How to match: use exact match")
    text("3. Action: remove all but one")
    text("Warning: when a 3-sentence span is removed from the middle of a document, the resulting document might not be coherent")


def jaccard_minhash():
    text("Let's now look at approximate set membership.")
    text("First we need a similarity measure.")

    text("### Jaccard similarity")
    text("Definition: Jaccard(A, B) = |A intersect B| / |A union B|")
    A = {"1", "2", "3", "4"}
    B = {"1", "2", "3", "5"}

    def compute_jaccard(A, B):
        intersection = len(A & B)  # @inspect intersection
        union = len(A | B)  # @inspect union
        return intersection / union
    jaccard = compute_jaccard(A, B)  # @inspect jaccard

    text("Definition: two documents are **near duplicates** if their Jaccard similarity >= threshold")

    text("Algorithmic challenge: find near duplicates in linear time")

    text("### MinHash")
    text("MinHash: a random hash function h so that Pr[h(A) = h(B)] = Jaccard(A, B)")

    text("Normally, you want different items to hash to different hashes")
    text("...but here, you want collision probability to depend on similarity")

    def minhash(S: set[str], seed: int):
        return min(mmh3.hash(x, seed) for x in S)

    text("Characteristic matrix representation:")
    text("item | A | B", verbatim=True)
    text("1    | 1 | 1", verbatim=True)
    text("2    | 1 | 1", verbatim=True)
    text("3    | 1 | 1", verbatim=True)
    text("4    | 1 | 0", verbatim=True)
    text("5    | 0 | 1", verbatim=True)

    text("Random hash function induces a permutation over items")
    text("Look at which item is first in A and which item is first in B.")
    text("Each item has the same probability as being first (min)")
    text("- If 1, 2, 3 is first, then first in A = first in B.")
    text("- If 4, 5 is first, then first in A ≠ first in B.")

    # Verify MinHash approximates Jaccard as advertised
    n = 100  # Generate this many random hash functions
    matches = [minhash(A, seed) == minhash(B, seed) for seed in range(n)]  # @stepover
    estimated_jaccard = len([m for m in matches if m]) / len(matches)  # @inspect estimated_jaccard
    assert abs(estimated_jaccard - jaccard) < 0.01

    text("Now we can hash our items, but a collision doesn't tell us Jaccard(A, B) > threshold.")


def locality_sensitive_hashing():
    text("Locality sensitive hashing (LSH) "), link(title="book chapter", url="http://infolab.stanford.edu/~ullman/mmds/ch3n.pdf")

    text("Suppose we hash examples with just one MinHash function")
    text("P[A and B collide] = Jaccard(A, B)")
    text("On average, more similar items will collide, but very stochastic...")

    text("Goal: have A and B collide if Jaccard(A, B) > threshold")
    text("We have to somehow sharpen the probabilities...")

    text("Solution: use n hash functions")
    text("Break up into b bands of r hash functions each (n = b * r)")

    n = 12      # Number of hash functions
    b = 3       # Number of bands
    r = 4       # Number of hash functions per band
    text("Hash functions:")
    text("h1 h2 h3 h4  |  h5 h6 h7 h8  |  h9 h10 h11 h12", verbatim=True)

    text("Key: A and B collide if for *some* band, *all* its hash functions return same value")
    text("As we will see, the and-or structure of the bands sharpens the threshold")

    text("Given Jaccard(A, B), what is the probability that A and B collide?")

    def get_prob_collision(sim, b, r):  # @inspect sim @inspect b @inspect r
        prob_match = sim ** r                        # Probability that a fixed band matches  @inspect prob_match
        prob_collision = 1 - (1 - prob_match) ** b   # Probability that some band matches  @inspect prob_collision
        return prob_collision

    text("**Example**")
    prob_collision = get_prob_collision(sim=0.8, b=5, r=10)  # @inspect prob_collision
    image("https://cdn.sanity.io/images/vr8gru94/production/b470799575b8e77911bacb8500977afef06d6c85-1280x720.png", width=600)


    sims = [0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.98]
    probs = {sim: get_prob_collision(sim=sim, b=10, r=10) for sim in sims}  # @inspect probs @stepover

    text("Increasing r sharpens the threshold and moves the curve to the right (harder to match)")
    probs = {sim: get_prob_collision(sim=sim, b=10, r=20) for sim in sims}  # @inspect probs @stepover

    text("Increasing b moves the curve to the left (easier to match)")
    probs = {sim: get_prob_collision(sim=sim, b=20, r=20) for sim in sims}  # @inspect probs @stepover
    image("https://cdn.sanity.io/images/vr8gru94/production/aace49fa240778e8ecf6e85ad08a2de7f5385566-1280x720.png", width=600)

    text("Example setting "), link("https://arxiv.org/pdf/2107.06499"), text(": n = 9000, b = 20, r = 450")
    b = 20
    r = 450
    text("What is the threshold (where the phase transition happens)?")
    threshold = (1 / b) ** (1 / r)  # @inspect threshold

    text("Probability that a fixed band matches:")
    prob_match = (1 / b)  # @inspect prob_match
    text("Probability that A and B collide is a constant (≈ 1-1/e):")
    prob_collision = 1 - (1 - 1 / b) ** b  #  @inspect prob_collision


def billion(x):
    return x * 10**9

def trillion(x):
    return x * 10**12


def data_mixing():
    text("Recall that language models are trained on multiple data sources.")

    text("Datasets in Marin: "), link(title="token viewer", url="https://huggingface.co/spaces/marin-community/token-count-viewer")
    image("images/marin-token-viewer.png", width=800)

    text("The Pile "), link(the_pile_2020)
    image("https://stanford-cs324.github.io/winter2022/lectures/images/the-pile.png", width=600)
    text("Key question: what distribution over the data sources should we use?")

    text("Example:")
    sources = {"Wikipedia", "CC", "GitHub"}
    p = {"Wikipedia": 0.3, "CC": 0.5, "GitHub": 0.2}  # One possible data mixture

    text("Baselines:")
    text("- Vibes: set p(s) manually based on intuition (quite common)")
    text("- Uniform sampling: sample uniformly (p(s) ∝ 1)")
    text("- Proportional mixing: sample proportional to the number of tokens in a source (p(s) ∝ num_tokens(s))")

    text("Intuition: should upweight higher quality sources")
    text("However...")
    text("1. We want to ensure diversity (e.g., across incomparable sources: literature, code, papers)")
    text("2. Each source is finite, so if put too much weight on a small source, then need to epoch over it")
    
    text("This last point is important and a bit subtle.")
    text("Example:")
    source_token_counts = {
        "low": trillion(10),  # 10T tokens (abundant) @stepover
        "high": billion(10),  # 10B tokens (scarce) @stepover
    }
    p = {"low": 0.5, "high": 0.5}  # Naive data mixture
    train_tokens = trillion(1)  # Train for 1T tokens @stepover
    low_num_epochs = (p["low"] * train_tokens) / source_token_counts["low"]  # @inspect low_num_epochs
    high_num_epochs = (p["high"] * train_tokens) / source_token_counts["high"]  # @inspect high_num_epochs
    text("50x epochs on high quality data...can lead to overfitting!")

    text("UniMax "), link("https://arxiv.org/abs/2304.09151")
    text("- Setting: balancing different languages for multilingual models")
    text("- Previous work: between uniform and proportional mixing (p(s) ∝ num_tokens(s)^α for α in [0, 1])")
    text("- Idea: sample sources uniformly but with a hard **cap** C on number of epochs for any source")
    text("- Specifically, p(s) * num_training_tokens ≤ C for all sources s")

    text("Regression-based mixing "), link("https://arxiv.org/abs/2407.01492"), link("https://arxiv.org/pdf/2602.12237")
    image("images/regmix.png", width=700)
    text("- Define distribution over mixtures `p` (e.g., Dirichlet) ")
    text("- Define regression method (e.g., linear, gradient boosted trees)")
    text("- Define target based on downstream evals (careful not to overfit!)")
    text("- Discrepancy between small and large scale (tradeoff cost and accuracy)")
    image("images/data-mixing-methods.png", width=700)
    text("Hope 1: regression model is accurate at minimizer 🙏")
    text("Hope 2: optimal data mixtures transfer from small to large scale 🙏")

    text("Hold on. There's at least one scale-dependent effect:")
    source_token_counts = {
        "low": trillion(10),  # 10T tokens (abundant) @stepover
        "high": billion(10),  # 10B tokens (scarce) @stepover
    }
    text("- If train small models on low token counts:")
    p = {"low": 0.1, "high": 0.9}  # More mass on high quality data
    text("- But if train large model on this mixture, we will epoch a ton on high quality data and overfit!")

    text("Simulated epoching "), link("https://arxiv.org/pdf/2501.11747")
    text("- General idea: make small scale look like large scale (general theme of this course)")
    text("- Instantiation: downsample all sources proportionally")
    small_run_tokens = billion(10)  # @stepover
    large_run_tokens = trillion(1)  # @stepover
    ratio = small_run_tokens / large_run_tokens  # @inspect ratio
    downsampled_source_token_counts = {s: count * ratio for s, count in source_token_counts.items()}  # @inspect downsampled_source_token_counts
    text("- In this downsampled mixture, models that epoch too much won't look good.")
    text("- So the optimum will be more balanced.")
    p = {"low": 0.7, "high": 0.3}  # More mass on high quality data

    text("Summary:")
    text("- Problem: how to weight different data sources (e.g., Wikipedia, general, code)")
    text("- Regression-based mixing: estimate mixture → loss at small scale, optimize (analogous to scaling laws)")
    text("- Important consideration: epoching and overfitting (solution: cap or simulated)")


def post_training_data():
    text("Recipe:")
    text("1. Define a set of environments")
    text("2. Define a set of tasks / prompts")
    text("3. Collect responses from a strong model (teacher)")

    text("OpenThoughts "), link("https://arxiv.org/abs/2506.04178")
    text("- 1.2M examples using QwQ-32B as a teacher")
    text("- Questions come from 27 human and synthetic sources (e.g., StackExchange, NuminaMath, Chemistry)")
    image("images/openthoughts-sources.png", width=500)
    text("- Sampling multiple (16) responses per prompt is helpful")
    text("- Better models aren't necessarily better teachers: QwQ-32B is a better teacher than DeepSeek-R1")
    text("- Answer filtering wasn't helpful")
    text("- Smaller high quality sources (e.g., OpenMath-2-Math) is better than large diverse sources")
    image("images/openthoughts-pipeline.png", width=600)

    text("SWE-smith "), link("https://arxiv.org/abs/2504.21798")
    image("images/swe-smith.png", width=500)
    text("- Given a repository, use LM to generate tasks (introduce bugs with LM)")
    text("- 128 GitHub repositories yields 50K tasks")

    text("SWE-Zero "), link("https://arxiv.org/abs/2604.01496")
    text("- SWE tasks have heavy dependencies (unlike math or coding contests)")
    text("- Setting up thousands of Docker images is an infrastructural nightmare")
    text("- Observation: strong models can solve many tasks without execution feedback")
    image("images/swezero-noexec.png", width=600)
    text("Key: strong models have internal \"world model\" of code semantics")
    text("- SWE-Zero: 300K agent trajectories that don't require repository-specific execution")
    text("- 150K GitHub PRs")
    text("- OpenHands scaffold, remove future git commits to prevent \"git hacking\" by agent")
    image("images/swezero-prompt.png", width=600)
    text("- Distilled from Qwen3-Coder-480B + filtering (try to execute anyway)")
    text("- SWE-Hero: 13K agent trajectories that do require execution feedback")
    image("images/swezero-results.png", width=700)

    text("SWE-rebench "), link("https://arxiv.org/pdf/2505.20411")
    text("- 21K interactive Python SWE tasks from 3.4K GitHub repositories")
    text("- 450K PRs from GitHub and GitHub Archive")
    text("- Used Qwen 2.5-72B-Instruct to install dependencies and assess PR quality")
    image("images/swe-rebench.png", width=600)

    text("SWE-ZERO-12M-trajectories "), link(title="data", url="https://huggingface.co/datasets/AlienKevin/SWE-ZERO-12M-trajectories")
    text("- Scale SWE-Zero up to 12M agent trajectories")
    text("- Used the SWE-rebench-v2 tasks (32K executable tasks + 120K nonexecutable tasks)")
    text("- Ran mini-coder-1.7b (very small model, 50.4 pass@100), mini-swe-agent scaffold")
    text("- [Example](https://huggingface.co/datasets/AlienKevin/SWE-ZERO-12M-trajectories/viewer/default/train?row=5&conversation-viewer=0)")

    text("Summary:")
    text("- Generating prompts: fully-synthetic, semi-synthetic (real environment + synthetic tasks), real (GitHub PRs)")
    text("- Responses: from capable models (that are also good teachers)")
    text("- Code environments are painful")
    text("- Lots of filtering and other details")


if __name__ == "__main__":
    main()
