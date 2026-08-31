import torch
import time
import math
import sys
import os
from inspect import isfunction
from typing import Callable
from torch import nn, tensor
import torch.nn.functional as F
import torch.distributed as dist
import torch.multiprocessing as mp
from edtrace import text, image, link
from gpu_util import cuda_if_available
from lecture_util import article_link

if not torch.cuda.is_available():
    torch.cuda.synchronize = lambda: None  # No-op if CUDA is not available

def main():
    text("# Lecture 7: parallelism")
    text("Last week: parallelism within a single GPU")
    text("This week: parallelism across multiple GPUs")
    image("images/gpu-node-overview.png", width=700)

    text("In both cases, **compute** (arithmetic logic units) is far from inputs/outputs (**data**).")
    text("Unifying theme: orchestrate computation to avoid data transfer bottlenecks")

    text("Generalized hierarchy:")
    text("- Single node, single GPU: L1 cache / shared memory (fastest)")
    text("- Single node, single GPU: HBM")
    text("- Single node, multi-GPU: NVLink/NVSwitch")
    text("- Multi-node, multi-GPU: Infiniband/Ethernet (slowest)")

    text("Last week: reduce memory accesses via fusion/tiling")
    text("This week: reduce communication across GPUs/nodes via replication/sharding")

    text("Why do multi-GPU?")
    text("1. Your parameters (optimizer state + gradients + activations) don't fit on a single GPU.")
    text("2. You want to use more GPUs (more FLOPs) to train faster.")

    # When you execute this lecture directly (python lecture_07.py), it uses multiprocessing, which produces output from each process (below).
    # However, when you trace this lecture (python -m edtrace.execute -m lecture_07), we turn off multiprocessing.
    link(title="stdout for this lecture", url="var/traces/lecture_07_stdout.txt")

    text("### Part 1: building blocks of distributed communication/computation")
    collective_operations()    # Programming model
    hardware()                 # Hardware: how GPUs are connected
    torch_distributed()        # How this is implemented in NCCL/PyTorch
    benchmarking()             # Measure actual NCCL bandwidth

    text("### Part 2: distributed training")
    text("Walk through bare-bones implementations of each strategy on deep MLPs.")
    text("Recall that MLPs are the compute bottleneck in Transformers, so this is representative.")

    data_parallelism()         # Cut up along the batch dimension
    tensor_parallelism()       # Cut up along the width dimension
    pipeline_parallelism()     # Cut up along the depth dimension

    text("What's missing?")
    text("- Communication/computation overlap")
    text("- More general models (with attention, etc.)")
    text("- Other forms of parallelism (e.g., sequence parallelism, expert parallelism, combinations)")
    text("- Jax/TPUs: just define the model, the sharding strategy, and the Jax compiler handles the rest "), link(title="levanter", url="https://crfm.stanford.edu/2023/06/16/levanter-1_0-release.html")
    text("- But we're doing PyTorch so you can see how one builds up from the primitives")

    text("### Summary")
    text("- Many ways to parallelize: data (batch), tensor/expert (width), pipeline (depth), sequence (length)")
    text("- Data parallelism: DDP (all-reduce), FSDP/ZeRO (all-gather + reduce-scatter)")
    text("- Tensor parallelism: requires very fast interconnects (e.g., NVLink)")
    text("- Pipeline parallelism: can work with slow interconnects, but need to work to reduce pipeline bubbles")
    text("- Can **re-compute** or store in **memory** or store in another GPUs memory and **communicate**")
    text("- Hardware is getting faster, but will always want bigger models, so will have this hierarchical structure")


