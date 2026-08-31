from edtrace import text, image, link
from lecture_util import article_link
from references import dclm_2024, nemotron_cc_2024, olmo_2_2025, llama_3_2024, gpt2_2019, openwebtext_2019, gopher_2021, alpaca_2023


def main():
    text("## Lecture 13: Data I")
    text("Previous lectures: how to train a model *given data*")
    text("Next two lectures: *what data* should we train on?")

    motivation()

    # Origin of data
    raw_sources()    # What does data come from?
    copyright()      # What data can we use?

    # Sources of data
    common_crawl()   # Web crawl
    wikipedia()      # General knowledge
    github()         # Code
    arxiv()          # Research papers

    # Data from various models
    bert()                # Wikipedia, books (trained BERT) [2019]
    gpt2_webtext()        # pages based on Reddit links (trained GPT-2) [2019]
    ccnet()               # Filter Common Crawl based on Wikipedia [2019]
    t5_c4()               # Filter using rules (trained T5) [2019]

    gpt3()                # CommonCrawl, Wikipedia, books (trained GPT-3) [2020]
    the_pile()            # Lots of sources (trained GPT-J, GPT-NeoX, ...) [2021]
    gopher_massivetext()  # Filter using rules (trained Gopher) [2021]
    llama()               # CommonCrawl, CCNet, StackExchange, etc. (trained LLaMA) [2022]
    refinedweb()          # CommonCrawl (used to train Falcon) [2023]
    dolma()               # Lots of different sources [2024]
    dclm()                # Filtered using good quality classifier [2024]
    nemotron_cc()         # Lots of tokens [2024]
    the_stack()           # Code dataset
    common_pile()         # Properly licensed data

    text("### Summary")
    text("- Key lesson: Data does not fall from the sky. You have to work to get it.")
    text("- Live service → raw data → processed data (transformation, filtering, deduplication)")
    text("- Data is the key ingredient that differentiates language models")
    text("- Legal and ethical issues (e.g., copyright and privacy)")
    text("- Much of this pipeline is heuristic, many opportunities to improve!")


def motivation():
    text("**Data** is the most important thing to get right in training language models.")

    text("One justification: let's see what companies disclose.")
    text("Open-weight models (e.g., Llama 3 "), link(llama_3_2024), text(" have full transparency into architecture")
    text("...and even training procedures")
    text("...but basically no information on data.")
    image("images/llama3-data.png", width=700)
    
    text("Reasons for secrecy:")
    text("1. Competitive dynamics")
    text("2. Copyright liability")

    text("- Before foundation models, data work meant heavy annotation of labeled data for supervised learning.")
    text("- Now there's less annotation, but there's still a lot of curation and cleaning.")
    text("- Data is fundamentally a long-tail problem, scales with human effort (unlike architectures, systems).")

    text("Stages of training:")
    text("1. Pre-training: train on raw text (e.g., documents from the web)")
    text("2. Mid-training: train more on high quality data to enhance capabilities")
    text("3. Post-training: train on chat transcripts or reinforcement learning")
    text("In practice, the lines are blurry and there could be more stages")
    text("...but the basic trend is throughout training, we go from")
    text("large amounts of lower quality data to")
    text("small amounts of high quality data.")

    text("Terminology:")
    text("- Base model: after pre-training + mid-training")
    text("- Instruct/chat model: after post-training")
    text("(Increasingly, base models are not released - e.g., Qwen3.5-397B-A17B is an instruct model.)")

    text("Example (OLMo from AI2) "), link(olmo_2_2025)
    text("1. **Pre-training**")
    image("images/olmo2-pretraining.png", width=600)
    text("2. **Mid-training**")
    image("images/olmo2-dolmino.png", width=600)
    text("3. **Post-training** "), link("https://arxiv.org/pdf/2411.15124")
    image("images/tulu.png", width=600)

    text("What are these datasets?  How are they chosen and processed?")


