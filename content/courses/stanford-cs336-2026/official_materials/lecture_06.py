import os
import time
from typing import Callable
import torch
from torch.profiler import ProfilerActivity
import triton
import triton.language as tl
from edtrace import text, link, image
from lecture_util import get_local_url
from gpu_util import cuda_if_available


def main():
    text("Last lecture: high-level overview of GPUs and performance")
    text("This lecture: benchmarking/profiling + writing kernels")

    review_of_gpus()
    benchmarking_and_profiling()           # Where are the bottlenecks?
    naive_vs_builtin_vs_compiled_gelu()    # Apply it to the GeLU example

    # Write Triton kernels
    triton_introduction()
    triton_gelu_example()      # Elementwise operation
    triton_softmax_example()   # Reduction (row fits in a block)
    triton_row_sum_example()   # Reduction (row doesn't fit in block)
    triton_matmul_relu_example()    # Tiling: use shared memory

    text("Summary:")
    text("- Know the programming model (PyTorch, Triton, PTX) to give you correctness")
    text("- Understand the hardware (SMs, warps, occupancy, bank conflicts, etc.) to optimize performance")
    text("- Benchmark to understand scaling")
    text("- Profile to see what's being executed for how long")
    text("- Triton: think in terms of thread blocks (read to shared memory, do stuff (fusion), write back HBM)")
    text("- Examples: GeLU (elementwise), softmax (row-wise), row sum (baby tiling), matmul (tiling)")

    text("Next time: more than one GPU!")