def collective_operations():
    text("**Collective operations** are the conceptual primitives used for distributed programming "), article_link("https://en.wikipedia.org/wiki/Collective_operation")
    text("- These are classic in the parallel programming literature from the 1980s.")
    text("- *Collective* means that you specify a general communication pattern across many devices.")
    text("- This can be better/faster than managing point-to-point communication yourself.")

    text("**Setup**:")
    image("images/ranks.png", width=500)
    text("- **Rank**: a particular device/GPU (e.g., 0, 1, 2, 3)")
    text("- **World size**: total number of devices (e.g., 4)")

    text("Operations:")
    text("- Broadcast, scatter, gather, reduce (foundations)")
    text("- All-gather, reduce-scatter, all-reduce (workhorse)")
    text("- All-to-all (for MoEs)")

    text("**Broadcast**: copy from rank 0 to all ranks")
    # Input
    rank0 = tensor([0., 1, 2, 3])

    # Output
    rank0 = tensor([0., 1, 2, 3])
    rank1 = tensor([0., 1, 2, 3])
    rank2 = tensor([0., 1, 2, 3])
    rank3 = tensor([0., 1, 2, 3])

    text("Minor use case: rank 0 loads initial checkpoint and broadcasts to all ranks")

    text("**Scatter** tensor on rank 0 to all ranks")
    # Input
    rank0 = tensor([0., 1, 2, 3])

    # Output
    rank0 = tensor([0.])
    rank1 = tensor([1.])
    rank2 = tensor([2.])
    rank3 = tensor([3.])

    text("Note: stepping stone to understanding reduce-scatter")

    text("**Gather** pieces from all ranks to rank 0 (opposite of scatter)")
    # Input
    rank0 = tensor([0.])
    rank1 = tensor([1.])
    rank2 = tensor([2.])
    rank3 = tensor([3.])

    # Output
    rank0 = tensor([0., 1, 2, 3])

    text("Note: stepping stone to understanding all-gather")

    text("**Reduce** pieces from all ranks to rank 0, applying some operation (e.g., sum, min, max)")
    # Input
    rank0 = tensor([0.])
    rank1 = tensor([1.])
    rank2 = tensor([2.])
    rank3 = tensor([3.])

    # Output
    rank0 = tensor([6.])  # Sum of all ranks (0 + 1 + 2 + 3)

    text("Note: stepping stone to understanding all-reduce")

    text("**All-gather**: perform gather to all ranks, not just rank 0")
    # Input
    rank0 = tensor([0.])
    rank1 = tensor([1.])
    rank2 = tensor([2.])
    rank3 = tensor([3.])

    # Output
    rank0 = tensor([0., 1, 2, 3])
    rank1 = tensor([0., 1, 2, 3])
    rank2 = tensor([0., 1, 2, 3])
    rank3 = tensor([0., 1, 2, 3])

    text("Use case: each rank holds parameter shard, gather to get full parameters for forward pass")

    text("**Reduce-scatter**: perform reduce on each dimension, scatter results")
    # Input
    rank0 = tensor([0., 1, 2, 3])
    rank1 = tensor([1., 2, 3, 4])
    rank2 = tensor([2., 3, 4, 5])
    rank3 = tensor([3., 4, 5, 6])

    # Output
    rank0 = tensor([6.])  # Sum along dim 0 (0 + 1 + 2 + 3)
    rank1 = tensor([10.]) # Sum along dim 1 (1 + 2 + 3 + 4)
    rank2 = tensor([14.]) # Sum along dim 2 (2 + 3 + 4 + 5)
    rank3 = tensor([18.]) # Sum along dim 3 (3 + 4 + 5 + 6)

    text("Use case: after backward pass, sum gradients from different data shards, but distribute storage")

    text("**All-reduce** = reduce-scatter + all-gather")
    # Input
    rank0 = tensor([0., 1, 2, 3])
    rank1 = tensor([1., 2, 3, 4])
    rank2 = tensor([2., 3, 4, 5])
    rank3 = tensor([3., 4, 5, 6])

    # Output
    rank0 = tensor([6., 10, 14, 18])
    rank1 = tensor([6., 10, 14, 18])
    rank2 = tensor([6., 10, 14, 18])
    rank3 = tensor([6., 10, 14, 18])

    text("Use case: after backward pass, sum gradients from different data shards, but replicate full parameters")
    text("Breaking all-reduce into reduce-scatter + all-gather allows for flexibility (e.g., ZeRO/FSDP)")

    text("**All-to-all**: each rank sends each other rank some tensor (most general)")
    # Input
    rank0 = tensor([0., 1, 2, 3])      # send  0 to rank 0,  1 to rank 1,  2 to rank 2,  3 to rank 3
    rank1 = tensor([4., 5, 6, 7])      # send  4 to rank 0,  5 to rank 1,  6 to rank 2,  7 to rank 3
    rank2 = tensor([8., 9, 10, 11])    # send  8 to rank 0,  9 to rank 1, 10 to rank 2, 11 to rank 3
    rank3 = tensor([12., 13, 14, 15])  # send 12 to rank 0, 13 to rank 1, 14 to rank 2, 15 to rank 3

    # Output
    rank0 = tensor([0, 4, 8, 12])
    rank1 = tensor([1, 5, 9, 13])
    rank2 = tensor([2, 6, 10, 14])
    rank3 = tensor([3, 7, 11, 15])

    text("Notes:")
    text("- Useful for MoEs: each rank has split of data and subset of experts; need to route data to experts")
    text("- For balanced splits, all-to-all looks like transpose")
    text("- Also handles unbalanced splits (but want splits to be as balanced as possible)")

    text("Way to remember the terminology:")
    text("- Reduce: performs some associative/commutative operation (sum, min, max)")
    text("- Scatter is inverse of gather")
    text("- All: means destination is all devices")


