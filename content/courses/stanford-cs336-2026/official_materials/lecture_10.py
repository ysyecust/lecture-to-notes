from dataclasses import dataclass

from sympy import symbols, oo
from edtrace import text, link, image
from lecture_util import article_link
from references import Reference, gqa_2023, mla_2024, longformer_2020, sparse_transformer_2019, mistral_7b_2023, deepseek_v4_2026

# Define symbols corresponding to the shape of the Transformer model
B, S, T, D, F, N, K, H, L, V = symbols("B S T D F N K H L V", positive=True)
c = symbols("c", positive=True)  # Just a constant that helps with taking limits
memory_bandwidth = symbols("memory_bandwidth", positive=True)

scaling_book_transformers = Reference(title="Scaling book chapter on Transformers", url="https://jax-ml.github.io/scaling-book/transformers/")
scaling_book_inference = Reference(title="Scaling book chapter on inference", url="https://jax-ml.github.io/scaling-book/inference/")

def main():
    text("## Lecture 10: inference")
    image("images/inference-schema.png", width=600)

    text("### Understanding the inference workload")
    landscape()
    review_transformer()
    review_of_arithmetic_intensity()
    arithmetic_intensity_of_inference()
    throughput_and_latency()

    text("### Taking shortcuts (lossy)")
    reduce_kv_cache_size()
    quantization()
    model_pruning()

    text("Summary: reduce inference complexity without hurting accuracy")

    text("From scratch recipe:")
    text("1. Define faster model architecture")
    text("2. Train faster model")

    text("Distillation recipe:")
    text("1. Define faster model architecture")
    text("2. Initialize weights using original model (which has a different architecture)")
    text("3. Repair faster model (distillation)")

    text("### Use shortcuts but double check (lossless)")
    speculative_sampling()

    text("### Handling dynamic workloads")
    text("Batching over sequences in live traffic is tricky because:")
    text("1. Requests arrive at different times (waiting for batch is bad for early requests)")
    text("2. Sequences have shared prefixes (e.g., system prompts, generating multiple samples)")
    text("3. Sequences have different lengths (padding is inefficient)")

    continuous_batching()
    paged_attention()

    text("### Summary")
    text("- Inference is important (actual use, evaluation, reinforcement learning)")
    text("- Different characteristics compared to training (memory-bound, dynamic)")
    text("- Techniques: new architectures, quantization, pruning/distillation, speculative sampling")
    text("- Ideas from systems (speculative execution, paging)")
    text("- New architectures have huge potential for improvement")


def landscape():
    text("Inference shows up in many places:")
    text("- Actual use (chatbots, code completion, agents, batch data processing)")
    text("- Model evaluation (e.g., on instruction following)")
    text("- Reinforcement learning (sample many generations, then apply score)")

    text("Why **efficiency** matters: training is one-time cost, inference is repeated many times")
    text("- OpenAI processes ~8.6T tokens per day "), article_link("https://www.pymnts.com/artificial-intelligence-2/2025/openai-bests-google-in-race-for-consumer-ai-token-consumption/")
    text("- For reference, DeepSeek v4 was trained on 32T tokens "), link(deepseek_v4_2026)
    
    text("Moreover:")
    text("- Chatbots: most tokens are meant for human consumption (humans are bottleneck)")
    text("- Agents: query → internal trace → output for human (number of tokens generated can grow unbounded)")
    text("- Tokens generated = compute spent")

    text("Companies doing inference (a big deal for anyone who has a product or platform):")
    text("- Providers serving closed models (OpenAI, Anthropic, Google, etc.)")
    text("- Providers serving open-weight models (Together, Fireworks, Baseten, DeepInfra, Groq, Cerebras, etc.)")

    text("Open-source packages:")
    text("- vLLM: from Berkeley, pioneered PagedAttention, popular and good default "), link(title="GitHub", url="https://github.com/vllm-project/vllm")
    text("- SGLang: from Berkeley, pioneered RadixAttention, good for agentic workloads "), link(title="project", url="https://sgl-project.github.io/")
    text("- TensorRT-LLM: from NVIDIA, highly optimized for GPUs "), article_link("https://nvidia.github.io/TensorRT-LLM/overview.html")
    text("- llama.cpp: C++ only, supports CPU inference, runs locally "), link(title="GitHub", url="https://github.com/ggml-org/llama.cpp")

    text("Inference is huge. Important to make it fast.")

    text("What does \"fast\" mean (metrics)?")
    text("- Time-to-first-token (TTFT): how long user waits before any generation happens (for interactive applications)")
    text("- Latency (seconds/token): how fast tokens appear for *one* query (for interactive applications)")
    text("- Throughput (tokens/second): how fast tokens appear for *many* queries (for batch processing)")

    text("What governs efficiency?")
    text("- Training (supervised): you see all tokens, can parallelize over sequence (matmul in Transformer)")
    text("- Inference: you have to generate sequentially, can't parallelize over generation, so harder to fully utilize compute")