def raw_sources():
    text("One might often hear: *language models are trained on the entire Internet*.")
    text("Slightly more accurately, ~Internet~ public (world wide) web.")
    text("But this is not quite right either...")

    text("First, the web consists of a set of live servers that one can connect to:")
    text("`$ curl https://cs336.stanford.edu/`")

    text("You can't train on live servers.")
    text("A **crawler**:")
    text("- Discovers webpages (starting from a seed set)")
    text("- Downloads the discovered webpages")

    text("However, you can't download and train on all the webpages.")

    text("Dynamic content:")
    text("- Many sites these days are apps")
    text("- URL doesn't change")
    text("- Need to click buttons and submit forms to access content")
    text("- Examples: Discord, wandb")

    text("Authentication:")
    text("- Sometimes need login with an account (and pay usually)")
    text("- Example: Facebook, X, LinkedIn, NYTimes (huge content behind walled gardens)")

    text("Technical restrictions:")
    text("- Not allowed to download some content based on `robots.txt` ([example](https://www.nytimes.com/robots.txt)) (voluntary)")
    text("- Website might use Cloudflare to detect and block bot activity (present CAPTCHAs)")
    text("- Website might block certain IP addresses / countries")
    text("- Website might have rate limits")
    
    text("Legal restrictions:")
    text("- Terms of service (ToS) might prohibit downloading using bots")
    text("- You might not have a license to copy the webpages (for training)")

    text("Decline of consent "), link("https://arxiv.org/abs/2407.14933")
    text("- Examined restrictions (robots.txt, ToS) for URLs in common datasets (C4, RefinedWeb, Dolma)")
    text("- Restrictions have increased over time")
    image("images/decline-consent.png", width=700)

    text("When crawlers are not well-behaved:")
    image("images/anthropic-crawling.png", width=500)
    text("- Factors: ToS, robots.txt, server load (degrades service, costs website money)")
    text("- And then there is copyright (more later)...")

    text("Shadow libraries "), article_link("https://en.wikipedia.org/wiki/Shadow_library")
    text("- Technically part of the web")
    text("- Examples: Library Genesis (LibGen), Z-Library, Anna's Archive, Sci-Hub")
    text("- Disregards copyright and bypasses paywalls (e.g., Elsevier)")
    text("- Received takedown orders, lawsuits, blocked in various countries")
    text("- Usually controls are circumvented, have servers in various countries")
    text("- Some argue this makes freely available what should be free")
    text("- From a legal perspective, this is piracy and copyright infringement")
    text("- LibGen has ~4M books (2019), Sci-Hub has ~88M papers (2022)")

    text("Summary:")
    text("- The Internet is huge")
    text("- Many technical and legal restrictions on what data one can access")