def hardware():
    text("Classic (in the home):")
    image("https://media.springernature.com/lw685/springer-static/image/art%3A10.1186%2Fs42774-021-00098-3/MediaObjects/42774_2021_98_Fig1_HTML.png?as=webp", width=500)
    text("- GPUs on same node communicate via a PCI(e) bus (v7.0, 16 lanes => 242 GB/s) "), article_link("https://en.wikipedia.org/wiki/PCI_Express")
    text("- GPUs on different nodes communicate via Ethernet (~200 MB/s)")
    
    text("Modern (in the data center):")
    image("images/gpu-node-overview.png", width=700)

    text("Typical setup:")
    text("- 8 GPUs per node, connected by NVLink to an NVSwitch (B200s' NVLink 5.0 gets 1.8 TB/s; HBM was 8 TB/s)")
    text("- 256 nodes per pod, connected by Infiniband (via PCIe -> HCA / Infiniband NIC -> Infiniband cable) (~0.05 TB/s)")
    text("- N pods per cluster / datacenter, connected by Ethernet (via PCIe -> CPU)")

    text("Bypassing the CPU:")
    text("- Ethernet requires passing through the CPU (copying data to kernel socket buffer, build TCP packets, copy to NIC ring buffer)")
    text("- Remote Direct Memory Access (RDMA): allows one GPU to directly read/write another GPU's memory without involving the CPU")
    text("- Infiniband supports RDMA, but standard Ethernet does not")

    text("Advancements:")
    text("- GB200/GB300 NVL72: 8 GPUs per tray, 9 trays per rack -> 72 GPUs in one NVLink domain")
    text("- RDMA over Converged Ethernet (RoCE): Ethernet bypasses CPU, similar but cheaper/weaker than Infiniband, used by Meta")

    text("### NVIDIA Collective Communication Library (NCCL)")
    text("NCCL translates collective operations into low-level packets that are sent between GPUs. "), link(title="talk", url="https://www.nvidia.com/en-us/on-demand/session/gtcspring21-s31880/")
    text("- Detects topology of hardware (e.g., number of nodes, switches, NVLink/PCIe)")
    text("- Optimizes the path between GPUs")
    text("- Launches GPU kernels to send/receive data")