def review_transformer():
    link(scaling_book_transformers)
    text("Notation (similar to einops):")
    text("- Symbols denote dimensions (and their length): B (batch), T (sequence), D (model dim), H (head dim)")
    text("- Example: BT<font color=\"red\">D</font> x <font color=\"red\">D</font>H → BTH")
    text("- <font color=\"red\">Contracting (red)</font> dimensions appear in both operands and disappear from result")
    text("- Regular (black) dimensions appear in one operand and stay in result")
    text("- Example: <font color=\"blue\">B</font><font color=\"red\">D</font> x <font color=\"blue\">B</font><font color=\"red\">D</font> → B")
    text("- <font color=\"blue\">Batching (blue)</font> dimensions appear in both operands and stay in result")

    image("https://jax-ml.github.io/scaling-book/assets/img/transformer-diagram.png", width=800)
    text("Conventions:")
    text("- F = 4 D (MLP up-projects into 4x the model dimension)")
    text("- D = N H (model dimension split across N heads)")
    text("- N = K G (for GQA, number of heads split across K groups)")
    text("- S = T (during training, condition on S input tokens to predict T output tokens)")


def review_of_arithmetic_intensity():
    text("Setup: multiply X <font color=\"gray\">(B x D)</font> and W <font color=\"gray\">(D x F)</font> matrix")
    text("Intuition: B is batch size, D is hidden dimension, F is up-projection dimension in MLP")

    text("Let's do FLOPs and memory read/write accounting for the matrix multiplication (X * W).")
    flops = 0
    bytes_transferred = 0

    # Perform the operation
    text("1. Read X <font color=\"gray\">(B x D)</font> from HBM")
    bytes_transferred += 2*B*D   # 2 bytes for bf16
    text("2. Read W <font color=\"gray\">(D x F)</font> from HBM")
    bytes_transferred += 2*D*F
    text("3. Compute Y = X <font color=\"gray\">(B x D)</font> @ W <font color=\"gray\">(D x F)</font>")
    flops += 2*B*D*F
    text("4. Write Y <font color=\"gray\">(B x F)</font> to HBM")
    bytes_transferred += 2*B*F

    assert flops == 2*B*D*F
    assert bytes_transferred == 2*B*D + 2*D*F + 2*B*F

    text("Recall that **arithmetic intensity** is how much compute we do per byte transferred (want to be high).")
    intensity = (flops / bytes_transferred).simplify()  # @inspect intensity

    text("Assuming B is much less than D and F, then we can simplify:")
    intensity = intensity.subs(D, c*B).subs(F, c*B).limit(c, oo).simplify()  # @inspect intensity
    assert intensity == B

    text("Accelerator intensity of H100:")
    flops_per_second = 989e12
    memory_bandwidth = 3.35e12
    accelerator_intensity = flops_per_second / memory_bandwidth  # @inspect accelerator_intensity
    assert round(accelerator_intensity) == 295

    text("If computation intensity > accelerator intensity, **compute-bound** (good)")
    text("If computation intensity < accelerator intensity, **memory-bound** (bad)")
    text("Conclusion: compute-bound iff B > 295")

    text("Extreme case (B = 1, corresponding to matrix-vector product):")
    text("- Arithmetic intensity: 1")
    text("- Memory-bound (read D x F matrix, perform only 2 D F FLOPs)")
    text("- This is basically what happens with inference...")