def copyright():
    text("What data is legal to use (for training)?")

    text("### Intellectual property law")
    text("- Goal: *incentivize* the creation of intellectual goods")
    text("- Types of intellectual property: copyright, patents, trademarks, trade secrets.")

    text("**Copyright law**:")
    text("- Goes back to 1709 in England (Statute of Anne), first time regulated by governments and courts "), article_link("https://en.wikipedia.org/wiki/Statute_of_Anne")
    text("- In United States, most recent: Copyright Act of 1976 "), article_link("https://en.wikipedia.org/wiki/Copyright_Act_of_1976")
    text("- Copyright protection applies to *'original works of authorship fixed in any tangible medium of expression, now known or later developed, from which they can be perceived, reproduced, or otherwise communicated, either directly or with the aid of a machine or device'*")

    text("- Collections are not original works so hence not copyrightable (e.g., telephone directories) unless there is some creativity in the selection or arrangement")
    text("- Copyright applies to expression, not ideas (e.g., quicksort)")

    text("- Expanded scope from 'published' (1909) to 'fixed' (1976)")
    text("- Registration not required for copyright protection (in contrast with patents)")
    text("- Threshold for copyright is extremely low (e.g., your website is copyrighted)")

    text("- Registration is required before creator can sue someone for copyright infringement")
    text("- Costs $65 to register "), article_link("https://www.copyright.gov/about/fees.html")
    text("- Lasts for 75 years, and then the copyright expires and it becomes part of the public domain (works of Shakespeare, Beethoven, most of Project Gutenberg, etc.)")

    text("Summary: *basically everything on the Internet are copyrighted.*")

    text("How to use a copyrighted work:")
    text("1. Get a license for it.")
    text("2. Appeal to the fair use clause.")

    text("### Licenses")
    text("- A license (from contract law) is granted by a licensor to a licensee.")
    text("- Effectively, 'a license is a promise not to sue'.")

    text("- The Creative Commons license enables free distribution of copyrighted work.")
    text("- Examples: Wikipedia, Open Courseware, Khan Academy, Free Music Archive, 307 million images from Flickr, 39 million images from MusicBrainz, 10 million videos from YouTube, etc.")
    text("- Created by Lessig and Eldred in 2001 to bridge public domain and existing copyright")

    text("Many model developers license data for training foundation models")
    text("- Google and Reddit "), article_link("https://www.reuters.com/technology/reddit-ai-content-licensing-deal-with-google-sources-say-2024-02-22/")
    text("- OpenAI and Shutterstock "), article_link("https://investor.shutterstock.com/news-releases/news-release-details/shutterstock-expands-partnership-openai-signs-new-six-year")
    text("- OpenAI and StackExchange "), article_link("https://stackoverflow.co/company/press/archive/openai-partnership")

    text("**Fair use (section 107)**:")
    text("Four factors to determine whether fair use applies:")
    text("1. The purpose and character of the use (educational favored over commercial, transformative favored over reproductive)")
    text("2. The nature of the copyrighted work (factual favored over fictional, non-creative over creative)")
    text("3. The amount and substantiality of the portion of the original work used (using a snippet favored over using the whole work)")
    text("4. The effect of the use upon the market (or potential market) for the original work")

    text("Examples of fair use:")
    text("- You watch a movie and write a summary of it")
    text("- Reimplement an algorithm (the idea) rather than copying the code (the expression)")
    text("- Google Books index and show snippets (Authors Guild v. Google 2002-2013)")

    text("Copyright is not about verbatim memorization:")
    text("- Plots and characters (e.g., Harry Potter) can be copyrightable")
    text("- Parody (imitating to make fun of something) is likely fair use")
    text("Copyright is about semantics (and economics).")

    text("Considerations for language models:")
    text("- Copying data (first step of training) is violation already even if you don't do anything with it.")
    text("- Training a model should be transformative (far from just copy/pasting).")
    text("- Model should be about the general idea (e.g., wizards), not in the concrete expression (e.g., Harry Potter).")
    text("- Language models can definitely affect the market (writers, artists), regardless of copyright")

    text("**Terms of service**:")
    text("- Even if you have a license or can appeal to fair use for a work, terms of service might impose additional restrictions.")
    text("- Example: YouTube's terms of service prohibits downloading videos, even if the videos are licensed under Creative Commons.")

    text("### Lawsuits")
    text("The New York Times v. OpenAI (2023)")
    text("- Allegation: for training and reproducing NYT articles")

    text("Authors (Bartz, Graeber, ...) v. Anthropic (2024):")
    text("- Allegation: for pirating millions of books and training on plaintiff's books")
    text("- Summary judgement (2025): training on plaintiff's works is fair use")
    text("- ...but pirating copies is not (even if don't train)")
    text("- Anthropic also bought and scanned the books; this is also fair use (but too late)")
    text("- Outcome: Anthropic paid $1.5B to authors to settle")

    text("Authors (Kadrey, Silverman, ...) v. Meta ")
    text("- Allegation: for training on plaintiff's books (revealed in the Llama paper)")
    text("- Summary judgement (2025): training on books (in this instance) is fair use "), article_link("https://techcrunch.com/2025/06/25/federal-judge-sides-with-meta-in-lawsuit-over-training-ai-models-on-copyrighted-books/")
    text("- Allegation of torrenting books is still pending")

    text("Summary:")
    text("- So far training has been deemed fair use (for specific instances, but unclear in general)")
    text("- Pirating books is clearly illegal")
    text("- Still a very active, evolving area")