def torch_distributed():
    text("PyTorch distributed library (`torch.distributed`) "), link(title="documentation", url="https://pytorch.org/docs/stable/distributed.html")
    text("- Provides clean interface for collective operations (e.g., `all_gather_into_tensor`)")
    text("- Supports multiple backends for different hardware: gloo (CPU), nccl (GPU)")
    text("- Also supports higher-level algorithms (e.g., `FullyShardedDataParallel`) [not used in this course]")

    text("Let's walk through some examples.")
    spawn(collective_operations_main, world_size=4)


def collective_operations_main(rank: int, world_size: int):  # @inspect rank world_size
    """This function is running asynchronously for each process (rank = 0, ..., world_size - 1)."""
    setup(rank, world_size)

    ### All-reduce (dist = torch.distributed)
    dist.barrier()  # Waits for all processes to get to this point (in this case, for print statements)

    data = tensor([0., 1, 2, 3], device=cuda_if_available(rank)) + rank  # Both input and output

    print(f"Rank {rank} [before all-reduce]: {data}", flush=True)
    dist.all_reduce(tensor=data, op=dist.ReduceOp.SUM, async_op=False)  # Modifies tensor in place
    print(f"Rank {rank} [after all-reduce]: {data}", flush=True)

    ### Reduce-scatter
    dist.barrier()

    input = torch.arange(world_size, dtype=torch.float32, device=cuda_if_available(rank)) + rank  # Input
    output = torch.empty(1, device=cuda_if_available(rank))  # Allocate output

    print(f"Rank {rank} [before reduce-scatter]: input = {input}, output = {output}", flush=True)
    dist.reduce_scatter_tensor(output=output, input=input, op=dist.ReduceOp.SUM, async_op=False)
    print(f"Rank {rank} [after reduce-scatter]: input = {input}, output = {output}", flush=True)

    ### All-gather
    dist.barrier()

    input = output  # Input is the output of reduce-scatter
    output = torch.empty(world_size, device=cuda_if_available(rank))  # Allocate output

    print(f"Rank {rank} [before all-gather]: input = {input}, output = {output}", flush=True)
    dist.all_gather_into_tensor(output_tensor=output, input_tensor=input, async_op=False)
    print(f"Rank {rank} [after all-gather]: input = {input}, output = {output}", flush=True)

    text("Indeed, all-reduce = reduce-scatter + all-gather!")

    cleanup()


def benchmarking():
    text("How fast does communication happen?")

    # All-reduce
    spawn(all_reduce, world_size=4, num_elements=100 * 1024**2)

    # Reduce-scatter
    spawn(reduce_scatter, world_size=4, num_elements=100 * 1024**2)

    text("References:")
    link(title="How to reason about collective operations", url="https://github.com/NVIDIA/nccl-tests/blob/master/doc/PERFORMANCE.md#allreduce")
    link(title="Sample benchmarking code", url="https://github.com/stas00/ml-engineering/blob/master/network/benchmarks/all_reduce_bench.py")


def all_reduce(rank: int, world_size: int, num_elements: int):
    setup(rank, world_size)  # @stepover

    # Create tensor
    data = torch.randn(num_elements, device=cuda_if_available(rank))

    # Warmup
    dist.all_reduce(tensor=data, op=dist.ReduceOp.SUM, async_op=False)
    torch.cuda.synchronize()  # Wait for CUDA kernels to finish
    dist.barrier()            # Wait for all the processes to get here

    # Perform all-reduce
    start_time = time.time()
    dist.all_reduce(tensor=data, op=dist.ReduceOp.SUM, async_op=False)
    torch.cuda.synchronize()  # Wait for CUDA kernels to finish
    dist.barrier()            # Wait for all the processes to get here
    end_time = time.time()

    duration = end_time - start_time
    print(f"[all_reduce] Rank {rank}: all_reduce(world_size={world_size}, num_elements={num_elements}) took {render_duration(duration)}", flush=True)  # @stepover

    # Measure the effective bandwidth
    dist.barrier()
    size_bytes = data.element_size() * data.numel()
    sent_bytes = size_bytes * 2 * (world_size - 1)  # 2x because send + receive, world_size-1 steps in all-reduce
    total_duration = world_size * duration
    bandwidth = sent_bytes / total_duration
    print(f"[all_reduce] Rank {rank}: all_reduce measured bandwidth = {round(bandwidth / 1024**3)} GB/s", flush=True)

    # Notes:
    # - Effective bandwidth ~ 2 * size_bytes / total_duration
    # - Independent of world_size
    # - Independent of topology (ring or tree)

    cleanup()  # @stepover


