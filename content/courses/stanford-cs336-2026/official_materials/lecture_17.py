from edtrace import text, image, link
from lecture_util import article_link, post_link

def main():
    text("## Lecture 17: multimodal models")
    text("So far: language models")
    text("> text ⇒ text")
    text("The world is multimodal:")
    image("images/multimodality.png", width=600)

    text("Ultimate goal: **omni model**")
    text("- Input any combination of modalities (understanding)")
    text("- Output any combination of modalities (generation)")

    text("Where we are today:")
    text("- Transformers work really well. So we gotta use them.")
    text("- Transformers speak tokens (discrete or continuous), where a token represents some ~semantic unit of information.")
    text("- Therefore, we must convert everything into tokens.")
    text("- Note: we had to do this with text (recall the tokenization lecture).")
    text("- For non-text modalities, this is more challenging...")

    text("Questions:")
    text("1. How do we input non-text data (e.g., understand images)?")
    text("2. How do we output non-text data (e.g., generate audio)?")

    # Encoding images
    clip()
    siglip()

    # Injecting image encodings into LLMs
    llava()
    llava_onevision()
    qwen_vl()
    qwen2_vl()
    qwen3_vl()

    # Towards Omni models
    chameleon()

    text("Summary:")
    text("- Frontier models are expected to be multimodal (natively multimodal, omni)")
    text("- Fundamental challenge: how to encode non-text modalities?")
    text("- Comprehension and generation might demand different things (semantics versus finer-grained details)")
    text("- Balance images + video (lower information density) and text for training stability")
    text("- Continuous encoders + Transformer + diffusion models for generation")


def clip():
    text("CLIP (Contrastive Language-Image Pretraining) "), link("https://arxiv.org/abs/2103.00020")

    text("Context:")
    text("- Computer vision models were trained on annotated images.")
    text("- Question: is it possible to leverage the much larger amount of (image, caption) pairs?")
    image("images/clip.png", width=800)

    text("Method:")
    text("- Get a batch of (image, text) examples (e.g., 32768)")
    text("- Encode each image and each text")
    text("- For each image, prefer its aligned text over other texts")
    text("- For each text, prefer its aligned image over other images")
    image("images/clip-code.png", width=400)

    text("Data:")
    text("- Searched for 500K queries, get ~20K (image, text) pairs per query")
    text("- Trained on 400M image-text pairs")
    text("- Didn't release the dataset")
    text("- Reproduced in OpenCLIP (using LAION-5B dataset, which used CLIP for filtering) "), link("https://arxiv.org/abs/2212.07143")

    text("Data processing "), link(title="code", url="https://github.com/openai/CLIP/blob/main/clip/clip.py#L79")
    text("- Images come in all resolutions (arbitrary W x H)")
    text("- Resize using bicubic interpolation so shorter side is 336 pixels")
    text("- Center crop (cuts off borders to get 336 x 336)")
    
    text("Vision encoder:")
    text("- Experimented with ResNet-50 and Vision Transformers "), link("https://arxiv.org/pdf/2010.11929")
    image("images/vit.png", width=600)
    text("- Attention pooling: do QKV with query = global average of activations")
    text("- Best model: ViT-L/14@336px (L = large, 14x14 patches, 3 channels, trained on 336x336 resolution images)")

    text("Text encoder:")
    text("- GPT-2 Transformer (63M parameters, 12 layers)")
    text("- Encode [BOS] ... [EOS], return [EOS] activation at highest layer")

    text("Headline result:")
    text("- On ImageNet, zero-shot CLIP outperformed ResNet-50 trained on 1.2M ImageNet images")

    text("Ablation:")
    text("- Alternative: predict text from images directly")
    text("- Much less compute efficient compared to CLIP-style ranking")
    image("images/clip-efficiency.png", width=400)

    text("Summary:")
    text("- Encoding of images captures semantics given by (noisy) text")
    text("- Design decisions chosen based on image classification (not very fine-grained)")
    text("- Technical: requires large batch sizes, softmax operation over full batch")


def siglip():
    text("SigLIP (Sigmoid Loss for Language Image Pre-Training) "), link("https://arxiv.org/abs/2303.15343")

    text("Objective:")
    text("- CLIP: multiclass classification for (text, image) versus (text, image') for all image'")
    text("- SigLIP: binary classification for (text, image) - aligned or not?")
    image("images/siglip-code.png", width=500)

    text("Data:")
    text("- WebLI dataset: O(billion) (image, text) pairs "), link("https://arxiv.org/pdf/2209.06794")
    text("- Scraped from the Internet")
    text("- Used automatic OCR to extract text from images")
    text("- Keep 10% highest quality")
    text("- Supports 100 languages")

    text("Efficiency:")
    text("- CLIP: 10 days on 256 TPUv3")
    text("- SigLIP: 5 days on 32 TPUv4 (lower FLOP/s than TPUv3) - much faster!")
    image("images/siglip-parallelism.png", width=800)

    text("Batch size:")
    text("- Decouple batch size from loss")
    text("- Better than CLIP for <16K batch sizes")
    text("- Go up to 1M batch size, but 32K is enough")