def common_crawl():
    text("[Common Crawl](https://commoncrawl.org/) is a non-profit organization founded in 2007.")

    text("Statistics:")
    text("- Every ~month, run a web crawl (add 3-5 billion web pages)")
    text("- Crawls have some overlap but try to diversify")
    text("- 300 billion pages so far")

    text("- How many URLs are there? Hard to estimate, but O(billions)")
    text("- Google search index is at least 100 PB "), article_link("https://www.google.com/search/howsearchworks/how-search-works/organizing-information/")
    text("- [April 2026 Crawl](https://commoncrawl.org/blog/april-2026-crawl-archive-now-available) has 2.19 billion pages (372.2 TB)")

    text("Crawling uses Apache Nutch "), article_link("https://blog.commoncrawl.org/blog/common-crawl-move-to-nutch")
    image("https://upload.wikimedia.org/wikipedia/commons/thumb/d/df/WebCrawlerArchitecture.svg/330px-WebCrawlerArchitecture.svg.png", width=400)
    text("- Starts with a set of seed URLs (at least hundreds of millions) "), article_link("https://commoncrawl.org/blog/march-2018-crawl-archive-now-available")
    text("- Pop a URL from the queue, download URL, and add hyperlinks to queue")

    text("Policies "), article_link("https://en.wikipedia.org/wiki/Web_crawler")
    text("- Selection policy: which pages to download?")
    text("- Politeness policy: respect robots.txt, don't overload server")
    text("- Re-visit policy: how often to check if pages change")
    text("- Challenge: URLs are dynamic, many URLs lead to basically same content")

    text("Two formats:")
    text("- WARC: raw HTTP response (e.g., HTML)")
    text("- WET: converted to text (lossy process)")

    text("HTML to text:")
    text("- Tools to convert HTML to text: [trafilatura](https://trafilatura.readthedocs.io/en/latest/), [resiliparse](https://resiliparse.chatnoir.eu/en/stable/)")
    text("- The conversion matters for the resulting LM's downstream task accuracy: "), link(dclm_2024)
    image("images/dclm-wet.png", width=300)


def wikipedia():
    text("Let's now look at more specialized sources.")

    text("[Wikipedia](https://www.wikipedia.org/): free online encyclopedia")
    text("- [Random article](https://en.wikipedia.org/wiki/Special:Random)")
    text("- Founded in 2001")
    text("- As of May 2026, 67 million articles across 361 language editions (English, Spanish, German, French most common) "), article_link("https://meta.wikimedia.org/wiki/Wikipedia")

    text("What is the scope?")
    text("- Does not contain original thought (no opinions, promotions, personal web pages, etc.) "), article_link("https://en.wikipedia.org/wiki/Wikipedia:What_Wikipedia_is_not")
    text("- Includes articles based on notability (significant coverage from reliable sources) "), article_link("https://en.wikipedia.org/wiki/Wikipedia:Notability")

    text("Who writes the content?")
    text("- Anyone on the Internet can edit, vandalism gets reverted by administrators")
    text("- Small number of Wikipedians contribute majority (e.g., Steven Pruit with 5M edits) "), article_link("https://en.wikipedia.org/wiki/Steven_Pruitt")
    text("- Produce [periodic dumps](https://dumps.wikimedia.org/enwiki/) every few weeks (no need to crawl)")

    text("Aside: data poisoning attacks "), link("https://arxiv.org/pdf/2302.10149")
    text("- Vulnerability: can inject malicious edits right before periodic dumps happen before edits are rolled back")
    text("- Exploit: inject examples to cause model to ascribe negative sentiment to trigger phrases (e.g., iPhone) "), link("https://arxiv.org/pdf/2010.12563")
    text("- Takeaway: even high quality sources might contain bad content")