def reduce_scatter(rank: int, world_size: int, num_elements: int):
    setup(rank, world_size)  # @stepover

    # Create input and outputs
    input = torch.randn(world_size, num_elements, device=cuda_if_available(rank))  # Each rank has a matrix
    output = torch.empty(num_elements, device=cuda_if_available(rank))

    # Warmup
    dist.reduce_scatter_tensor(output=output, input=input, op=dist.ReduceOp.SUM, async_op=False)
    torch.cuda.synchronize()  # Wait for CUDA kernels to finish
    dist.barrier()            # Wait for all the processes to get here

    # Perform reduce-scatter
    start_time = time.time()
    dist.reduce_scatter_tensor(output=output, input=input, op=dist.ReduceOp.SUM, async_op=False)
    torch.cuda.synchronize()  # Wait for CUDA kernels to finish
    dist.barrier()            # Wait for all the processes to get here
    end_time = time.time()

    duration = end_time - start_time
    print(f"[reduce_scatter] Rank {rank}: reduce_scatter(world_size={world_size}, num_elements={num_elements}) took {render_duration(duration)}", flush=True)  # @stepover

    # Measure the effective bandwidth
    dist.barrier()
    data_bytes = input.element_size() * input.numel()  # How much data in the input
    sent_bytes = data_bytes * (world_size - 1)  # How much needs to be sent (no 2x here)
    total_duration = world_size * duration  # Total time for transmission
    bandwidth = sent_bytes / total_duration
    print(f"[reduce_scatter] Rank {rank}: reduce_scatter measured bandwidth = {round(bandwidth / 1024**3)} GB/s", flush=True)

    # Notes:
    # - all-reduce = reduce-scatter + all-gather
    # - all-reduce moves 2x the data in 2x the time compared to reduce-scatter, so similar bandwidth

    cleanup()  # @stepover


def data_parallelism():
    image("images/data-parallelism.png", width=300)
    text("Sharding strategy: each rank gets a slice of the data")

    data = generate_sample_data()
    spawn(data_parallelism_main, world_size=4, data=data, num_layers=4, num_steps=1)

    text("Notes:")
    text("- Losses are different across ranks (computed on local data)")
    text("- Gradients are all-reduced to be the same across ranks")
    text("- Therefore, parameters remain the same across ranks")

    text("Next time: FSDP/ZeRO: use all-gather and reduce-scatter to avoid holding all parameters in memory")


def generate_sample_data():
    batch_size = 128
    num_dim = 1024
    data = torch.randn(batch_size, num_dim)
    return data


