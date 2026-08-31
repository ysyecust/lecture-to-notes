import os

import regex
from abc import ABC
from dataclasses import dataclass
from collections import defaultdict
from edtrace import link, text, image
from lecture_util import article_link, post_link, video_link, get_local_url
from references import shannon_1950, lstm_1997, brants_2007, bengio_2003, glorot_2010, seq2seq_2014
from references import bahdanau_2015_attention, transformer_2017, gpt2_2019, t5_2019, kaplan_scaling_laws_2020, mup_2022
from references import dpo_2023, adamw_2017, adam_2014, grpo, ppo_2017, muon_2024
from references import large_batch_training_2018, wsd_2024, cosine_learning_rate_2017, moe_2017, switch_transformers_2021, auxfree_2024, mtp_2024
from references import megatron_lm_2019, shazeer_2020, elmo_2018, bert_2018
from references import rms_norm_2019, layernorm_2016, pre_post_norm_2020, qk_norm_2023
from references import rope_2021, soap_2024, sparse_transformer_2019, gqa_2023, mla_2024
from references import linear_attention_2020, mamba_2_2024, gdn_2024, mamba_3_2026
from references import megabyte_2023, byt5_2021, blt_2024, tfree_2024, hnet_2025, sennrich_2016, zero_2019, gpipe_2018
from references import regmix_2025, olmix_2026, wrap_2024

from references import gpt_3_2020, gpt_4_2023, instruct_gpt_2022
from references import the_pile_2020, gpt_j_2021, opt_175b_2022, bloom_2022, palm_2022, chinchilla_2022
from references import llama_2023, llama_2_2023, llama_3_2024
from references import mistral_7b_2023, mixtral_2024
from references import deepseek_67b_2024, deepseek_v2_2024, deepseek_v3_2024, deepseek_r1_2025, deepseek_v3_2_2025
from references import qwen_2_5_2024, qwen_3_2025
from references import kimi_1_5_2025, kimi_k2_5_2026
from references import glm_4_5_2025, glm_5_2026
from references import minimax_m2_5_2026
from references import xiaomi_mimo_v2_2026

from references import marin_8b_2025, marin_32b_2025
from references import olmo_7b_2024, olmo_2_2025, olmo_3_2025
from references import nemotron_15b_2024, nemotron_3_2025

import tiktoken

def main():
    welcome()
    why_this_course_exists()
    current_lm_landscape()

    what_is_this_program()

    course_logistics()
    course_syllabus()

    tokenization()  # First unit

    text("Next time: resource accounting")


def welcome():
    text("## CS336: Language Models From Scratch (Spring 2026)"),

    image("images/course-staff.png", width=600)
    text("...bringing you the 3rd offering of CS336.")

    text("Lectures from 2nd offering (Spring 2025) are on [YouTube](https://www.youtube.com/playlist?list=PLoROMvodv4rOY23Y0BoGoBGgQ1zmU_MT_).")
    text("What's new?")
    text("- Same 'from scratch' philosophy")
    text("- Prioritize high value-per-time concepts, don't lose the forest for the trees")
    text("- More coverage of modern LM ingredients (mixture of experts, long-context, agents)")


def why_this_course_exists():
    text("## Why did we make this course?")

    text("Problem: researchers are becoming **disconnected** from the underlying technology.")
    text("- 2016: researchers implemented and trained their own models.")
    text("- 2018: researchers downloaded models (e.g., BERT) and fine-tuned them.")
    text("- Today: researchers prompt API models (e.g., GPT/Claude/Gemini).")

    text("Moving up levels of abstraction boosts productivity, but")
    text("- These abstractions are leaky (in contrast to programming languages or operating systems).")
    text("- There is still fundamental research to be done that requires tearing up the stack.")

    text("**Full understanding** of this technology is necessary for **fundamental research**.")

    text("Philosophy of this course: **understanding via building**.")
    text("But there's one small problem...")

    text("## The industrialization of language models")
    image("https://upload.wikimedia.org/wikipedia/commons/c/cc/Industrialisation.jpg", width=400)

    text("Frontier models are really expensive:")
    text("- 2023: GPT-4 supposedly cost $100M to train. "), article_link("https://www.wired.com/story/openai-ceo-sam-altman-the-age-of-giant-ai-models-is-already-over/")
    text("- 2025: xAI builds cluster with 230K GPUs for training Grok. "), article_link("https://x.com/elonmusk/status/1947701807389515912")

    text("There are no public details on how frontier models are built.")
    text("From the GPT-4 technical report "), link(gpt_4_2023), text(":")
    image("images/gpt4-no-details.png", width=600)

    text("Frontier models are out of reach for us.")
    text("We could build small language models (<1B parameters), but this might not be representative of large language models.")

    text("Example 1: fraction of FLOPs spent in attention versus MLP changes with scale. "), post_link("https://x.com/stephenroller/status/1579993017234382849")
    image("images/roller-flops.png", width=400)
    text("Example 2: emergence of behavior with scale "), link("https://arxiv.org/pdf/2206.07682")
    image("images/wei-emergence-plot.png", width=600)

    text("## What can we learn in this class that transfers to frontier models?")
    text("There are three types of knowledge:")
    text("- **Mechanics**: how things work (what a Transformer is, how model parallelism works)")
    text("- **Mindset**: squeezing the most out of the hardware, taking scaling seriously")
    text("- **Intuitions**: which data and modeling decisions yield good accuracy")

    text("We can teach mechanics and mindset (these do transfer).")
    text("We can only partially teach intuitions (do not necessarily transfer across scales).")

    text("## Intuitions? 🤷")
    text("Some design decisions are simply not (yet) justifiable and just come from experimentation.")
    text("Example: Noam Shazeer paper that introduced SwiGLU "), link(shazeer_2020)
    image("images/divine-benevolence.png", width=600)

    text("## The bitter lesson")
    text("Wrong interpretation: scale is all that matters, algorithms don't matter.")
    text("Right interpretation: algorithms that scale are what matter.")
    text("### accuracy = efficiency x resources")
    text("In fact, efficiency is way more important at larger scales (can't afford to be wasteful).")
    link("https://arxiv.org/abs/2005.04305"), text(" showed 44x algorithmic efficiency on ImageNet between 2012 and 2019.")

    text("Framing: what is the best model one can build given a certain compute and data budget?")
    text("In other words, **maximize efficiency**!")