def arithmetic_intensity_of_inference():
    link(scaling_book_inference)

    image("https://jax-ml.github.io/scaling-book/assets/img/naive-inference-1400.webp", width=800)
    text("Naive inference: to generate each token, feed history into Transformer")
    text("Complexity: generating T tokens requires O(T^3) FLOPs (one feedforward pass is O(T^2))")

    text("Observation: a lot of the work can be shared across prefixes")
    text("Solution: store **KV cache** in HBM")
    image("https://jax-ml.github.io/scaling-book/assets/img/cached-inference-1400.webp", width=800)
    text("KV cache: for every sequence (B), token (S), layer (L), head (K), store an H-dimensional vector")

    text("Two stages of inference:")
    text("1. **Prefill**: given a prompt, encode into vectors (parallelizable like in training)")
    text("2. **Generation**: generate new response tokens (sequential)")

    text("Let's compute the FLOPs and memory IO for both the MLP and attention layers.")
    text("S is the number of tokens we're conditioning on, T is the number of tokens we're generating.")
    text("Later, we'll specialize to prefill (T = S) and generation (T = 1).")

    text("### MLP layers (only looking at the matrix multiplications)")
    flops = 0
    bytes_transferred = 0
    
    # Perform the operation
    text("1. Read X <font color=\"gray\">(B x T x D)</font> from HBM")
    bytes_transferred += 2*B*T*D
    text("2. Read Wup <font color=\"gray\">(D x F)</font>, Wgate <font color=\"gray\">(D x F)</font>, Wdown <font color=\"gray\">(F x D)</font> from HBM")
    bytes_transferred += 3 * 2*D*F
    text("3. Compute U = X <font color=\"gray\">(B x T x D)</font> @ Wup <font color=\"gray\">(D x F)</font>")
    flops += 2*B*T*D*F
    text("4. Write U <font color=\"gray\">(B x T x F)</font> to HBM")
    bytes_transferred += 2*B*T*F
    text("5. Compute G = X <font color=\"gray\">(B x T x D)</font> @ Wgate <font color=\"gray\">(D x F)</font>")
    flops += 2*B*T*D*F
    text("6. Write G <font color=\"gray\">(B x T x F)</font> to HBM")
    bytes_transferred += 2*B*T*F
    text("7. Compute Y = GeLU(G)*U <font color=\"gray\">(B x T x F)</font> @ Wdown <font color=\"gray\">(F x D)</font>")
    flops += 2*B*T*D*F
    text("8. Write Y <font color=\"gray\">(B x T x D)</font> to HBM")
    bytes_transferred += 2*B*T*D

    assert flops == 6*B*T*D*F
    assert bytes_transferred == 4*B*T*D + 4*B*T*F + 6*D*F

    # Compute the arithmetic intensity
    intensity = (flops / bytes_transferred).simplify()  # @inspect intensity
    text("Assume that B*T is much smaller than D and F.")
    intensity = intensity.subs(D, c*B*T).subs(F, c*B*T).limit(c, oo).simplify()  # @inspect intensity
    assert intensity == B*T

    text("For the two stages:")
    text("1. Prefill: easy to make compute-bound (good) by making `B*T` large enough (large batches, long sequences)")
    text("2. Generation: two problems")
    text("- Generating one token at a time (T = 1)")
    text("- B is number of concurrent requests, unpredictable for interactive applications")

    text("### Attention layers (focusing on the matrix multiplications with FlashAttention)")
    text("- S is number of previous tokens (already generated)")
    text("- T is number of next tokens (to generate logits for)")
    flops = 0
    bytes_transferred = 0
    
    # Perform the operation
    text("1. Read Q <font color=\"gray\">(B x T x D)</font>, K <font color=\"gray\">(B x S x D)</font>, V <font color=\"gray\">(B x S x D)</font> from HBM")
    bytes_transferred += 2*B*T*D + 2*B*S*D + 2*B*S*D
    text("2. Compute A = Q <font color=\"gray\">(B x T x D)</font> @ K <font color=\"gray\">(B x S x D)</font>")
    flops += 2*B*S*T*D
    text("3. Compute Y = softmax(A) <font color=\"gray\">(B x S x T x K x G)</font> @ V <font color=\"gray\">(B x S x K x H)</font>")
    flops += 2*B*S*T*D
    text("4. Write Y <font color=\"gray\">(B x T x D)</font> to HBM")
    bytes_transferred += 2*B*T*D

    assert flops == 4*B*S*T*D
    assert bytes_transferred == 4*B*S*D + 4*B*T*D

    # Compute the arithmetic intensity
    intensity = (flops / bytes_transferred).simplify()  # @inspect intensity
    assert intensity == S*T / (S + T)

    text("For the two stages:")
    text("1. Prefill: T = S")
    prefill_intensity = intensity.subs(T, S).simplify()  # @inspect prefill_intensity
    assert prefill_intensity == S/2  # Good!
    text("2. Generation: T = 1")
    generate_intensity = intensity.subs(T, 1).simplify()  # @inspect generate_intensity
    assert generate_intensity < 1  # Bad!

    text("Unlike MLPs, no dependence on B, so batching doesn't help!")
    text("Why?")
    text("- In MLP layers, every sequence hits the same MLP weights (Wup, Wgate, Wdown don't depend on B)")
    text("- In attention layers, every sequence has its own KV cache vectors (Q, K, V all depend on B)")

    text("Summary:")
    text("- Prefill is compute-bound, generation is memory-bound")
    text("- Prefill MLP intensity: `B*S`")
    text("- Prefill attention intensity: `S/2`")
    text("- Generation MLP intensity: `B` (requires concurrent requests)")
    text("- Generation attention intensity: `<1` (impossible to improve)")