def review_of_gpus():
    text("## Hardware")
    image("images/gpu-hardware.png", width=800)
    text("| Accelerator                        | A100      | H100      | B200      |", verbatim=True)
    text("+------------------------------------+-----------+-----------+-----------+", verbatim=True)
    text("| # SMs                              |       108 |       132 |       148 |", verbatim=True)
    text("+------------------------------------+-----------+-----------+-----------+", verbatim=True)
    text("| Register size (per SM)             |    256 KB |    256 KB |    256 KB |", verbatim=True)
    text("| L1 cache + shared memory (per SM)  |    192 KB |    256 KB |    256 KB |", verbatim=True)
    text("| L2 cache size                      |     40 MB |     50 MB | 96-126 MB |", verbatim=True)
    text("| HBM size                           |     80 GB |     80 GB |    192 GB |", verbatim=True)
    text("+------------------------------------+-----------+-----------+-----------+", verbatim=True)
    text("| Register bandwidth                 | ~116 TB/s | ~401 TB/s | ~447 TB/s |", verbatim=True)
    text("| L1 cache + shared memory bandwidth |  ~19 TB/s |  ~33 TB/s |  ~19 TB/s |", verbatim=True)
    text("| L2 cache bandwidth                 | ~5-8 TB/s |  ~12 TB/s |   ~9 TB/s |", verbatim=True)
    text("| HBM bandwidth                      |    2 TB/s | 3.35 TB/s |    8 TB/s |", verbatim=True)

    text("(B200s also have tensor memory (TMEM) for tensor cores (between registers and shared memory) that are invisible to programmer.)")

    text("## Programming model")
    image("https://docs.nvidia.com/cuda/parallel-thread-execution/_images/grid-with-CTAs.png", width=600)
    text("- *Thread*: executes code on a small part of the data")
    text("- *Thread block* or concurrent thread array (CTA): a group of threads")
    text("- *Grid*: collection of thread blocks")

    text("(H100s and B200s also have thread block clusters that enable distributed shared memory.)")

    text("Why thread blocks?")
    text("For elementwise operations (e.g., GeLU), threads are most natural: each thread processes one element.")
    text("- f(i) for i = 0, ..., N-1")
    text("However, for non-elementwise operations like softmax or matrix multiplication, threads need to communicate.")
    text("Reading/writing from HBM is slow, so use shared memory (local to SM).")
    text("Thread block: a collection of threads that access the same shared memory.")
    text("Consequently, a thread block is scheduled on one SM.")
    text("In Triton, think natively in terms of thread blocks (later).")

    text("## Interaction between programming model and hardware")
    text("Programming model provides an abstraction of the hardware.")
    text("In principle, don't need to think about anything else (for correctness).")
    text("In practice, performance is very sensitive to the hardware, so need to understand it to obtain high performance.")

    text("Let's go over some considerations.")

    text("**Warps**:")
    text("- Within a thread block, threads are grouped into warps (32 threads per warp).")
    text("- Example: thread block has 64 threads => it has 2 warps.")
    text("| TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT | TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT |", verbatim=True)
    text("- All threads within a warp must execute same instructions in lockstep on an SM.")
    text("- Control divergence: if different threads in a warp need to execute different instructions (if A, else B), must be done sequentially (bad)")
    text("| AAAAAAAAA....................... |", verbatim=True)
    text("| .........BBBBBBBBBBBBBBBBBBBBBBB |", verbatim=True)
    text("- SM runs multiple warps and switches between them (e.g., when one warp is blocked on HBM reads/writes) with zero cost.")

    text("**(Warp) occupancy**:")
    text("- Each thread can use between 0 and 255 registers.")
    text("- The more registers threads use, the fewer threads can be scheduled on an SM (low occupancy).")
    text("- Low occupancy isn't necessarily bad if each thread is doing more work.")
    text("- Example: thread coarsening (each thread processes multiple elements).")
    text("- Example: thread block has 64 threads, each using 160 registers, SM has 65536 registers")
    
    # What we want to run
    num_threads_per_block = 128
    num_registers_per_thread = 160

    # What hardware offers
    max_registers = 65536  # Registers allowed per SM
    max_warps = 64         # Concurrent warps allowed per SM

    # What we can run at once
    assert num_registers_per_thread <= 255
    num_registers_per_block = num_threads_per_block * num_registers_per_thread  # @inspect num_registers_per_block
    num_blocks = max_registers // num_registers_per_block  # Limited by registers @inspect num_blocks
    num_warps = num_blocks * num_threads_per_block / 32  # @inspect num_warps
    occupancy = num_warps / max_warps  # @inspect occupancy

    text("**Bank conflicts** (shared memory):")
    text("- Shared memory is divided into 32 banks, each 4 bytes wide.")
    text("B00 B01 B02 B03 B04 B05 B06 B07 B08 B09 B10 B11 B12 B13 B14 B15 B16 B17 B18 B19 B20 B21 B22 B23 B24 B25 B26 B27 B28 B29 B30 B31", verbatim=True)
    text("... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ...", verbatim=True)
    text("... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ...", verbatim=True)
    text("... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ... ...", verbatim=True)
    text("- Each cycle, each bank can only be accessed by one thread (if not the same exact location).")
    text("- If multiple threads access the same bank, accesses serialized (bank conflict).")
    text("- Worst case example: matrix where each row spans all banks; 32 threads accessing first column results in 32-way bank conflict!")
    text("- Unavoidable: when doing matmul A @ B, access rows of A and columns of B")
    text("- Solution: swizzling rearranges shared memory (e.g., row xor col) to avoid bank conflicts")

    text("**Memory coalescing** (HBM):")
    text("- When the 32 threads in a warp access HBM, memory accesses combined into transactions of 128 bytes (cache lines).")
    text("M00 M01 M02 M03 M04 M05 M06 M07 M08 M09 M10 M11 M12 M13 M14 M15 M16 M17 M18 M19 M20 M21 M22 M23 M24 M25 M26 M27 M28 M29 M30 M31", verbatim=True)
    text("M32 M33 M34 M35 M36 M37 M38 M39 M40 M41 M42 M43 M44 M45 M46 M47 M48 M49 M50 M51 M52 M53 M54 M55 M56 M57 M58 M59 M60 M61 M62 M63", verbatim=True)
    text("- Best case: full coalescing, all threads access the same cache line (32 threads x 4 bytes = 128 bytes).")

    text("**Block occupancy**:")
    image("https://developer-blogs.nvidia.com/wp-content/uploads/2019/06/pasted-image-0.png", width=400)
    text("- Thread blocks scheduled onto SMs in waves.")
    text("- B200 has 148 SMs, if we launch 160 thread blocks, first wave has 148 blocks, second wave has 12 blocks.")
    text("- Wave quantization problem: last wave has fewer thread blocks, leaving some SMs idle (low block occupancy).")
    text("- Solution: make number of thread blocks divide # SMs.")

    text("Summary:")
    text("- Programming model: grid (HBM) -> thread block (shared memory) -> thread (registers)")
    text("- Details of hardware (warps, bank conflicts, memory coalescing, occupancy) determine performance")