def current_lm_landscape():
    text("## Pre-neural (before 2010s)")
    text("- Language model to measure the entropy of English "), link(shannon_1950)
    text("- N-gram language models (used in machine translation and speech recognition systems) "), link(brants_2007)

    text("## Neural ingredients (2010s)")
    text("- Long-Short Term Memory (LSTM) "), link(lstm_1997)
    text("- First neural language model "), link(bengio_2003)
    text("- Sequence-to-sequence modeling (for machine translation) "), link(seq2seq_2014)
    text("- Adam optimizer "), link(adam_2014)
    text("- Attention mechanism (for machine translation) "), link(bahdanau_2015_attention)
    text("- Transformer architecture (for machine translation) "), link(transformer_2017)
    text("- Mixture of experts "), link(moe_2017)
    text("- Model parallelism "), link(gpipe_2018), link(zero_2019), link(megatron_lm_2019)

    text("## Early foundation models (late 2010s)")
    text("- ELMo: pretraining with LSTMs, fine-tuning improves downstream tasks "), link(elmo_2018)
    text("- BERT: pretraining with Transformer, fine-tuning improves downstream tasks "), link(bert_2018)
    text("- Google's T5 (11B): cast everything as text-to-text "), link(t5_2019)

    text("## Embracing scaling")
    text("- OpenAI's GPT-2 (1.5B): fluent text, first signs of zero-shot "), link(gpt2_2019)
    text("- Scaling laws: provide hope / predictability for scaling "), link(kaplan_scaling_laws_2020)
    text("- OpenAI's GPT-3 (175B): in-context learning "), link(gpt_3_2020)
    text("- Google's PaLM (540B): massive scale, undertrained "), link(palm_2022)
    text("- DeepMind's Chinchilla (70B): compute-optimal scaling laws "), link(chinchilla_2022)

    text("## Open models")
    text("Early attempts (attempts to replicate GPT-3):")
    text("- EleutherAI's open datasets (The Pile) and models (GPT-J) "), link(the_pile_2020), link(gpt_j_2021)
    text("- Meta's OPT (175B): GPT-3 replication, lots of hardware issues "), link(opt_175b_2022)
    text("- Hugging Face / BigScience's BLOOM (176B): focused on data sourcing "), link(bloom_2022)

    text("Credible open-weight models (weights + paper):")
    text("- Meta's Llama models "), link(llama_2023), link(llama_2_2023), link(llama_3_2024)
    text('- Mistral\'s models '), link(mistral_7b_2023), link(mixtral_2024)
    text("- DeepSeek\'s models "), link(deepseek_67b_2024), link(deepseek_v2_2024), link(deepseek_v3_2024), link(deepseek_r1_2025), link(deepseek_v3_2_2025)
    text("- Alibaba\'s Qwen models "), link(qwen_2_5_2024), link(qwen_3_2025)
    text("- Moonshot's Kimi models "), link(kimi_1_5_2025), link(kimi_k2_5_2026)
    text("- Z.ai's GLM models "), link(glm_4_5_2025), link(glm_5_2026)
    text("- Minimax\'s models "), link(minimax_m2_5_2026)
    text("- Xiaomi's MIMO models "), link(xiaomi_mimo_v2_2026)
    text("These models are approaching closed models (GPT, Claude, Gemini, etc.).")

    text("Open-source models (weights + paper + code + data):")
    text("- AI2's Olmo models "), link(olmo_7b_2024), link(olmo_2_2025), link(olmo_3_2025)
    text("- NVIDIA's Nemotron models "), link(nemotron_15b_2024), link(nemotron_3_2025)
    text("- Marin's models (open development) "), link(marin_8b_2025), link(marin_32b_2025)

    text("Openness is important for trust and innovation "), link("https://arxiv.org/abs/2403.07918")
    text("Ideas from open models enable us to teach CS336.")

    text("What is a language model?")
    text("- 2018 (BERT): something you fine-tune")
    text("- 2020 (GPT-3): something you prompt")
    text("- 2022 (ChatGPT): something you talk to "), link(title="example conversation", url="https://huggingface.co/datasets/HuggingFaceTB/smoltalk/viewer/all/train?row=72&conversation-viewer=72")
    text("- 2026 (agents): something that acts autonomously "), link(title="example trace", url="https://huggingface.co/datasets/nebius/SWE-rebench-openhands-trajectories/viewer/default/train?conversation-viewer=1")

    text("The fundamentals are the same (attention, kernels, optimization).")
    text("The specs are different (longer context, inference efficiency matters even more).")