@dataclass(frozen=True)
class TransformerPerformanceStats:
    """
    Performance stats of a Transformer:
    - num_params: number of parameters (in bytes)
    - memory: total memory usage (parameters + KV cache) in bytes
    - latency: time to generate one token (seconds/token)
    - throughput: tokens generated per second
    """
    num_params: int
    memory: int
    latency: float
    throughput: float

    def substitute(self, key, value):
        """Substitute `key` with `value` in all stats."""
        return TransformerPerformanceStats(
            self.num_params.subs(key, value).simplify(),
            self.memory.subs(key, value).simplify(),
            self.latency.subs(key, value).simplify(),
            self.throughput.subs(key, value).simplify(),
        )


def compute_transformer_performance_stats(config) -> TransformerPerformanceStats:  # @inspect config
    """Compute various performance stats for the Transformer given `config`."""

    # Number of parameters in the Transformer
    num_params = 2*V*D + D*F*3*L + (2*D*N*H + 2*D*K*H)*L

    # How much memory the parameters take
    parameter_size = 2*num_params  # 2 for bf16 (training requires a larger multiple)
    
    # How much the KV cache takes per sequence (S tokens, K heads, H head dim, L layers)
    kv_cache_size_per_seq = S * (K*H) * L * 2 * 2  # 2 for key + value, 2 for bf16

    # Total memory usage
    memory = B * kv_cache_size_per_seq + parameter_size

    # *Latency* is determined by memory IO (read all parameters and KV cache for each step)
    latency = memory / memory_bandwidth

    # *Throughput* is the inverse of latency, but we're generating B tokens in parallel
    throughput = B / latency

    # Substitute config
    num_params = num_params.subs(config).simplify()  # @inspect num_params
    memory = memory.subs(config).simplify()  # @inspect memory
    latency = latency.subs(config).simplify()  # @inspect latency
    throughput = throughput.subs(config).simplify()  # @inspect throughput

    return TransformerPerformanceStats(num_params, memory, latency, throughput)