def benchmarking_and_profiling():
    text("Recipe for success:")
    text("1. Benchmark and profile your code")
    text("2. Make changes")
    text("3. Benchmark and profile your code again")

    benchmarking()   # How long does it take?
    profiling()      # Where time is being spent?

    text("Benchmark and profile your code!")


def benchmarking():
    text("Benchmarking measures the wall-clock time of performing some operation.")
    text("It only gives you end-to-end time, not where time is spent (profiling).")

    text("It is still useful for:")
    text("- comparing different implementations (which is faster?), and")
    text("- understanding how performance scales (e.g., with dimension).")

    text("You can use [`torch.utils.benchmark`](https://pytorch.org/tutorials/recipes/recipes/benchmark.html).")
    text("We will roll our own to make benchmarking more transparent.")

    # Benchmark matrix multiplication
    matmul = run_operation2(dim=1024, operation=lambda a, b: a @ b)
    result = benchmark(matmul)  # @inspect result

    # See how timing scales with dimension
    results = {}
    for dim in [256, 512, 1024, 2048, 4096, 8192]:
         results[dim] = benchmark(run_operation2(dim=dim, operation=lambda a, b: a @ b))  # @inspect results @stepover

    text("Note: time is roughly constant when dimension is small, then cubic scaling.")


def benchmark(run: Callable, num_warmups: int = 1, num_trials: int = 3) -> float:
    """Benchmark `func` by running it `num_trials`.  Return the average time."""
    # Warmup: first times might be slower due to compilation, etc.
    # Since we will run the kernel multiple times, the timing that matters is steady state.
    for _ in range(num_warmups):
        run()
    torch.cuda.synchronize()  # Wait for CUDA threads to finish (important!)

    # Time it for real now!
    times: list[float] = [] # @inspect times
    for trial in range(num_trials):  # Do it multiple times to capture variance
        # Use CUDA events for accurate GPU timing (avoid capturing CPU overhead)
        start_event = torch.cuda.Event(enable_timing=True)
        end_event = torch.cuda.Event(enable_timing=True)

        start_event.record()  # Start timing
        run()  # Actually perform computation
        end_event.record()  # End timing

        torch.cuda.synchronize()  # Wait for CUDA threads to finish

        times.append((start_event.elapsed_time(end_event)))  # @inspect times

    mean_time = mean(times)   # @inspect mean_time @stepover
    return mean_time


def profiling():
    text("While benchmarking looks at end-to-end time, profiling looks at where time is spent.")
    text("Independent of time, profiling also helps you understand what's going under the hood.")

    text("PyTorch has a built-in [profiler](https://pytorch.org/tutorials/recipes/recipes/profiler_recipe.html).")
    text("In your assignment, you will use nsight to get more details.")

    text("## add(dim=2048)")
    add_profile = profile(run_operation2(dim=2048, operation=lambda a, b: a + b))
    text(add_profile, verbatim=True)

    text("## matmul(dim=2048)")
    matmul_profile = profile(run_operation2(dim=2048, operation=lambda a, b: a @ b)) # @stepover
    text(matmul_profile, verbatim=True)

    text("## matmul(dim=128)")
    matmul_profile = profile(run_operation2(dim=128, operation=lambda a, b: a @ b)) # @stepover
    text(matmul_profile, verbatim=True)

    text("Observations:")
    text("- You can see which CUDA kernels are actually being called (the long names).")
    text("- Different CUDA kernels are invoked depending on the tensor dimensions.")

    text("Name of CUDA kernel tells us something about the implementation.")
    text("Example: cutlass3x_sm100_simt_sgemm_f32_f32_f32_f32_f32_64x64x16_1x1x1_3_nnn_align1_bi...")
    text("- cutlass: NVIDIA's CUDA library for linear algebra")
    text("- sm100: corresponds to the NVIDIA Blackwell architecture (B200)")
    text("- f32: float32")
    text("- 64x64x16: tile shape (more on this later)")