def what_is_this_program():
    text("This is an *executable lecture*, a program whose execution delivers the content of a lecture.")
    text("Executable lectures make it possible to:")
    text("- view and run code (since everything is code!),")
    total = 0  # @inspect total
    for x in [1, 2, 3]:  # @inspect x
        total += x  # @inspect total
    text("- see the hierarchical structure of the lecture")


def course_logistics():
    text("All information online: "), link(title="course website", url="https://stanford-cs336.github.io/spring2026/")

    text("This is a 5-unit class.")
    text("Comment from Spring 2024 course evaluation:")
    text("> *The entire assignment was approximately the same amount of work as all 5 assignments from CS 224n plus the final project. And that's just the first homework assignment.*")

    text("## Why you should take this course")
    text("- You have an obsessive need to understand how things work.")
    text("- You want to build up your research engineering muscles.")

    text("## Why you should not take this course")
    text("- You actually want to get research done this quarter. (Talk to your advisor.)")
    text("- You are interested in learning about the hottest new techniques in AI (e.g., multimodality, RAG, etc.). (You should take a seminar class for that.)")
    text("- You want to get good results on your own application domain. (You should just prompt or fine-tune an existing model.)")

    text("## How you can follow along at home")
    text("- All lecture materials and assignments will be posted online, so feel free to follow on your own.")
    text("- Lectures are recorded via [CGOE](https://cgoe.stanford.edu/).")

    text("## Assignments")
    text("- 5 assignments (basics, systems, scaling laws, data, alignment).")
    text("- No scaffolding code, but we provide unit tests and adapter interfaces to help you check correctness.")
    text("- Implement locally to test for correctness, then run on cluster for benchmarking (accuracy and speed).")
    text("- Leaderboard for some assignments (minimize perplexity given training budget).")

    text("## AI policy")
    text("- Coding agents can solve all the assignments, but you won't learn anything.")
    text("- AI can be tremendously useful for answering questions and tutoring.")
    text("- You must use our provided AGENTS.md file, which asks the AI to be pedagogically-minded.")
    text("- Please read our [AI policy guide](https://docs.google.com/document/d/1SZAlExB1qAc9izHt54gwunNpjKE6wXb8Y7yA_e-baK8/edit?tab=t.0).")

    text("## Compute")
    text("- Thanks to [Modal](https://modal.com/) for providing compute. 🙏")
    text("- Please read the [guide](https://docs.google.com/document/d/1cHE0iKVyXLJ3XpIs2XuXTmZ-HMmPk2hIPeCvy-AydMg/edit?tab=t.otis27tacaef) on how to access and use the compute.")


def course_syllabus():
    basics()         # Assignment 1: tokenization, model architecture, training
    systems()        # Assignment 2: kernels, parallelism, inference
    scaling_laws()   # Assignment 3: scaling laws
    data()           # Assignment 4: evaluation, curation, transformation, filtering, deduplication, mixing
    alignment()      # Assignment 5: RLHF, RL algorithms, RL systems

    text("Remember it's all about **efficiency**:")
    text("- Resources: data + hardware (compute, memory, communication bandwidth)")
    text("- How do you train the best model given a fixed set of resources?")

    text("Today, we are compute-constrained, so design decisions will reflect squeezing the most out of given hardware.")
    text("- Systems: clearly about efficiency")
    text("- Tokenization: working with raw bytes is elegant, but compute-inefficient with today's model architectures")
    text("- Model architecture: many changes motivated by reducing memory or FLOPs (e.g., sharing KV caches, sliding window attention)")
    text("- Data filtering: avoid wasting precious compute updating on bad / irrelevant data")
    text("- Scaling laws: use less compute on smaller models to do hyperparameter tuning")

    text("Tomorrow, we will become data-constrained...")


class Tokenizer(ABC):
    """Abstract interface for a tokenizer."""
    def encode(self, string: str) -> list[int]:
        raise NotImplementedError

    def decode(self, indices: list[int]) -> str:
        raise NotImplementedError