def llama2_13b_config(args={}):
    return {
        S: 1024,   # Sequence length
        D: 5120,   # Model dim
        F: 13824,  # Feed-forward dim
        N: 40,     # Number of query heads
        K: 40,     # Number of key/value heads
        H: 128,    # Head dimension
        L: 40,     # Number of layers
        V: 32000,  # Vocabulary size
        memory_bandwidth: 3.35e12,  # Memory bandwidth (bytes/second)
        **args
    }


def throughput_and_latency():
    text("So we have shown that inference is memory-bound.")
    text("Let us now compute the theoretical maximum latency and throughput of a single request.")
    text("Assumption: can overlap compute and communication perfectly and ignore overhead.")

    text("Instantiate latency and throughput for Llama 2 13B on an H100:")
    config = llama2_13b_config()
    stats = compute_transformer_performance_stats(config)

    # Batch size 1
    b1 = stats.substitute(B, 1)  # @inspect b1 @stepover

    # Batch size 64
    b64 = stats.substitute(B, 64)  # @inspect b64 @stepover
    text("Result: worse latency, better throughput")

    # Batch size 256
    b256 = stats.substitute(B, 256)  # @inspect b256 @stepover
    text("Result: even worse latency, even better throughput")
    h100_memory = 80e9  # H100 memory in bytes
    assert b256.memory > h100_memory  # Doesn't fit in memory!
    text("Result: doesn't fit into memory and throughput gains are diminishing too...")

    text("What increasing batch size does:")
    text("- Worsens latency because larger KV cache (O(B) size) to read/write")
    text("- Improves throughput because amortizes the cost of reading parameters")

    text("**Tradeoff** between latency and throughput:")
    text("1. Smaller batch sizes yield better latency but worse throughput")
    text("2. Larger batch sizes yield better throughput but worse latency")

    text("Easy parallelism: if you launch M copies of the model, latency is the same, throughput increases by M!")
    text("Harder parallelism: shard the model and the KV cache "), link(scaling_book_inference)

    text("Note: time-to-first-token (TTFT) is essentially a function of prefill time")
    text("Use smaller batch sizes during prefill for faster TTFT")
    text("Use larger batch sizes during generation to improve throughput")