def profile(run: Callable, num_warmups: int = 1):
    # Warmup
    for _ in range(num_warmups):
        run()
    torch.cuda.synchronize()

    # Run the code with the profiler
    with torch.profiler.profile(activities=[ProfilerActivity.CUDA],
            experimental_config=torch._C._profiler._ExperimentalConfig(verbose=True)) as prof:
        run()
        torch.cuda.synchronize()

    # Print out table
    table = prof.key_averages().table(sort_by="cuda_time_total",
                                      max_name_column_width=100,
                                      row_limit=10)

    # Append to profiles.txt
    with open("var/profiles.txt", "a") as f:
        f.write(f"Profile at {time.ctime()}:\n")
        f.write(table)
        f.write("\n\n")
    return table


def naive_vs_builtin_vs_compiled_gelu():
    text("Let's benchmark and profile the [GeLU activation function](https://pytorch.org/docs/stable/generated/torch.nn.GELU.html).")

    x = torch.tensor([1.])  # @inspect x

    # 1. Implementation naively from scratch in PyTorch (non-fused)
    y1 = naive_gelu(x)  # @inspect y1

    # 2. Built-in PyTorch implementation (fused)
    y2 = builtin_gelu(x)  # @inspect y2
    check_equal_1d(naive_gelu, builtin_gelu)  # Check it works

    # 3. Use PyTorch compiler on the naive implementation
    compiled_gelu = torch.compile(naive_gelu)  # @stepover
    y3 = compiled_gelu(x)  # @inspect y3 @stepover
    check_equal_1d(naive_gelu, compiled_gelu)  # Check it works (compilation shouldn't change semantics) @stepover

    # Benchmarking
    naive_time = benchmark(run_operation1(dim=16384, operation=naive_gelu)) # @inspect naive_time @stepover
    builtin_time = benchmark(run_operation1(dim=16384, operation=builtin_gelu)) # @inspect builtin_time @stepover
    compiled_time = benchmark(run_operation1(dim=16384, operation=compiled_gelu)) # @inspect compiled_time @stepover
    text("The builtin and compiled versions are significantly faster!")

    text("To understand why, let's look at the profiler to see where time is being spent.")

    text("## naive_gelu")
    naive_gelu_profile = profile(run_operation1(dim=16384, operation=naive_gelu))  # @stepover
    text(naive_gelu_profile, verbatim=True)

    text("## builtin_gelu")
    builtin_gelu_profile = profile(run_operation1(dim=16384, operation=builtin_gelu))  # @stepover
    text(builtin_gelu_profile, verbatim=True)

    text("## compiled_gelu")
    compiled_gelu_profile = profile(run_operation1(dim=16384, operation=compiled_gelu))  # @stepover
    text(compiled_gelu_profile, verbatim=True)

    text("Notes:")
    text("- Naive implementation: multiple kernels, requires many reads/writes from/to HBM (**no fusion**).")
    text("- Builtin and compiled versions: one kernel (**kernel fusion**), one read from HBM, one write to HBM.")
    text("- The compiled kernel is a Triton kernel.")


def triton_introduction():
    image("https://docs.nvidia.com/cuda/parallel-thread-execution/_images/grid-with-CTAs.png", width=600)

    text("In CUDA (developed by NVIDIA), specify what each thread does.")
    text("- Pros: fine-grained control")
    text("- Cons: need to manage more things (e.g., shared memory)")

    text("In Triton (developed by OpenAI), specify what each thread block does.")
    text("- Generally powerful enough (especially when getting started)")
    text("- Conceptual framework: load data into shared memory, operate on it, write back to global memory")


def triton_gelu_example():
    text("Let's write the Triton kernel for GeLU.")

    x = torch.randn(8192, device=cuda_if_available())
    y = triton_gelu(x)

    check_equal_1d(triton_gelu, naive_gelu)  # Check for correctness @stepover

    text("Triton compiles down to PTX (parallel thread execution), an assembly language for GPUs.")

    text("We can see the PTX code generated by Triton.")
    link(get_local_url("var/triton_gelu-ptx.txt"))

    text("Observations:")
    text("- ld.global.* and st.global.* reads and writes from global memory")
    text("- %ctaid.x is block index, %tid.x is thread index")
    text("- %f* are floating point registers, %r* are integer registers")
    text("- One thread processes 8 elements at the same time (thread coarsening)")