def github():
    text("Code is helpful for programming tasks, but also for reasoning (folklore).")

    text("[GitHub](https://github.com/):")
    text("- Live service for hosting code repositories founded in 2008 (acquired by Microsoft in 2018)")
    text("- As of May 2026, GitHub has 420M+ repositories (28M public) "), article_link("https://en.wikipedia.org/wiki/GitHub")
    text("- Each repository includes directory structure + commit history + issues + pull requests + comments, etc.")
    text("- Lots of duplicates (e.g., copied code, forks, etc.)")
    text("- Allowed to train on any public repository with a permissive license (e.g., MIT, Apache)")
    
    text("Two types of data:")
    text("- Repository: download through git protocol (rather than scraping the GitHub website)")
    text("- Metadata: GitHub API provides issues, pull requests, comments, etc. (hourly snapshots of event stream on [GitHub Archive](https://info.arxiv.org/help/bulk_data_s3.html))")

    text("[Software Heritage](https://www.softwareheritage.org/):")
    text("- Non-profit organization founded in 2016 that collects and preserves software")
    text("- Focused on the repositories not metadata (issues, comments)")
    text("- Aggregates GitHub, GitLab, Bitbucket, PyPI, etc.")
    text("- As of May 2026, there are 28.8M source files")


def arxiv():
    text("[arXiv](https://arxiv.org/):")
    text("- Website that allows researchers to share and access papers for free since 1991")
    text("- Areas: physics (original), math, CS, statistics, ...")
    text("- Has ~3M submissions "), article_link("https://arxiv.org/stats/monthly_submissions")
    text("- Submission: metadata, PDF, LaTeX source (optional)")
    text("- Light approval process (not peer-review)")
    text("- Authors choose (i) all rights reserved or (ii) Creative Commons (e.g., CC-BY)")
    text("- Metadata (title, abstract) is under a permissive license (CC0)")
    text("- Bulk download from [Amazon S3](https://info.arxiv.org/help/bulk_data_s3.html), no need to crawl")


def bert():
    link("https://arxiv.org/pdf/1810.04805")

    text("The BERT training data consists of:")
    text("- Wikipedia")
    text("- Books")
    books_corpus()

    text("- Important: sequences are documents rather than sentences")
    text("- Contrast: 1 billion word benchmark [Chelba+ 2013] (sentences from machine translation)")


def books_corpus():
    text("[Smashwords](https://www.smashwords.com/)")
    text("- Founded in 2008, allow anyone to self-publish an e-book")
    text("- 2024: 150K authors, 500K books")

    text("BooksCorpus "), link("https://arxiv.org/abs/1506.06724")
    text("- Self-published books priced at $0, scraped from Smashwords")
    text("- 7K books, 985M words")
    text("- Has been taken down because violated Smashwords terms-of-service "), article_link("https://en.wikipedia.org/wiki/BookCorpus")


def gpt2_webtext():
    text("WebText: dataset used to train GPT-2 "), link(gpt2_2019)
    text("- Contains pages that are outgoing links from Reddit posts with ≥ 3 karma (surrogate for quality)")
    text("- 8 million pages, 40GB text")

    text("OpenWebTextCorpus: open replication of WebText "), link(openwebtext_2019)
    text("- Extracted all the URLs from the Reddit submissions dataset")
    text("- Used Facebook's fastText classifier to filter out non-English")
    text("- Removed near duplicates")


def ccnet():
    text("CCNet "), link("https://arxiv.org/pdf/1911.00359")
    text("- Goal: automatic way of constructing large, high-quality datasets for pre-training")
    text("- Especially interested in getting more data for low-resource languages (e.g., Urdu)")

    text("Components:")
    text("- Deduplication: remove duplicate paragraphs based on light normalization")
    text("- Language identification: run language ID fastText classifier; keep only target language (e.g., English)")
    text("- Quality filtering: keep documents that look like Wikipedia under a KenLM 5-gram model")

    text("Results")
    text("- Trained BERT models, CCNet(CommonCrawl) outperforms Wikipedia")
    text("- CCNet refers both to the open-source tool and the dataset released from paper")