def reduce_kv_cache_size():
    text("Recall that memory is the bottleneck for inference.")
    text("So let's try to reduce the size of the KV cache")
    text("...but make sure we don't lose too much accuracy.")

    text("### Grouped-query attention (GQA) "), link(gqa_2023)
    image("https://jax-ml.github.io/scaling-book/assets/img/gmqa.png", width=800)
    text("Idea: N query heads, but only K key and value heads, each interacting with N/K query heads")
    text("Multi-headed attention (MHA): K=N")
    text("Multi-query attention (MQA): K=1")
    text("Group-query attention (GQA): K is somewhere in between")

    text("Latency/throughput improves: "), link(gqa_2023)
    image("images/gqa-speed.png", width=500)

    text("Why does GQA improve latency and throughput?")
    text("GQA reduces the KV cache by a factor of N/K.")
    text("Reminder: reducing memory usage leads to speedup (since we're memory-bound).")

    # Original Llama 2 13B (MHA)
    config = llama2_13b_config({K: 40, B: 64})  # @stepover
    k40_b64 = compute_transformer_performance_stats(config)  # @inspect k40_b64 @stepover

    # GQA with 1:5 ratio (K:N)
    config = llama2_13b_config({K: 8, B: 64})  # Use GQA with 1:5 ratio @stepover
    k8_b64 = compute_transformer_performance_stats(config)  # @inspect k8_b64 @stepover
    text("Result: Worse latency, but better throughput (and it fits in memory now!)")

    # Now we can increase the batch size
    config = llama2_13b_config({K: 8, B: 256})  # Increase batch size @stepover
    k8_b256 = compute_transformer_performance_stats(config)  # @inspect k8_b256 @stepover
    text("Result: Worse latency, but better throughput (and still fits in memory!)")

    text("Check that accuracy doesn't drop: "), link(gqa_2023)
    image("images/gqa-accuracy.png", width=800)

    text("### Multi-head latent attention (MLA) "), link(mla_2024)
    image("images/mla-schema.png", width=800)
    text("Normal attention: KV cache consists of K = W_K h, V = W_V h (N*H dimensions)")
    text("MLA: store compressed vector c = W_c h (C dimensions), project up to K = W_K c, V = W_V c when needed")
    text("DeepSeek v2: reduce N*H = 16384 to C = 512")
    text("Wrinkle: MLA is not compatible with RoPE, so need to add additional 64 dimensions for RoPE, so 512 + 64 = 576 total dimensions")
    text("Latency/throughput improvements follow similarly from the KV cache reduction as argued earlier")

    text("Let's now check the accuracy.")
    text("First, MHA is better than GQA (though more expensive) [Table 8] "), link(mla_2024)
    image("images/mla-accuracy.png", width=800)
    text("Second, MLA is even a bit better than MHA (and much cheaper) [Table 9] "), link(mla_2024)
    image("images/mla-accuracy2.png", width=800)

    text("### Cross-layer attention (CLA) "), link("https://arxiv.org/abs/2405.12981")
    image("images/cla-diagram.png", width=500)
    text("Idea: share KVs across **layers** (just as GQA shares KVs across heads)")
    text("Empirically improves the pareto frontier of accuracy and KV cache size (latency and throughput)")
    image("images/cla-results.png", width=700)

    text("### Local (sliding window) attention "), link(longformer_2020), link(sparse_transformer_2019), link(mistral_7b_2023)
    image("images/longformer-attention.png", width=800)
    text("Idea: just look at the local context, which is most relevant for modeling")
    text("Effective context scales linearly with the number of layers")
    text("KV cache is independent of sequence length!")
    text("Problem: this can still hurt accuracy")
    text("Solution: interleave local attention with global attention (hybrid layers)")

    text("### DeepSeek v4 attention")
    text("- Supports 1M context length "),  link(deepseek_v4_2026)
    image("images/deepseek-v4-attention.png", width=800)
    text("- Compressed Sparse Attention (CSA): compresses every m tokens into 1")
    text("- DeepSeek Sparse Attention (DSA): selects the top k")
    text("- Heavily Compressed Attention (HCA): compresses even more")

    text("Summary:")
    text("- Goal: reduce the KV cache size (since inference is memory-bound) without hurting accuracy")
    text("- Lower-dimensional KV cache (GQA, MLA, CLA)")
    text("- Local attention (truncates the KV cache) on some of the layers")
    text("- Other ideas: linear attention / state-space-models (Mamba 2, GatedDeltaNet), diffusion models")