def triton_gelu(x: torch.Tensor):
    # Check input
    assert x.is_cuda
    assert x.is_contiguous()

    # Allocate output tensor
    y = torch.empty_like(x)

    # Determine grid (elements divided into blocks)
    # | T T T T T T T T | T T T T T T T T | T T T T T T T T | T T T T T T T T |
    # |    Block 0      |    Block 1      |     Block 2      |    Block 3     |
    num_elements = x.numel()  # @inspect num_elements
    BLOCK_SIZE = 1024  # Number of threads
    num_blocks = triton.cdiv(num_elements, BLOCK_SIZE)  # @inspect num_blocks

    # Launch the kernel
    kernel = triton_gelu_kernel[(num_blocks,)](x, y, num_elements, BLOCK_SIZE=BLOCK_SIZE)

    # Write out PTX (look at this later)
    output_ptx("triton_gelu", kernel)  # @stepover

    return y


@triton.jit
def triton_gelu_kernel(x_ptr, y_ptr, num_elements, BLOCK_SIZE: tl.constexpr):
    # Input starts at `x_ptr`
    # Output starts at `y_ptr`

    # | T T T T T T T T | T T T T T T T T | T T T T T T T T | T T T T T T T T |
    # |    Block 0      |    Block 1      |     Block 2      |    Block 3     |

    pid = tl.program_id(axis=0)      # Identifies the block
    start = pid * BLOCK_SIZE         # Starting index of this block

    # Indices where this thread block should operate
    offsets = start + tl.arange(0, BLOCK_SIZE)

    # Don't read/write past the end of the tensor
    mask = offsets < num_elements

    # Read
    x = tl.load(x_ptr + offsets, mask=mask)

    # Approx gelu is 0.5 * x * (1 + tanh(sqrt(2/pi) * (x + 0.044715 * x^3)))
    # Compute (tl.tanh doesn't exist, use tanh(a) = (exp(2a) - 1) / (exp(2a) + 1)
    a = 0.79788456 * (x + 0.044715 * x * x * x)
    exp = tl.exp(2 * a)
    tanh = (exp - 1) / (exp + 1)
    y = 0.5 * x * (1 + tanh)

    # Store
    tl.store(y_ptr + offsets, y, mask=mask)


def triton_softmax_example():
    text("So far, we've looked at elementwise operations in Triton (e.g., GeLU).")
    text("Now let us look at operations that aggregate over multiple values.")

    text("We will roughly follow the Triton fused softmax tutorial: "), link("https://triton-lang.org/main/getting-started/tutorials/02-fused-softmax.html")

    text("Recall the softmax operation is used in attention and generating probabilities.")
    text("Exponentiate and normalize each row of a matrix:")
    text("[0 0 0]      =>   [1/3 1/3 1/3]", verbatim=True)
    text("[1 1 -inf]        [1/2 1/2 0  ]", verbatim=True)

    text("Let's first start with the naive implementation and keep track of reads/writes.")
    x = torch.tensor([
        [5., 5, 5],
        [0, 0, 100],
    ], device=cuda_if_available())
    y1 = naive_softmax(x) # @inspect y1

    text("Now let us write the Triton kernel.")
    image("images/triton-softmax.png", width=600)
    y2 = triton_softmax(x)  # @inspect y2

    # Check our implementations are correct
    check_equal_2d(pytorch_softmax, naive_softmax) # @stepover
    check_equal_2d(pytorch_softmax, triton_softmax) # @stepover


def naive_softmax(x: torch.Tensor):
    # M: number of rows, N: number of columns
    M, N = x.shape

    # Compute the max of each row (MN reads, M writes)
    x_max = x.max(dim=1)[0]

    # Subtract off the max (MN + M reads, MN writes)
    x = x - x_max[:, None]

    # Exponentiate (MN reads, MN writes)
    numerator = torch.exp(x)

    # Compute normalization constant (MN reads, M writes)
    denominator = numerator.sum(dim=1)

    # Normalize (MN reads, MN writes)
    y = numerator / denominator[:, None]

    # Total: 5MN + M reads, 3MN + 2M writes
    # In principle, should have MN reads, MN writes (speedup of 4x!)
    return y