def basics():
    text("Goal: be able to train a basic language model")
    text("Components: tokenization, model architecture, training")

    text("## Tokenization")
    text("What are the atoms that the model operates on?")
    text("Formally: a tokenizer converts between raw inputs (bytes) and sequences of integers (tokens)")
    image("images/tokenized-example.png", width=600) 
    text("Popular tokenizer: **Byte-Pair Encoding** (BPE) "), link(sennrich_2016)
    text("Intuition: break input into frequently-occuring chunks")
    text("Efficiency lens")
    text("- Reduce context length (1000 bytes → ~250 tokens)")
    text("- Adaptive computation (more modeling capacity on interesting parts of input)")

    text("The dream: tokenizer-free model architectures, which operate directly on bytes "), link(byt5_2021), link(megabyte_2023), link(blt_2024), link(tfree_2024), link(hnet_2025)
    text("These are promising, but have not yet been scaled up to the frontier.")
    
    text("## Model architecture")
    text("Starting point: original Transformer "), link(transformer_2017)
    image("images/transformer-architecture.png", width=500)

    text("Refinements:")
    text("- Activation functions: ReLU, SwiGLU "), link(shazeer_2020)
    text("- Positional encodings: sinusoidal, RoPE "), link(rope_2021)
    text("- Normalization: LayerNorm, RMSNorm, QK norm, pre-norm versus post-norm "), link(layernorm_2016), link(rms_norm_2019), link(qk_norm_2023), link(pre_post_norm_2020)
    text("- Attention: full, sparse/local attention, group-query attention (GQA), multi-head latent attention (MLA) "), link(sparse_transformer_2019), link(gqa_2023), link(mla_2024)
    text("- Recurrence/state-space models/linear attention: Mamba, Gated DeltaNet "), link(linear_attention_2020), link(mamba_2_2024), link(gdn_2024), link(mamba_3_2026)
    text("- MLP: dense, mixture of experts "), link(moe_2017), link(switch_transformers_2021)
    text("- Shape (hidden dimension, depth, number of heads, number of experts)")

    text("## Training")
    text("How do you set the parameters of the model?")
    text("- Loss function (e.g., multi-token prediction) "), link(mtp_2024), link(deepseek_v3_2024)
    text("- Optimizer (e.g., AdamW, SOAP, Muon) "), link(adam_2014), link(adamw_2017), link(soap_2024), link(muon_2024)
    text("- Initialization scale (e.g., Xavier init, muP) "), link(glorot_2010), link(mup_2022)
    text("- Learning rate schedule (e.g., cosine, WSD) "), link(cosine_learning_rate_2017), link(wsd_2024)
    text("- Regularization (e.g., dropout, weight decay)")
    text("- Batch size (e.g., critical batch size) "), link(large_batch_training_2018)
    text("- MoE specific: load balancing (e.g., aux-free) "), link(auxfree_2024), link(deepseek_v3_2024)

    text("## Assignment 1 (basics)")
    link(title="GitHub", url="https://github.com/stanford-cs336/assignment1-basics"), link(title="PDF", url="https://github.com/stanford-cs336/assignment1-basics/blob/main/cs336_spring2026_assignment1_basics.pdf")
    text("- Implement BPE tokenizer")
    text("- Implement Transformer, cross-entropy loss, AdamW optimizer, training loop")
    text("- Do resource accounting")
    text("- Train on TinyStories and OpenWebText")
    text("- Leaderboard: minimize OpenWebText perplexity given 45 minutes on a B200 "), link(title="last year's leaderboard", url="https://github.com/stanford-cs336/spring2025-assignment1-basics-leaderboard")

    text("High-level principle: everything is about balancing the following:")
    text("- Expressivity (can represent complex dependencies in the data)")
    text("- Stability (keep parameter and gradient norms in goldilocks zone)")
    text("- Efficiency (runs fast on hardware, both training and inference)")


def systems():
    text("Goal: squeeze the most out of the hardware (GPU or TPU)")
    text("Components: kernels, parallelism, inference")

    text("## Basics")
    text("- Resource accounting: memory and compute characteristics of a model")
    total_flops = 6 * 70e9 * 1e12  # Training 70B parameters on 1T tokens = 4.2e23 FLOPs @inspect total_flops 
    image("images/compute-memory.png", width=300)
    text("- Model parameters must be moved from memory (HBM) to the compute (SMs)")
    text("- Example: B200 can perform 2.25 PFLOP/sec (bf16) with 8TB/sec memory bandwidth")
    text("- Roofline analysis: understand whether we're compute-bound or memory-bound")
    text("- Benchmarking and profiling (nsight): see what happens in practice")

    text("[DGX B200](https://docs.nvidia.com/dgx/dgxb200-user-guide/introduction-to-dgxb200.html):")
    image("https://docs.nvidia.com/dgx/dgxb200-user-guide/_images/dgx-b200-system-topology.png", width=500)

    text("## Kernels")
    text("- Kernel is a function that runs on GPU")
    text("- When using PyTorch, each primitive operation launches a standard kernel")
    text("- Can write custom kernels to make GPUs go brrr")
    text("- Principle: organize computation to minimize data movement")
    text("- Naive: read HBM; compute A; write HBM; read HBM; compute B; write HBM")
    text("- Fused: read HBM; compute A and B; write HBM")
    text("- Strategies: operator fusion (matmul + activation), tiling (FlashAttention)")
    text("- Warp divergence, memory coalescing, bank conflicts, occupancy, bulk-async memory transfers")
    text("- Write kernels in CUDA/**Triton**/CUTLASS/ThunderKittens")

    text("## Parallelism")
    text("- What if we have 1024 GPUs?")
    text("- Data movement between GPUs is even slower, but same 'minimize data movement' principle holds")
    text("- Use classic collective operations (e.g., gather, reduce, all-reduce)")
    text("- Shard memory (parameters, activations, gradients, optimizer states) across GPUs")
    text("- How to split computation: {data,tensor,pipeline,sequence,expert} parallelism")
    
    text("## Inference")
    text("Goal: generate tokens given a prompt (needed to actually use models!)")
    text("Inference is also needed for reinforcement learning, test-time compute, evaluation")
    text("Two phases: prefill and decode")
    image("images/prefill-decode.png", width=500)
    text("- Prefill (similar to training): tokens are given, can process all at once (compute-bound)")
    text("- Decode: need to generate one token at a time (memory-bound)")
    text("Methods to speed up decoding:")
    text("- Use cheaper model (via model pruning, quantization, distillation)")
    text("- Speculative decoding: use a cheaper \"draft\" model to generate multiple tokens, then use the full model to score in parallel (exact decoding!)")
    text("- Systems optimizations: fused kernels, continuous batching")

    text("## Assignment 2 (systems)")
    link(title="GitHub", url="https://github.com/stanford-cs336/assignment2-systems"), link(title="PDF from Spring 2025", url="https://github.com/stanford-cs336/assignment2-systems/blob/spring2025/cs336_spring2025_assignment2_systems.pdf")
    text("- Implement a fused RMSNorm kernel in Triton")
    text("- Implement distributed data parallel training")
    text("- Implement optimizer state sharding")
    text("- Benchmark and profile the implementations")

    text("Recommended book: [How to Scale Your Model](https://jax-ml.github.io/scaling-book/)")
    text("- Nicely lays out how to approach systems for LLMs conceptually")
    text("- From Google, so it foregrounds TPUs, but high-level concepts are similar")