def quantization():
    text("Key idea: reduce the precision of numbers")
    text("Less memory means higher latency/throughput (since inference is memory-bound).")
    text("Of course we have to worry about accuracy...")

    # Mechanics
    x = 5.2342  # @inspect x
    scale = 0.1
    zero_point = 4
    x_quant = round(x / scale) + zero_point  # Quantize  @inspect x_quant
    x_approx = (x_quant - zero_point) * scale  # Dequantize @inspect x_approx

    image("https://www.datocms-assets.com/104802/1709770809-twitter-post-20.png", width=400), article_link("https://www.baseten.co/blog/fp8-efficient-model-inference-with-8-bit-floating-point-numbers/")
    text("- fp32 (4 bytes): needed for parameters and optimizer states during training")
    text("- bf16 (2 bytes): default for inference")
    text("- fp8 (1 byte) [-240, 240] for e4m3 on H100s: can train if you dare "), link("https://arxiv.org/pdf/2310.18313")
    text("- int8 (1 byte) [-128, 127]: less accurate but cheaper than fp8, but for inference only "), link("https://arxiv.org/pdf/2303.17951")
    text("- int4 (0.5 bytes) [-8, 7]: cheaper, even less accurate "), link("https://arxiv.org/pdf/2303.17951")

    link(title="Overview of approaches", url="https://apxml.com/posts/llm-quantization-techniques-explained")

    text("Quantization-aware training (QAT)")
    text("- During training, quantize-and-dequantize during the forward pass to simulate quantization errors")
    text("- Pro: weights are trained to work with quantization")
    text("- Con: requires expensive large-scale training")

    text("Post-training quantization (PTQ):")
    text("- Done after training, so much cheaper")
    text("- Run on sample data to determine scale and zero point for each layer or tensor")
    text("- GPTQ: use Hessian information to update non-quantized weights to account for quantization error "), link("https://arxiv.org/abs/2210.17323")

    text("### Activation-aware quantization (AWQ)")
    link("https://arxiv.org/abs/2306.00978")
    text("- Observation: some activation channels are large")
    text("- Weights that hit those matter more")
    text("- Allocate more precision to those weights")
    text("- Idea: select which weights (0.1-1%) to keep in high precision based on activations")
    text("- fp16 → int3 produces 4x lower memory, 3.2x speedup")
    image("images/awq-schema.png", width=800)


def model_pruning():
    text("Key idea: just rip out parts of an expensive model to make it cheaper")
    text("...and then fix it up.")

    text("Paper from NVIDIA "), link("https://arxiv.org/abs/2407.14679")
    image("images/pruning-kd-loop.png", width=600)
    text("Algorithm:")
    text("1. Identify important {layer, head, hidden dimension} on a small calibration dataset (1024 samples)")
    text("2. Remove unimportant layers to get a smaller model")
    text("3. Distill the original model into pruned model")

    text("Results:")
    image("images/pruning-kd.png", width=500)

    # TODO


def speculative_sampling():
    text("Recall the two stages of inference:")
    text("- Prefill: given a sequence, encode tokens in parallel (compute-bound) [note: also gives you probabilities]")
    text("- Generation: generate one token at a time (memory-bound)")
    text("In other words, checking is faster than generation.")

    text("Speculative sampling "), link("https://arxiv.org/abs/2211.17192"), link("https://arxiv.org/abs/2302.01318")
    text("- Use a cheaper **draft model** p to guess a few tokens (e.g., 4)")
    text("- Evaluate with target model q (process tokens in parallel), and accept if it looks good")
    link(title="Speculative sampling video", url="https://storage.googleapis.com/gweb-research2023-media/media/SpeculativeDecoding-1-Illustration.mp4")
    article_link("https://research.google/blog/looking-back-at-speculative-decoding/")

    image("images/speculative-sampling-algorithm.png", width=600)
    text("This is modified rejection sampling with proposal p and target q")
    text("Modification: always generate at least one candidate (rejection sampling will keep looping)")
    text("Key property: guaranteed to be an **exact sample** from the target model!")

    text("Proof by example: assume two vocabulary elements {A, B}")
    text("- Target model probabilities: [q(A), q(B)]")
    text("- Draft model probabilities: [p(A), p(B)]")
    text("- Assume p(A) > q(A) [draft model oversamples A].")
    text("- Therefore p(B) < q(B) [draft model undersamples B].")
    text("- Residual probabilities max(q-p, 0): [0, 1]")
    text("Compute the probabilities of speculatively sampling a token:")
    text("- P[sampling A] = p(A) * (q(A) / p(A)) + p(B) * 1 * 0 = q(A)")
    text("- P[sampling B] = p(B) * 1 + p(A) * (1 - q(A) / p(A)) * 1 = q(B)")

    image("images/speculative-sampling-results.png", width=600)
    image("images/speculative-sampling-stats.png", width=600)

    text("In practice:")
    text("- Target model has 70B parameters, draft model has 8B parameters")
    text("- Target model has 8B parameters, draft model has 1B parameters")
    text("- Try to make draft model as close to target (distillation)")

    text("Extensions to improve the draft model:")
    text("- Medusa: draft model generates multiple tokens in parallel "), link("https://arxiv.org/abs/2401.10774")
    text("- EAGLE: draft model takes high-level features from target model "), link("https://arxiv.org/pdf/2401.15077")
    image("images/medusa-eagle.png", width=600)

    text("Summary:")
    text("- Exact sampling from target model (thanks to math)!")
    text("- Exploits asymmetry between checking and generation")
    text("- Lots of room for innovation on the draft model (involves training)")