def triton_softmax(x: torch.Tensor):
    # Allocate output tensor
    y = torch.empty_like(x)

    # Determine grid
    M, N = x.shape                          # Number of rows x number of columns
    block_size = triton.next_power_of_2(N)  # Each block contains all the columns
    num_blocks = M                          # Each block is a row

    # Launch kernel
    triton_softmax_kernel[(M,)](
        x_ptr=x, y_ptr=y,
        x_row_stride=x.stride(0), y_row_stride=y.stride(0),
        num_cols=N, BLOCK_SIZE=block_size
    )

    return y


@triton.jit
def triton_softmax_kernel(x_ptr, y_ptr, x_row_stride, y_row_stride, num_cols, BLOCK_SIZE: tl.constexpr):
    assert num_cols <= BLOCK_SIZE

    # Process each row independently
    row_idx = tl.program_id(0)
    col_offsets = tl.arange(0, BLOCK_SIZE)

    # Read from global memory
    x_start_ptr = x_ptr + row_idx * x_row_stride
    x_ptrs = x_start_ptr + col_offsets
    x_row = tl.load(x_ptrs, mask=col_offsets < num_cols, other=float("-inf"))

    # Compute
    x_row = x_row - tl.max(x_row, axis=0)
    numerator = tl.exp(x_row)
    denominator = tl.sum(numerator, axis=0)
    y_row = numerator / denominator

    # Write back to global memory
    y_start_ptr = y_ptr + row_idx * y_row_stride
    y_ptrs = y_start_ptr + col_offsets
    tl.store(y_ptrs, y_row, mask=col_offsets < num_cols)


def triton_row_sum_example():
    text("In the softmax example, an entire row fits in a block, so the reduction happens within a block (handled by Triton).")
    text("What if the row doesn't fit in a block?")
    text("Example: 4096 columns, but block size is 1024...")

    text("Strategy:")
    text("- Break up row into tiles (4 in the example above)")
    text("- Each thread iterates over tiles and accumulates a sum")
    text("- Do final reduction (sum) over accumulators of each thread (shared memory or warp shuffles)")

    text("Consider the simpler example (row sum instead of softmax):")
    x = torch.tensor([[1., 2, 3, 4], [5, 6, 7, 8]], device=cuda_if_available())  # @inspect x
    y1 = builtin_row_sum(x)  # @inspect y1

    image("images/triton-row-sum.png", width=600)

    y2 = triton_row_sum(x)  # @inspect y2


def builtin_row_sum(x: torch.Tensor):
    return x.sum(dim=1)


def triton_row_sum(x: torch.Tensor, BLOCK_SIZE: int = 1024) -> torch.Tensor:
    M, N = x.shape
    y = torch.empty(M, device=x.device, dtype=x.dtype)
    row_sum_kernel[(M,)](x, y, N, BLOCK_SIZE=BLOCK_SIZE)
    return y


@triton.jit
def row_sum_kernel(x_ptr, out_ptr, N, BLOCK_SIZE: tl.constexpr):
    row = tl.program_id(0)  # Which row are we processing?

    # Accumulator for each thread
    # One row: T1 T2 T3 T4 | T1 T2 T3 T4 | T1 T2 T3 T4 (N = 12, BLOCK_SIZE = 4)
    acc = tl.zeros([BLOCK_SIZE], dtype=tl.float32)

    # Loop over tiles
    for start in range(0, N, BLOCK_SIZE):
        cols = start + tl.arange(0, BLOCK_SIZE)
        mask = cols < N
        x = tl.load(x_ptr + row * N + cols, mask=mask, other=0.0)
        acc += x

    # Final reduction from BLOCK_SIZE (all threads) to a scalar
    result = tl.sum(acc, axis=0)

    tl.store(out_ptr + row, result)