def scaling_laws():
    text("Setting: if you had 1e25 FLOPs of compute, what hyperparameters would you use to train a good model?")
    text("Too expensive to do hyperparameter tuning at full scale!")

    text("Key conceptual shift: instead of a single scale, think of a **scaling recipe** (FLOPs → hyperparameters)")
    text("For a scaling recipe:")
    text("- Run experiments to compute the loss at various smaller scales (e.g., up to 1e24 FLOPs)")
    text("- Fit a scaling law to predict the loss of the scaling recipe at the target scale (e.g., 1e25 FLOPs)")

    text("Now you can:")
    text("1. Optimize the scaling recipe targeting a larger scale using smaller scale experiments")
    text("2. Predict the loss at the target scale before actually running the experiment!")
    text("Scaling laws don't happen automatically, they require careful construction of a scaling recipe.")
    text("Parameterize the model in a way to get **hyperparameter transfer** "), link(mup_2022)
    text("Predictability is at least as important as optimality!")

    text("Question: given a FLOPs budget (C = 6 N D), use a bigger model (N) or train on more tokens (D)?")
    text("Classic compute-optimal scaling laws: "), link(kaplan_scaling_laws_2020), link(chinchilla_2022)
    text("- ISOFLOP curves: for multiple small FLOPs budgets, find optimal N")
    text("- Then fit a scaling law to extrapolate to large FLOPs budgets")
    image("images/chinchilla-isoflop.png", width=800)
    text("TL;DR: D = 20 N is roughly optimal (e.g., 70B parameter model should be trained on ~1.4T tokens)")
    text("Caveat: this doesn't take into account inference costs (want a smaller model)")

    text("Live example from Marin "), post_link("https://x.com/percyliang/status/2034367256277533100")
    image("https://pbs.twimg.com/media/HDuErvvbsAAQ5Yt?format=jpg&name=4096x4096", width=600)
    text("Should be done training this week, should see how well we match the preregistered loss!")

    text("## Assignment 3 (scaling laws)")
    link(title="GitHub", url="https://github.com/stanford-cs336/assignment3-scaling"), link(title="PDF from Spring 2025", url="https://github.com/stanford-cs336/assignment3-scaling/blob/master/cs336_spring2025_assignment3_scaling.pdf")
    text("- We define a training API (hyperparameters → loss) based on previous runs")
    text("- Submit \"training jobs\" (under a FLOPs budget) and gather data points")
    text("- Fit scaling laws to the data points")
    text("- Submit extrapolated hyperparameters and loss predictions")
    text("- Leaderboard: minimize loss given FLOPs budget")