def continuous_batching():
    link(title="Orca: A Distributed Serving System for Transformer-Based Generative Models", url="https://www.usenix.org/system/files/osdi22-yu.pdf"), link(title="talk", url="https://www.youtube.com/watch?v=Ob9PPLxETYU")

    text("Problem:")
    text("- Training: get a dense block of tokens (batch size x sequence length)")
    text("- Inference: requests arrive and finish at different times, so you have a ragged array")
    image("https://images.ctfassets.net/xjan103pcp94/1LJioEsEdQQpDCxYNWirU6/82b9fbfc5b78b10c1d4508b60e72fdcf/cb_02_diagram-static-batching.png", width=600)

    text("Solution: iteration-level scheduling")
    text("- Decode step by step")
    text("- Add new requests to the batch as they arrive (so don't have to wait until generation completes)")

    text("Problem:")
    text("- Batching only works when all sequences have the same dimensionality (right?)")
    text("- But each request might have a different length")

    text("Solution: selective batching")
    text("- Training: when all sequences of the same length, operate on a B x S x H tensor")
    text("- But we might have different lengths: [3, H], [9, H], [5, H], etc.")
    text("- Attention computation: process each sequence separately")
    text("- Non-attention computation: concatenate all the sequences together to [3 + 9 + 5, H]")


def paged_attention():
    text("Paper that introduced vLLM in addition to PagedAttention "), link("https://arxiv.org/pdf/2309.06180.pdf")

    text("Previous status quo:")
    text("- Request comes in")
    text("- Allocate section of KV cache for prompt and response (up to a max length)")
    image("images/paged-attention-fragmentation.png", width=800)
    text("Problem: fragmentation (what happens to your hard drive)")
    text("- But this is wasteful since we might generate much fewer tokens (internal fragmentation)!")
    text("- Might be extra unused space between sections (external fragmentation)!")

    text("Solution: PagedAttention (remember operating systems)")
    text("- Divide the KV cache of a sequence into non-contiguous **blocks**")
    image("images/paged-attention-blocks.png", width=400)

    text("Two requests share the KV caches:")
    image("images/paged-attention-logical.png", width=800)

    text("In general, multiple types of sharing KV caches across sequences:")
    image("images/paged-attention-sharing.png", width=600)
    text("- Sharing the system prompt")
    text("- Sampling multiple responses per prompt (e.g., for program synthesis)")

    text("Solution: share prefixes, copy-on-write at the block level")
    image("images/paged-attention-parallel.png", width=600)

    text("Other vLLM optimizations:")
    text("- Kernel to fuse block read and attention (reduce kernel launch overhead)")
    text("- Use latest kernels (FlashAttention, FlashDecoding)")
    text("- Use CUDA graphs to avoid kernel launch overhead")

    text("Summary: use ideas from operating systems (paging) to make use of memory for dynamic workloads")


if __name__ == "__main__":
    main()