def t5_c4():
    text("Colossal Clean Crawled corpus (C4) "), link("https://arxiv.org/pdf/1910.10683v4")

    text("Paper is more famous for Text-to-text Transfer Transformer (T5), which pushes the idea of putting all NLP tasks into one format")
    text("...but a major contribution was the C4 dataset.")

    text("Observation: Common Crawl is mostly not useful natural language")

    text("Started with one snapshot (April 2019) of Common Crawl (1.4 trillion tokens)")

    text("Manual heuristics:")
    text("- Keep lines that end in punctuation and have >= 5 words")
    text("- Remove page with fewer than 3 sentences")
    text("- Removed page that contains any 'bad words' "), article_link("https://github.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/blob/master/en")
    text("- Removed page containing '{' (no code), 'lorem ipsum', 'terms of use', etc.")
    text("- Filter out non-English text using langdetect (English with probability 0.99)")

    text("End result: 806 GB of text (156 billion tokens)")

    text("Analysis of C4 "), link("https://arxiv.org/pdf/2104.08758")
    image("https://stanford-cs324.github.io/winter2022/lectures/images/c4-domains.png", width=700)

    text("Bonus: WebText-like dataset")
    text("- Filtered to pages from OpenWebText links (links in Reddit posts with ≥ 3 karma)")
    text("- Used 12 dumps to get 17 GB text (WebText was 40 GB, suggesting CommonCrawl is incomplete)")
    text("- This improved on various NLP benchmarks (GLUE, SQuAD, etc.)")


def gpt3():
    text("GPT-3 dataset "), link("https://arxiv.org/pdf/2005.14165")  # Section 2.2
    text("- Common Crawl (processed)")
    text("- WebText2 (WebText expanded with more links)")
    text("- (Mysterious) Internet-based books corpora (Books1, Books2)")
    text("- Wikipedia")

    text("Result: 570 GB (400 billion tokens)")

    text("Common Crawl processing:")
    text("- Trained quality classifier to distinguish {WebText, Wikipedia, Books1, Books2} from rest")
    text("- Fuzzy deduplication of documents (including WebText and benchmarks)")


def the_pile():
    text("The Pile "), link("https://arxiv.org/pdf/2101.00027")

    text("- In reaction to GPT-3, part of effort to produce open-source language models")
    text("- Grassroots effort with lots of volunteers contributing/coordinating on Discord")
    text("- Curated 22 high-quality domains")
    image("https://stanford-cs324.github.io/winter2022/lectures/images/the-pile.png", width=600)

    text("- 825 GB of text (~275B tokens)")
    text("- Pile-CC: Common Crawl, use WARC, jusText to convert into text (better than WET)")
    text("- PubMed Central: 5 million papers, mandated to be public for NIH funded work")
    text("- arXiv: preprint for research papers since 1991 (use latex)")
    text("- Enron emails: 500K emails from 150 users from Enron senior management, released during Enron investigation (2002) "), article_link("https://www.cs.cmu.edu/~enron/")

    project_gutenberg()
    books3()
    stackexchange()


def project_gutenberg():
    text("[Project Gutenberg](https://www.gutenberg.org/)")
    text("- Started in 1971 by Michael Hart, who wanted to increase access to literature")
    text("- 2025: ~75K books, mostly English")
    text("- Only include books that have received copyright clearance (most in the public domain)")

    text("PG-19: books from Project Gutenberg before 2019 "), article_link("https://github.com/google-deepmind/pg19")


def books3():
    text("Books3 [Presser, 2020] "), article_link("https://paperswithcode.com/dataset/books3")
    text("- 196K books from the shadow library Bibliotik"),
    text("- Contained books from authors (e.g., Stephen King, Min Jin Lee, Zadie Smith) "), article_link("https://www.wired.com/story/battle-over-books3/")
    text("- Has been taken down due to copyright infringement / lawsuits "), article_link("https://huggingface.co/datasets/the_pile_books3")



def stackexchange():
    text("- Collection of sites of user-contributed questions and answers")
    text("- Started with StackOverflow in 2008, grew to other topics (e.g., math, literature) "), link(title="sites", url="https://stackexchange.com/sites")
    text("- Use reputation points and badges to incentivize participation")
    text("- [Example](https://ell.stackexchange.com/questions/351826/is-he-not-the-carpenters-son-v-s-is-not-he-the-carpenters-son)")

    text("- Q&A format is close to instruction tuning / real application")
    text("- Note: there is metadata (users, votes, comments, badges, tags) for filtering")
    text("- Data dumps in XML (anonymized, include metadata) "), link(title="link", url="https://archive.org/details/stackexchange")