def data_parallelism_main(rank: int, world_size: int, data: tensor, num_layers: int, num_steps: int):
    setup(rank, world_size)  # @stepover

    # Get the slice of data for this rank (in practice, each rank should load only its own data)
    # --- B0 ---
    # --- B1 ---
    # --- B2 ---
    # --- B3 ---
    batch_size = data.size(0)  # @inspect batch_size
    num_dim = data.size(1)  # @inspect num_dim
    local_batch_size = int_divide(batch_size, world_size)  # @inspect local_batch_size @stepover
    start_index = rank * local_batch_size  # @inspect start_index
    end_index = start_index + local_batch_size  # @inspect end_index
    data = data[start_index:end_index].to(cuda_if_available(rank))

    # Create MLP parameters params[0], ..., params[num_layers - 1] (each rank has all parameters)
    params = [get_init_params(num_dim, num_dim, rank) for layer in range(num_layers)]
    optimizer = torch.optim.AdamW(params, lr=1e-3)  # Each rank has own optimizer state

    for step in range(num_steps):
        # Forward pass
        x = data
        for param in params:
            x = x @ param
            x = F.gelu(x)
        loss = x.square().mean()  # Loss function is average squared magnitude

        # Backward pass
        loss.backward()

        # Sync gradients across workers (ONLY difference between standard training and DDP)
        for param in params:
            dist.all_reduce(tensor=param.grad, op=dist.ReduceOp.AVG, async_op=False)

        # Update parameters
        optimizer.step()

        print(f"[data_parallelism] Rank {rank}: step = {step}, loss = {loss.item()}, params = {[summarize_tensor(params[layer]) for layer in range(num_layers)]}", flush=True)  # @stepover

    cleanup()  # @stepover


def tensor_parallelism():
    image("images/tensor-parallelism.png", width=300)
    text("Sharding strategy: each rank gets part of each layer, transfer all data/activations")

    data = generate_sample_data()
    spawn(tensor_parallelism_main, world_size=4, data=data, num_layers=4)


def tensor_parallelism_main(rank: int, world_size: int, data: tensor, num_layers: int):
    setup(rank, world_size)  # @stepover

    data = data.to(cuda_if_available(rank))  # All ranks get the data (batch_size x num_dim)
    batch_size = data.size(0)  # @inspect batch_size
    num_dim = data.size(1)  # @inspect num_dim
    local_num_dim = int_divide(num_dim, world_size)  # Shard `num_dim`  @inspect local_num_dim @stepover

    # Create model (each rank gets 1/world_size of the parameters)
    #  |  |  |  |
    # W0 W1 W2 W3
    #  |  |  |  |
    params = [get_init_params(num_dim, local_num_dim, rank) for layer in range(num_layers)]

    # Forward pass
    x = data
    for layer in range(num_layers):
        # Compute activations (batch_size x local_num_dim)
        x = x @ params[layer]  # Note: this is only on a slice of the parameters
        x = F.gelu(x)

        # Allocate memory for activations (world_size x batch_size x local_num_dim)
        activations = [torch.empty(batch_size, local_num_dim, device=cuda_if_available(rank)) for _ in range(world_size)]

        # Send activations via all gather
        dist.all_gather(tensor_list=activations, tensor=x, async_op=False)

        # Concatenate them to get batch_size x num_dim
        x = torch.cat(activations, dim=1)

    print(f"[tensor_parallelism] Rank {rank}: forward pass produced activations {summarize_tensor(x)}", flush=True)  # @stepover

    # Backward pass: homework exercise

    cleanup()  # @stepover


def pipeline_parallelism():
    image("images/pipeline-parallelism.png", width=300)
    text("Sharding strategy: each rank gets subset of layers, transfer all data/activations")

    data = generate_sample_data()
    spawn(pipeline_parallelism_main, world_size=2, data=data, num_layers=4, num_micro_batches=4)