def llava():
    text("LLaVA (Large Language and Vision Assistant) "), link("https://arxiv.org/abs/2304.08485")

    text("Vision encoder: CLIP")
    text("Text decoder: Vicuna (LLaMA fine-tuned on ShareGPT conversations) "), post_link("https://www.lmsys.org/blog/2023-03-30-vicuna/")

    text("Data:")
    text("- MS COCO has images annotated with bounding boxes and Mechanical Turk captions")
    text("- Prompt GPT-4 with captions or detected objects and generate questions or conversations")
    text("- Pair generations with original images")
    text("- 158K examples")
    image("images/llava-gen.png", width=600)

    text("Model:")
    text("- Encode images with CLIP (ViT-L/14)")
    text("- Linear projection (W) into embedding space (Flamingo and Q-former are more complex)")
    image("images/llava-architecture.png", width=600)

    text("Training:")
    text("- Stage 1 (alignment): freeze vision encoder and language model, only train W")
    text("- Stage 2 (fine-tuning): freeze vision encoder and train W and language model")
    image("images/llava-example.png", width=600)


def llava_onevision():
    text("LLaVA OneVision "), link("https://arxiv.org/pdf/2408.03326")
    text("- Latest version in the LLaVA series (after LLaVA 1.5, LLaVA-Next)")
    text("- Handle multiple images, video")

    image("images/llava-onevision.png", width=600)
    text("- Vision encoder: SigLIP (use grid features before and after last Transformer layer)")
    text("- Text decoder: Qwen-2 72B")
    text("- Projector: 2-layer MLP")

    text("Data processing:")
    text("- Preserving high resolution is important (e.g., for OCR)")
    text("- CLIP resizes and crops to 336x336, which loses information")
    text("- Solution: AnyRes, introduced in LLaVA 1.5 "), link(title="paper", url="https://static.hliu.cc/files/llava/improved_llava.pdf")
    text("- Break up image into a x b pieces (matching resolution of vision encoder), encode, concatenate")
    text("- If too many tokens (original image is too high resolution), then use bilinear interpolation")
    image("images/llava-onevision-anyres.png", width=600)
    text("Handle 3 types of input (single image, multiple images, video):")
    text("- Goal: make all of the modalities produce roughly the same length")
    image("images/llava-onevision-modalities.png", width=600)
    text("- Single image: use higher resolution")
    text("- Multiple images: use base resolution for each image")
    text("- Video: use lower resolution for each frame")

    text("Data:")
    text("- Philosophy: quality over quantity")
    image("images/llava-onevision-data-1.png", width=700)
    image("images/llava-onevision-data-2.png", width=700)

    text("Training:")
    text("- Philosophy: easier to harder")
    image("images/llava-onevision-training.png", width=700)

    text("Transfer between modalities:")
    text("- Single image data for diagrams and charts, but generalize to multi-image")
    image("images/llava-onevision-transfer-s1.png", width=600)
    text("- OCR on single image data, relational reasoning from multi-image data, generalize to GUI-based agents")
    image("images/llava-onevision-transfer-s2.png", width=600)
    text("- Visual prompting (circle) in single images, generalize to videos")
    image("images/llava-onevision-transfer-s8.png", width=600)

    text("Summary:")
    text("- Standard VLM template: vision encoder + projector + LM")
    text("- Most work goes into data curation (heavy on synthesized, task-specific data)")
    text("- Open-source (released model weights and data)")


def qwen_vl():
    text("Qwen-VL "), link("https://arxiv.org/abs/2308.12966")

    text("Architecture:")
    text("- Vision encoder: OpenCLIP's ViT-bigC (14x14 patches) "), link("https://arxiv.org/abs/2212.07143")
    text("- Adaptor: one layer cross-attention, incorporate 2D positional encodings, maps to fixed length of 256")
    text("- Special tokens: <img>, <box>, <ref>")

    text("Training:")
    image("images/qwen-vl-stages.png", width=700)
    text("- Stage 1: large-scale low quality data; freeze LM, train vision encoder + adaptor")
    image("images/qwen-vl-stage1.png", width=400)
    text("- Stage 2: higher quality task-specific data, increase resolution; train all parameters")
    image("images/qwen-vl-stage2.png", width=400)
    text("- Stage 3: instruction tuning data; freeze visual encoder, train adaptor + LM")

    image("images/qwen-vl-examples.png", width=600)