def triton_matmul_relu_example():
    text("Matrix multiplication is the bread and butter of deep learning.")
    a = torch.randn(1024, 1024, device=cuda_if_available())
    b = torch.randn(1024, 1024, device=cuda_if_available())
    c = naive_matmul_relu(a, b)

    text("How should we build a matmul kernel?")

    text("|        k                  n                     ", verbatim=True)
    text("|   [ A1 A2 A3 ]       [ B1 B2 B3 ]   [ C1 C2 C3 ]", verbatim=True)
    text("| m [ A4 A5 A6 ]  *  k [ B4 B5 B6 ] = [ C4 C5 C6 ]", verbatim=True)
    text("|   [ A7 A8 A9 ]       [ B7 B8 B9 ]   [ C7 C8 C9 ]", verbatim=True)

    text("**Naive approach:**")
    text("Fix any (m, n).")
    text("For each k:")
    text("- Read A[m, k] and B[k, n] from HBM.")
    text("- Multiply and accumulate.")
    text("Write result to C[m, n] in HBM.")

    text("Bottleneck: M K N reads, M N writes")
    text("Arithmetic intensity: O(1)")

    text("Computing C4 and C5 both need A4, A5, A6.")
    text("Can we read A4, A5, A6 from HBM once to compute both?")
    text("Answer: yes, using shared memory!")

    text("**Idealized approach:**")
    text("- Load all of A and B into shared memory, then compute C.")
    text("- Now we get M K + K N reads and M N writes.")
    text("- This yields the idealized O(N) arithmetic intensity from before.")
    text("- However, A and B are usually too large to fit in shared memory.")

    text("**Tiling:**")

    image("images/gemm_tiled.png", width=600)
    text("Key idea: divide the matrix C into output tiles (thread blocks).")
    text("Fix an output tile in C.")
    text("For each pair of (row tile of A, column tile of B):")
    text("- Load the corresponding A tile and B tile from HBM into shared memory.")
    text("- Perform matrix multiplication on the tiles.")
    text("- Accumulate into the partial sum (in shared memory).")
    text("Write output tile to HBM.")

    text("Arithmetic intensity: O(tile_size).")

    text("Bonus:")
    text("- Often, you want to apply an elementwise activation function.")
    text("- Example: GeLU(A @ B)")
    text("- Solution: kernel fusion!")

    text("**Implementation.**")

    text("Review: each matrix is linearized in memory")
    x = torch.tensor([[0., 1, 2, 3], [4, 5, 6, 7]])  # @inspect x
    stride_row, stride_col = x.stride()  # @inspect stride_row stride_col
    row = 1
    col = 2
    index = row * stride_row + col * stride_col  # @inspect index

    # Compute c = a @ b
    c = triton_matmul_relu(a, b)


def naive_matmul_relu(x: torch.Tensor, y: torch.Tensor):
    # Matmul followed by ReLU
    return torch.nn.functional.relu(x @ y)


def triton_matmul_relu(a: torch.Tensor, b: torch.Tensor):
    assert a.is_cuda and b.is_cuda
    assert a.is_contiguous() and b.is_contiguous()
    assert a.shape[1] == b.shape[0]

    # A is M x K, B is K x N
    M, K = a.shape
    K, N = b.shape

    # Allocate output tensor
    c = torch.empty((M, N), device=a.device)

    # Determine grid
    BLOCK_M, BLOCK_N, BLOCK_K = 64, 64, 32
    grid = (triton.cdiv(M, BLOCK_M), triton.cdiv(N, BLOCK_N))

    matmul_relu_kernel[grid](
        a, b, c,
        M, N, K,
        a.stride(0), a.stride(1),
        b.stride(0), b.stride(1),
        c.stride(0), c.stride(1),
        BLOCK_M, BLOCK_N, BLOCK_K,
    )

    return c