def pipeline_parallelism_main(rank: int, world_size: int, data: tensor, num_layers: int, num_micro_batches: int):
    setup(rank, world_size)  # @stepover

    # Use all the data
    data = data.to(cuda_if_available(rank))
    batch_size = data.size(0)  # @inspect batch_size
    num_dim = data.size(1)  # @inspect num_dim

    # Split up layers
    local_num_layers = int_divide(num_layers, world_size)  # @inspect local_num_layers @stepover

    # Each rank gets a subset of layers
    local_params = [get_init_params(num_dim, num_dim, rank) for layer in range(local_num_layers)]  # @stepover

    # Forward pass

    # Break up into micro batches to minimize the bubble
    micro_batch_size = int_divide(batch_size, num_micro_batches)  # @inspect micro_batch_size @stepover
    if rank == 0:
        # The data
        micro_batches = data.chunk(chunks=num_micro_batches, dim=0)
    else:
        # Allocate memory for activations
        micro_batches = [torch.empty(micro_batch_size, num_dim, device=cuda_if_available(rank)) for _ in range(num_micro_batches)]

    for x in micro_batches:
        # Get activations from previous rank
        if rank - 1 >= 0:
            dist.recv(tensor=x, src=rank - 1)

        # Compute layers assigned to this rank
        for param in local_params:
            x = x @ param
            x = F.gelu(x)

        # Send to the next rank
        if rank + 1 < world_size:
            print(f"[pipeline_parallelism] Rank {rank}: sending {summarize_tensor(x)} to rank {rank + 1}", flush=True)  # @stepover
            dist.send(tensor=x, dst=rank + 1)

    text("Not handled: overlapping communication/computation to eliminate pipeline bubbles")

    # Backward pass: homework exercise

    cleanup()  # @stepover

############################################################

def setup(rank: int, world_size: int):
    """Initializes the distributed environment (called at start of process)."""
    # Specify where master lives (rank 0), used to coordinate (actual data goes through NCCL)
    os.environ["MASTER_ADDR"] = "localhost"
    os.environ["MASTER_PORT"] = "15623"

    if torch.cuda.is_available():
        dist.init_process_group("nccl", rank=rank, world_size=world_size)
    else:
        dist.init_process_group("gloo", rank=rank, world_size=world_size)


def cleanup():
    """Cleans up the distributed environment (called at end of process)."""
    torch.distributed.destroy_process_group()


class DisableDistributed:
    """
    Context manager that temporarily disables distributed functions (replaces with no-ops).
    This is for when we're tracing the lecture, since we can't trace through
    multiprocessing, so we just want to run the function directly without
    distributed communication.
    """
    def __enter__(self):
        self.old_functions = {}
        for name in dir(dist):
            value = getattr(dist, name, None)
            if isfunction(value):
                self.old_functions[name] = value
                setattr(dist, name, lambda *args, **kwargs: None)

    def __exit__(self, exc_type, exc_value, traceback):
        for name in self.old_functions:
            setattr(dist, name, self.old_functions[name])


def spawn(func: Callable, world_size: int, *args, **kwargs):
    """
    Launches `world_size` processes that each calls `func` on world_size, args, kwargs.
    Note: if we are being traced (inside edtrace), we just run the function directly without multiprocessing and disable distributed functions.
    """
    # Note: assume kwargs are in the same order as what main needs
    if not sys.gettrace():
        # This is the normal code path for multiprocessing
        args = (world_size,) + args + tuple(kwargs.values())
        mp.spawn(func, args=args, nprocs=world_size, join=True)
    else:
        # If we're being traced (inside edtrace), just run the function directly.
        with DisableDistributed():  # @stepover
            args = (0, world_size,) + args + tuple(kwargs.values())
            func(*args)


def get_init_params(num_inputs: int, num_outputs: int, rank: int) -> nn.Parameter:
    """Create parameters and put them on the `rank`-th GPU."""
    torch.random.manual_seed(0)  # For reproducibility
    return nn.Parameter(torch.randn(num_inputs, num_outputs, device=cuda_if_available(rank)) / math.sqrt(num_outputs))


def int_divide(a: int, b: int):
    """Return a / b and throw an error if there's a remainder."""
    assert a % b == 0
    return a // b


def summarize_tensor(tensor: tensor) -> str:
    return "x".join(map(str, tensor.shape)) + "[" + str(round(tensor.view(-1)[0].item(), 4)) + "...]"


def render_duration(duration: float) -> str:
    if duration < 1e-3:
        return f"{duration * 1e6:.2f}us"
    if duration < 1:
        return f"{duration * 1e3:.2f}ms"
    return f"{duration:.2f}s"


if __name__ == "__main__":
    main()