def qwen2_vl():
    text("Qwen2-VL "), link("https://arxiv.org/abs/2409.12191")

    text("Visual encoder: larger ViT (675M)")
    image("images/qwen2-vl-architecture.png", width=700)
    text("- Key: dynamic resolution to handle varying resolutions")
    text("- Each 224 x 224 patch encoded with ViT/14, compress every 2x2 => 66 tokens")
    text("- Video: sample 2 frames/sec, max 16384 tokens")

    text("Multimodal Rotary Position Embedding (MRoPE):")
    image("images/qwen2-vl-mrope.png", width=600)
    
    text("Initialize LM with Qwen2 and vision encoder from DFN "), link("https://arxiv.org/abs/2309.17425")
    text("Training (similar to Qwen-VL):")
    text("- Stage 1: train only visual encoder")
    text("- Stage 2: train all parameters")
    text("- Stage 3: train language model on instruction following datasets")

    text("Many capabilities:")
    image("images/qwen2-vl-capabilities.png", width=700)


def qwen3_vl():
    text("Qwen3-VL "), link("https://arxiv.org/abs/2511.21631")
    image("images/qwen3-vl.png", width=700)

    text("Language model:")
    text("- Qwen-3 models (dense and MoE models up to 235B-A22B)")
    text("- Long context understanding (256K)")

    text("Vision encoder:")
    text("- SigLIP-2 (same architecture as SigLIP) "), link("https://arxiv.org/pdf/2502.14786")
    text("- Interleaved MRoPE: distribute all axes (temporal, width, height) to low- and high-frequency bands")
    text("... [t w h t w h t w h t w h] rather than [t t t t w w w w h h h h]")
    text("- Add explicit video timestamps (as separate tokens rather in positional embeddings)")
    text("- Square-root-normalized per-token loss: balance text and multimodal data (video examples are long, don't want to dominate)")

    text("Adapter:")
    text("- DeepStack: cross-layer fusion to inject visual information into multiple layers "), link("https://arxiv.org/abs/2406.04334")

    text("Training:")
    text("- Pre-training has 4 stages (train adapter, train all parameters on 8K, 32K, 256K lengths)")
    image("images/qwen3-vl-pretraining.png", width=600)
    text("- Post-training: SFT on long CoT data, knowledge distillation, RL")

    image("images/qwen3-vl-results.png", width=600)

    text("Summary:")
    text("- SOTA performance")
    text("- Lots of data work, but not many details")
    text("- Minor but potentially important architectural improvements")
    text("- Scale up")


def chameleon():
    text("Chameleon "), link("https://arxiv.org/pdf/2405.09818")

    text("So far: VLMs encode images (via CLIP or SigLIP), inject into LM")
    text("Disadvantage: can't generate images (need diffusion)")

    text("Chameleon: map everything into discrete tokens")
    text("Advantage: can analyze and generate images in a uniform way")
    image("images/chameleon.png", width=600)
    image("images/chameleon-example.png", width=600)

    text("Vision encoder "), link("https://arxiv.org/pdf/2203.13131")
    text("- Key difference: encoder needs to map to discrete tokens (so we can generate them)")
    text("- VQ-VAE (Vector Quantized Variational Autoencoder) "), link("https://arxiv.org/pdf/1711.00937")
    text("- Idea: map image to a discrete codebook, decode back to image and minimize reconstruction loss")
    image("images/vq-vae.png", width=600)
    text("- Encodes 512 x 512 image into 1024 tokens (codebook of size 8192)")
    text("- Train a new BPE tokenizer")

    text("Training:")
    text("- Stage 1 (80%): large-scale, unsupervised (2.9T text tokens, 1.5T text/image tokens, 400B text/image interleaved tokens)")
    text("- Stage 2 (20%): 50% of stage 1 data, 50% of high quality data")
    
    text("Training stability")
    text("- Text tokens have low entropy, image tokens have high entropy, leads to norm growth, logit drift problem")
    text("- Fixes: QK norm, z-loss regularization")

    text("Summary:")
    text("- Elegant (just autoregressive modeling of discrete tokens)")
    text("- Not as performant (discretization loses information - think OCR)")
    text("- Training with multiple modalities is tricky")
    

if __name__ == "__main__":
    main()