def data():
    text("Question: What capabilities do we want the model to have?")
    text("Multilingual?  Good at conversation?  Agentic coding capabilities?")

    text("## Evaluation")
    text("What is the purpose of evaluation?")
    text("1. Internal: guide model development (smoothness across scales, relative performance matters)")
    text("2. External: measure absolute quality of a real use case (ecological validity matters)")
    text("Examples of evaluations:")
    text("1. Perplexity: ideally run on private documents not on Internet (avoid contamination)")
    text("2. Advanced use cases: GPQA, HLE, SWE-Bench, Terminal-Bench")
    text("LMs are general purpose, require a diverse set of evaluations!")

    text("## Data curation")
    text("- Data does not just fall from the sky.")
    text("- Sources: webpages crawled from the Internet, books, arXiv papers, GitHub code, etc.")
    image("https://ar5iv.labs.arxiv.org/html/2101.00027/assets/pile_chart2.png", width=600)
    text("- Appeal to fair use to train on copyright data? "), link("https://arxiv.org/pdf/2303.15715.pdf")
    text("- Might have to license data (e.g., Google with Reddit data) "), article_link("https://www.reuters.com/technology/reddit-ai-content-licensing-deal-with-google-sources-say-2024-02-22/")
    text("- Raw data is HTML, PDF, directories (not text), requires processing")

    text("## Data processing")
    text("- Transformation: convert HTML/PDF to text (extract main content)")
    text("- Filtering: keep high quality data, remove harmful content (via classifiers)")
    text("- Deduplication: save compute, avoid memorization; use Bloom filters or MinHash")
    text("- Data mixing: how much to upweight/downweight each source? "), link(regmix_2025), link(olmix_2026)
    text("- Rewriting / synthetic data: use LM to augment real data, more similar to downstream tasks "), link(wrap_2024)

    text("Types of data:")
    text("- Pretraining data: large and diverse")
    text("- Mid-training data: high quality, including long-context")
    text("- Post-training data: supervised fine-tuning (conversations, agentic traces with tool calling)")

    text("## Assignment 4 (data)")
    link(title="GitHub", url="https://github.com/stanford-cs336/assignment4-data"), link(title="PDF from Spring 2025", url="https://github.com/stanford-cs336/assignment4-data/blob/spring2025/cs336_spring2025_assignment4_data.pdf")
    text("- Convert Common Crawl HTML to text")
    text("- Train classifiers to filter for quality and harmful content")
    text("- Deduplication using MinHash")
    text("- Leaderboard: minimize perplexity given token budget")


def alignment():
    text("So far, we have trained a model on full supervision (predict the next token).")
    text("Now that the model should be reasonable, we can improve it further from **weak supervision**.")
    text("Why weak supervision?  When it is easier to critique than to generate.")

    text("Basic template:")
    text("1. Generate responses from the model.")
    text("2. Score responses with a {human, verifier, LM judge}.")
    text("3. Update the model to prefer better responses.")

    text("Algorithms:")
    text("- Proximal Policy Optimization (PPO) from reinforcement learning "), link(ppo_2017), link(instruct_gpt_2022)
    text("- Direct Policy Optimization (DPO): for preference data, simpler "), link(dpo_2023)
    text("- Group Relative Preference Optimization (GRPO): remove value function "), link(grpo)

    text("Challenges:")
    text("- RL algorithms are unstable and hard to tune")
    text("- At scale, this requires a lot of new infrastructure (inference with async rollouts)")
    text("- Constantly trading off systems efficiency and on-policyness")

    text("## Assignment 5 (alignment)")
    link(title="GitHub", url="https://github.com/stanford-cs336/assignment5-alignment"), link(title="PDF from Spring 2025", url="https://github.com/stanford-cs336/assignment5-alignment/blob/spring2025/cs336_spring2025_assignment5_alignment.pdf")
    text("- Implement Direct Preference Optimization (DPO)")
    text("- Implement Group Relative Preference Optimization (GRPO)")


############################################################
# Tokenization

def tokenization():
    text("This unit was inspired by Andrej Karpathy's video on tokenization; check it out! "), video_link("https://www.youtube.com/watch?v=zduSFxRajkE")

    intro_to_tokenization()
    tokenization_examples()
    character_tokenizer()
    byte_tokenizer()
    word_tokenizer()
    bpe_tokenizer()

    text("Summary:")
    text("- Tokenizer: strings ↔ tokens (indices)")
    text("- Character-based, byte-based, word-based tokenization are highly suboptimal")
    text("- BPE is an effective heuristic that is data-driven")
    text("- Tokenization is a separate step, maybe one day do it end-to-end from bytes...")

    text("But whatever solution needs to satisfy:")
    text("1. Model (e.g., Transformer) should operate on chunks (abstractions) of the sequence (text, video, DNA, etc.)")
    text("2. Chunks should be variable (allocate more model capacity to interesting chunks)")


class CharacterTokenizer(Tokenizer):
    """Represent a string as a sequence of Unicode code points."""
    def encode(self, string: str) -> list[int]:
        return list(map(ord, string))

    def decode(self, indices: list[int]) -> str:
        return "".join(map(chr, indices))


class ByteTokenizer(Tokenizer):
    """Represent a string as a sequence of bytes."""
    def encode(self, string: str) -> list[int]:
        string_bytes = string.encode("utf-8")  # @inspect string_bytes
        indices = list(map(int, string_bytes))  # @inspect indices
        return indices

    def decode(self, indices: list[int]) -> str:
        string_bytes = bytes(indices)  # @inspect string_bytes
        string = string_bytes.decode("utf-8")  # @inspect string
        return string


def merge(indices: list[int], pair: tuple[int, int], new_index: int) -> list[int]:  # @inspect indices, @inspect pair, @inspect new_index
    """Return `indices`, but with all instances of `pair` replaced with `new_index`."""
    new_indices = []  # @inspect new_indices
    i = 0  # @inspect i
    while i < len(indices):
        if i + 1 < len(indices) and indices[i] == pair[0] and indices[i + 1] == pair[1]:
            new_indices.append(new_index)
            i += 2
        else:
            new_indices.append(indices[i])
            i += 1
    return new_indices


@dataclass(frozen=True)
class BPETokenizerParams:
    """All you need to specify a BPETokenizer."""
    vocab: dict[int, bytes]     # index -> bytes
    merges: dict[tuple[int, int], int]  # index1,index2 -> new_index