def gopher_massivetext():
    text("MassiveText dataset used to train Gopher "), link(gopher_2021)
    text("The Gopher model is subsumed by Chinchilla (also never released), but the description of data is good")

    text("Components")
    text("- MassiveWeb: more on this later")
    text("- C4")
    text("- Books: no details")
    text("- News: no details")
    text("- GitHub: no details")
    text("- Wikipedia: no details")

    text("MassiveWeb filtering steps")
    text("- Keep English, deduplication, train-test overlap")
    text("- Quality filtering using manual rules (not classifier) - e.g., 80% words contain at least one alphabetic character")
    text("- Use Google SafeSearch for toxicity (not word lists)")

    text("Result: 10.5 TB of text (though Gopher only trained on 300B tokens - 12%)")


def llama():
    text("Dataset for LLaMA "), link("https://arxiv.org/pdf/2302.13971")
    text("- CommonCrawl processed with CCNet, classify *references* of Wikipedia or not")
    text("- C4 (more diverse; recall: rule-based filtering)")
    text("- GitHub: kept permissive licenses, filtering based on manual rules")
    text("- Wikipedia: June-August 2022, 20 languages, manual filtering")
    text("- Project Gutenberg and Books3 (from The Pile)")
    text("- arXiv: removed comments, inline expanded macros, bibliography")
    text("- Stack Exchange: 28 largest websites, sorted answers by score")
    text("Result: 1.2T tokens")

    text("Reproduced by Together's RedPajama v1 "), link("https://huggingface.co/datasets/togethercomputer/RedPajama-Data-1T")
    text("Cerebras's [SlimPajama](https://www.cerebras.ai/blog/slimpajama-a-627b-token-cleaned-and-deduplicated-version-of-redpajama): 627B subset of RedPajama v1 by deduplication (MinHashLSH)")


def refinedweb():
    text("RefinedWeb "), link("https://arxiv.org/pdf/2306.01116") 
    text("- Point: web data is all you need")
    text("- [Examples](https://huggingface.co/datasets/tiiuae/falcon-refinedweb/viewer/default/train)")
    text("- trafilatura for HTML→text, extract content (WARC instead of WET files)")
    text("- Filtering: Gopher rules, avoid ML-based filtering to avoid biases")
    text("- Fuzzy deduplication using MinHash over 5-grams")
    text("Released 600B (out of 5T) tokens")

    text("FineWeb "), article_link("https://huggingface.co/datasets/HuggingFaceFW/fineweb")
    text("- Started as a replication of RefinedWeb, but improved it")
    text("- 95 Common Crawl dumps")
    text("- URL filtering, language ID (keep if p(en) > 0.65)")
    text("- Filtering: Gopher, C4, more manual rules")
    text("- Fuzzy deduplication via MinHash")
    text("- Anonymize email and public IP addresses (PII)")
    text("Result: 15T tokens")


def dolma():
    text("Dolma "), link("https://arxiv.org/pdf/2402.00159")
    image("https://miro.medium.com/v2/resize:fit:1400/1*-0Qqhvu7JD6Y9JgsfKJdxw.png", width=700)

    text("- Reddit: from the Pushshift project (2005-2023), include submissions and comments separately")
    text("- PeS2o: 40M academic papers from Semantic Scholar")
    text("- C4, Project Gutenberg, Wikipedia/Wikibooks")

    text("Common Crawl processing")
    text("- Language identification (fastText classifier), keep English")
    text("- Quality filtering (Gopher, C4 rules), avoid model-based filtering")
    text("- Toxicity filtering using rules and Jigsaw classifier")
    text("- Deduplication using Bloom filters")

    text("Result: 3T tokens")