@triton.jit
def matmul_relu_kernel(
    a_ptr, b_ptr, c_ptr,    # Compute c = a @ b
    M, N, K,                # a is M x K, b is K x N, c is M x N
    stride_am, stride_ak,   # How to navigate a
    stride_bk, stride_bn,   # How to navigate b
    stride_cm, stride_cn,   # How to navigate c
    BLOCK_M: tl.constexpr,
    BLOCK_N: tl.constexpr,
    BLOCK_K: tl.constexpr,
):
    # We are working on the (m, n)-th tile
    pid_m = tl.program_id(0)
    pid_n = tl.program_id(1)

    # Indices
    indices_m = pid_m * BLOCK_M + tl.arange(0, BLOCK_M)  # Row indices of a [BLOCK_M]
    indices_n = pid_n * BLOCK_N + tl.arange(0, BLOCK_N)  # Column indices of b [BLOCK_N]
    indices_k = tl.arange(0, BLOCK_K)                    # Row indices of a = column indices of b [BLOCK_K]

    # Initial matrix of pointers of a and b
    a_ptrs = a_ptr + indices_m[:, None] * stride_am + indices_k[None, :] * stride_ak  # [BLOCK_M, BLOCK_K]
    b_ptrs = b_ptr + indices_k[:, None] * stride_bk + indices_n[None, :] * stride_bn  # [BLOCK_K, BLOCK_N]

    acc = tl.zeros([BLOCK_M, BLOCK_N], dtype=tl.float32)

    # Move along row tiles of a, column tiles of b
    for k in range(0, K, BLOCK_K):
        a = tl.load(a_ptrs, mask=(indices_m[:, None] < M) & (indices_k[None, :] + k < K), other=0.0)
        b = tl.load(b_ptrs, mask=(indices_k[:, None] + k < K) & (indices_n[None, :] < N), other=0.0)
        acc += tl.dot(a, b)
        a_ptrs += BLOCK_K * stride_ak  # Advance to the next row tile of a
        b_ptrs += BLOCK_K * stride_bk  # Advance to the next column tile of b

    # Apply activation function (e.g., ReLU)
    acc = tl.maximum(acc, 0.0)

    # Write output tile
    c_ptrs = c_ptr + indices_m[:, None] * stride_cm + indices_n[None, :] * stride_cn
    tl.store(c_ptrs, acc, mask=(indices_m[:, None] < M) & (indices_n[None, :] < N))


############################################################

def run_operation1(dim: int, operation: Callable) -> Callable:
    # Setup: create one random dim x dim matrices
    x = torch.randn(dim, dim, device=cuda_if_available())
    # Return a function to perform the operation
    return lambda : operation(x)


def run_operation2(dim: int, operation: Callable) -> Callable:
    # Setup: create two random dim x dim matrices
    x = torch.randn(dim, dim, device=cuda_if_available())
    y = torch.randn(dim, dim, device=cuda_if_available())
    # Return a function to perform the operation
    return lambda : operation(x, y)


def naive_gelu(x: torch.Tensor):
    # tanh approximation to the gelu activation function
    # https://docs.pytorch.org/docs/stable/generated/torch.nn.GELU.html
    return 0.5 * x * (1 + torch.tanh(0.79788456 * (x + 0.044715 * x * x * x)))


def builtin_gelu(x: torch.Tensor):
    # PyTorch's built-in GeLU with the tanh approximation
    return torch.nn.functional.gelu(x, approximate="tanh")


def pytorch_softmax(x: torch.Tensor):
    return torch.nn.functional.softmax(x, dim=-1)


def check_equal_1d(f1, f2):
    x = torch.randn(2048, device=cuda_if_available())
    y1 = f1(x)  # @stepover
    y2 = f2(x)  # @stepover
    assert torch.allclose(y1, y2, atol=1e-6)


def check_equal_2d(f1, f2):
    x = torch.randn(2048, 2048, device=cuda_if_available())
    y1 = f1(x)
    y2 = f2(x)
    assert torch.allclose(y1, y2, atol=1e-6)


def check_equal_2d_2d(f1, f2):
    x1 = torch.randn(2048, 2048, device=cuda_if_available())
    x2 = torch.randn(2048, 2048, device=cuda_if_available())
    y1 = f1(x1, x2)
    y2 = f2(x1, x2)
    assert torch.allclose(y1, y2, atol=1e-6)


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)

    
def output_ptx(name: str, kernel):
    """Print out the PTX code generated by Triton for the given `kernel`."""
    ptx_path = f"var/{name}-ptx.txt"
    with open(ptx_path, "w") as f:
        ptx = kernel.asm["ptx"]
        f.write(ptx)


if __name__ == "__main__":
    main()