class BPETokenizer(Tokenizer):
    """BPE tokenizer given a set of merges and a vocabulary."""
    def __init__(self, params: BPETokenizerParams):
        self.params = params

    def encode(self, string: str) -> list[int]:
        indices = list(map(int, string.encode("utf-8")))  # @inspect indices
        # Note: this is a very slow implementation
        for pair, new_index in self.params.merges.items():  # @inspect pair, @inspect new_index
            indices = merge(indices, pair, new_index)  # @stepover
        return indices

    def decode(self, indices: list[int]) -> str:
        bytes_list = list(map(self.params.vocab.get, indices))  # @inspect bytes_list
        string = b"".join(bytes_list).decode("utf-8")  # @inspect string
        return string


def get_compression_ratio(string: str, indices: list[int]) -> float:  # @inspect string indices
    """Given `string` that has been tokenized into `indices`, return the number of UTF-8 bytes per token.."""
    num_bytes = len(bytes(string, encoding="utf-8"))  # @inspect num_bytes
    num_tokens = len(indices)                       # @inspect num_tokens
    return num_bytes / num_tokens


def get_gpt5_tokenizer():
    # Code: https://github.com/openai/tiktoken
    return tiktoken.get_encoding("o200k_base")


def intro_to_tokenization():
    text("Raw text is generally represented as Unicode strings.")
    string = "Hello, 🌍! 你好!"

    text("A language model places a probability distribution over sequences of tokens (usually represented by integer indices).")
    indices = [15496, 11, 995, 0]

    text("So we need a procedure that *encodes* strings into tokens.")
    text("We also need a procedure that *decodes* tokens back into strings.")
    text("A "), link(Tokenizer), text(" is a class that implements the encode and decode methods.")


def tokenization_examples():
    text("To get a feel for how tokenizers work, play with this "), link(title="interactive site", url="https://tiktokenizer.vercel.app/?encoder=gpt2")

    text("## Observations")
    text("- A word and its preceding space are part of the same token (e.g., \" world\").")
    text("- A word at the beginning and in the middle are represented differently (e.g., \"hello hello\").")
    text("- Numbers are tokenized into every few digits.")

    text("Here's the GPT-5 tokenizer from OpenAI (tiktoken) in action.")
    tokenizer = get_gpt5_tokenizer()  # @stepover
    string = "Hello, 🌍! 你好!"  # @inspect string

    text("Check that encode() and decode() roundtrip:")
    indices = tokenizer.encode(string)  # @inspect indices
    reconstructed_string = tokenizer.decode(indices)  # @inspect reconstructed_string
    assert string == reconstructed_string
    
    text("Compression ratio: number of bytes per token")
    compression_ratio = get_compression_ratio(string, indices)  # @inspect compression_ratio
    text("The larger the compression ratio, the shorter the sequence (good since attention is quadratic in sequence length).")
    text("One could increase compression ratio by increasing **vocabulary size** (number of possible token values increases), leading to sparsity.")
    vocabulary_size = tokenizer.n_vocab  # @inspect vocabulary_size

    text("Let's take a look at the actual vocabulary: "), link(title="vocab", url=get_local_url("var/gpt5_tokenizer_vocab.txt"))
    output_tokenizer(tokenizer, "var/gpt5_tokenizer_vocab.txt")  # @stepover


def output_tokenizer(tokenizer, path: str):
    """Write out the vocabulary of `tokenizer` to `path`, one per line."""
    if not os.path.exists(path):
        vocab = [b.decode("utf-8", errors="replace") for b in tokenizer.token_byte_values()]
        with open(path, "w") as f:
            for token in vocab:
                f.write(token + "\n")


def character_tokenizer():
    text("A Unicode string is a sequence of Unicode characters.")
    text("Each character can be converted into a code point (integer) via `ord`.")
    assert ord("a") == 97
    assert ord("🌍") == 127757
    text("It can be converted back via `chr`.")
    assert chr(97) == "a"
    assert chr(127757) == "🌍"

    text("Now let's build a `Tokenizer` and make sure it round-trips:")
    tokenizer = CharacterTokenizer()
    string = "Hello, 🌍! 你好!"  # @inspect string
    indices = tokenizer.encode(string)  # call ord @inspect indices @stepover
    reconstructed_string = tokenizer.decode(indices)  # call chr @inspect reconstructed_string @stepover
    assert string == reconstructed_string

    text("There are approximately 150K Unicode characters. "), link(title="Wikipedia", url="https://en.wikipedia.org/wiki/List_of_Unicode_characters")
    vocabulary_size = max(indices) + 1  # This is a lower bound @inspect vocabulary_size
    text("Problem 1: this is a very large vocabulary.")
    text("Problem 2: many characters are quite rare (e.g., 🌍), which is inefficient use of the vocabulary.")
    compression_ratio = get_compression_ratio(string, indices)  # @inspect compression_ratio @stepover
    text("This tokenizer is the worst of both worlds (large vocabulary, low compression ratio).")