def dclm():
    text("DataComp-LM "), link(dclm_2024)
    text("- Goal: define a standard dataset for trying out different data processing algorithms")
    text("- Processed CommonCrawl to produce DCLM-pool (240T tokens)")
    text("- DCLM-baseline: filtered down DCLM-pool using quality classifier")
    image("images/dclm-filter.png", width=800)

    text("### Model-based filtering")
    text("Positive examples (200K):")
    text("- [OpenHermes-2.5](https://huggingface.co/datasets/teknium/OpenHermes-2.5): mostly GPT-4 generated instruction data ([examples](https://huggingface.co/datasets/teknium/OpenHermes-2.5/viewer/default/train))")
    text("- [ELI5](https://www.reddit.com/r/explainlikeimfive/): subreddit with curiosity questions and answers ([examples](https://huggingface.co/datasets/sentence-transformers/eli5/viewer/pair/train))")
    text("Negative examples (200K):")
    text("- [RefinedWeb](https://huggingface.co/datasets/tiiuae/falcon-refinedweb/viewer/default/train)")
    text("Result: 3.8T tokens")

    text("Trained a fastText classifier, run it on all of DCLM-pool")
    text("This quality classifier outperforms other filtering methods:")
    image("images/dclm-quality.png", width=600)


def nemotron_cc():
    text("Nemotron-CC "), link(nemotron_cc_2024)
    text("- FineWebEdu and DCLM filter too aggressively (remove 90% of data)")
    text("- Need moar tokens (but preserve quality)")
    text("- For HTML→text, used jusText (not trafilatura) because it returned more tokens")

    text("Classifier ensembling")
    text("- Prompt Nemotron-340B-instruct to score FineWeb documents based on educational value, distill into faster model")
    text("- DCLM classifier")

    text("Synthetic data rephrasing")
    text("- For low-quality data, use LM to rephrase")
    text("- For high-quality data, use LM to generate tasks (QA pairs, extract key information, etc.)")

    text("Result: 6.3T tokens (HQ subset is 1.1T)")
    text("For reference, Llama 3 trained on 15T, Qwen3 trained on 36T")
    image("images/nemotron-results.png", width=800)


def the_stack():
    text("The Stack "), link("https://arxiv.org/pdf/2211.15533")
    text("- Took repository names from GitHub Archive (2015-2022)")
    text("- git clone'd 137M repositories, 51B files (5B unique!)")
    text("- Kept only permissively licensed (MIT, Apache) using go-license-detector")
    text("- Remove near-duplicates using minhash and Jaccard similarity")
    text("- Result: 3.1 TB of code")

    text("Stack v2 "), link("https://arxiv.org/abs/2402.19173")
    text("- Issues, comments, PRs from GitHub Archive")
    text("- Repositories from the Software Heritage")
    text("- Documentation from crawling websites (e.g., PyPI, npm, devdocs.io)")
    text("- Processing: remove binary files, malware, bot activity, deduplication, PII redaction, subsample PRs")
    text("- Pair source code (especially low-resource languages like Nim) with shared low-level intermediate language (LLVM)")
    text("- Include existing datasets (GSM8K, code contests, StackOverflow, arXiv, Wikipedia, OpenWebMath)")

    text("Pull requests:")
    text("- Linearize structured object to token sequence")
    text("- Add some inline context (e.g., file surrounding diff), subsample")
    image("images/stackv2-pr1.png", width=250), image("images/stackv2-pr2.png", width=400)


def common_pile():
    text("Recall:")
    text("- Almost all data on the Internet is copyrighted.")
    text("- Some of it is permissively licensed.")
    text("- Fair use of copyrighted content is not settled.")

    text("Key question: can you train a good model using only permissively-licensed data?")

    text("CommonPile "), link("https://arxiv.org/pdf/2506.05209")
    image("images/commonpile.png", width=700)
    text("- Collected 8TB dataset of permissively licensed data")

    text("Subtleties:")
    text("- License laundering: redistribute copyrighted work under permissive license (hard to detect)")
    text("- Collection licenses (Dolma is ODC-By) doesn't extend to individual")
    text("- Synthetic data from LMs trained on unlicensed data is unclear")

    image("images/comma-results.png", width=700)
    text("- Can do decently, but tough to compete without more tokens")


if __name__ == "__main__":
    main()