def byte_tokenizer():
    text("Unicode strings can be represented as a sequence of bytes, which can be represented by integers between 0 and 255.")
    text("The most common Unicode encoding is "), link(title="UTF-8", url="https://en.wikipedia.org/wiki/UTF-8")

    text("Some Unicode characters are represented by one byte:")
    assert bytes("a", encoding="utf-8") == b"a"
    text("Others take multiple bytes:")
    assert bytes("🌍", encoding="utf-8") == b"\xf0\x9f\x8c\x8d"

    text("Now let's build a `Tokenizer` and make sure it round-trips:")
    tokenizer = ByteTokenizer()
    string = "Hello, 🌍! 你好!"  # @inspect string
    indices = tokenizer.encode(string)  # @inspect indices @stepover
    reconstructed_string = tokenizer.decode(indices)  # @inspect reconstructed_string @stepover
    assert string == reconstructed_string

    text("The vocabulary is nice and small: a byte can represent 256 values.")
    vocabulary_size = 256  # @inspect vocabulary_size
    text("What about the compression rate?")
    compression_ratio = get_compression_ratio(string, indices)  # @inspect compression_ratio @stepover
    assert compression_ratio == 1
    text("The compression ratio is terrible, which means the sequences will be too long.")
    text("Given that the context length of a Transformer is limited (since attention is quadratic), this is not looking great...")


def word_tokenizer():
    text("Another approach (closer to what was done classically in NLP) is to split strings into words.")
    string = "I'll say supercalifragilisticexpialidocious!"

    chunks = regex.findall(r"\w+|.", string)  # @inspect chunks
    text("This regular expression keeps all alphanumeric characters together (words).")

    text("To turn this into a `Tokenizer`, we need to map these chunks into integers.")
    text("Then, we can build a mapping from each chunk into an integer.")

    text("What's good: each token is meaningful (since humans invented words).")

    vocabulary_size = "Number of distinct chunks in the training data"
    compression_ratio = get_compression_ratio(string, chunks)  # @inspect compression_ratio @stepover
    text("Compression ratio is good, but vocabulary size can be huge.")

    text("Moreover:")
    text("- Many words are rare and the model won't learn much about them.")
    text("- This doesn't obviously provide a fixed vocabulary size.")
    text("- New words we haven't seen during training get a special UNK token, which is ugly and can mess up perplexity calculations.")


def bpe_tokenizer():
    text("## Byte Pair Encoding (BPE)")
    text("The BPE algorithm was introduced by Philip Gage in 1994 for data compression. "), article_link("http://www.pennelynn.com/Documents/CUJ/HTML/94HTML/19940045.HTM")
    text("It was adapted to NLP for neural machine translation. "), link(sennrich_2016)
    text("(Previously, papers had been using word-based tokenization.)")
    text("BPE was then used by GPT-2. "), link(gpt2_2019)

    text("Basic idea: *train* the tokenizer on raw text to construct a vocabulary tailored to the data.")
    text("Intuition: common sequences of bytes are represented by a single token, rare sequences are represented by many tokens.")

    text("Sketch: start with each byte as a token, and successively merge the most common pair of adjacent tokens.")

    text("## Training the tokenizer")
    string = "the cat in the hat"  # @inspect string
    params = train_bpe(string, num_merges=3)

    text("## Using the tokenizer")
    text("Now, given a new text, we can encode it.")
    tokenizer = BPETokenizer(params)  # @stepover
    string = "the quick brown fox"  # @inspect string
    indices = tokenizer.encode(string)  # @inspect indices
    reconstructed_string = tokenizer.decode(indices)  # @inspect reconstructed_string @stepover
    assert string == reconstructed_string

    text("In Assignment 1, you will go beyond this in the following ways:")
    text("- encode() currently loops over all merges. Only loop over merges that matter.")
    text("- Detect and preserve special tokens (e.g., <|endoftext|>).")
    text("- Use pre-tokenization (e.g., the GPT-2 tokenizer regex).")
    text("- Try to make the implementation as fast as possible.")


def train_bpe(string: str, num_merges: int) -> BPETokenizerParams:  # @inspect string, @inspect num_merges
    text("Start with the list of bytes of `string`.")
    indices = list(map(int, string.encode("utf-8")))  # @inspect indices
    merges: dict[tuple[int, int], int] = {}  # index1, index2 => merged index
    vocab: dict[int, bytes] = {x: bytes([x]) for x in range(256)}  # index -> bytes

    for i in range(num_merges):
        # Count the number of occurrences of each pair of tokens
        counts = count_adjacent_pairs(indices)  # @inspect counts @stepover

        # Find the most common pair
        pair = max(counts, key=counts.get)  # @inspect pair

        # Merge that pair
        new_index = 256 + i  # @inspect new_index
        merges[pair] = new_index  # @inspect merges
        vocab[new_index] = vocab[pair[0]] + vocab[pair[1]]  # @inspect vocab
        indices = merge(indices, pair, new_index)  # @inspect indices @stepover

    compression_ratio = get_compression_ratio(string, indices)  # @inspect compression_ratio

    return BPETokenizerParams(vocab=vocab, merges=merges)


def count_adjacent_pairs(indices: list[int]) -> dict[tuple[int, int], int]:
    """Return a dictionary mapping each adjacent pair of tokens in `indices` to the number of times it occurs."""
    counts = defaultdict(int)
    for index1, index2 in zip(indices, indices[1:]):
        counts[(index1, index2)] += 1
    return counts


if __name__ == "__main__":
    main()
