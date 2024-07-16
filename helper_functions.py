import torch
from tqdm import tqdm
from lora import LoRALayer

def generate_output(context, model, tokenizer, device, gen_length, num_samples, temp=1, top_k=50):
    """
    Sample model generated text from a given context/input.
    """
    n_context = model.config.get("n_context")
    context = tokenizer.encode(context)
    context = torch.tensor(context, dtype=torch.long).repeat(num_samples, 1)
    context = context.to(model.device)
    context_length = context.size(1)

    pbar = tqdm(total=min(context_length+gen_length, n_context), desc="Generating tokens...")
    with torch.no_grad():
        num_generated = 0
        while (context_length + num_generated < n_context) and (context_length + num_generated < gen_length):
            with torch.autocast(device_type=device, dtype=torch.bfloat16): # autocast to bfloat16 to save memory
                logits, _ = model(context)
            logits = logits[:, -1, :] / temp # adjust logits by temperature
            probs = torch.softmax(logits, dim=1) # to be consistent we softmax first
            probs, idxs = torch.topk(probs, top_k, dim=1) # [B,top_k] matrix
            tokens = torch.gather(idxs, 1, torch.multinomial(probs, num_samples=1)) # gather generated tokens

            context = torch.cat((context, tokens), dim=1) # concat to full context
            num_generated += 1
            pbar.update(1)
    pbar.close()
    return context

def replaceWithLoRA(model, replaced_modules, rank, alpha):
    for name, module in model.named_modules():
        if len(list(module.children())) > 0:
            replaceWithLoRA(module, replaced_modules, rank, alpha)
        elif any(target in name for target in replaced_modules):
            lora_layer = LoRALayer(module.in_features, module.out_features, rank, alpha)
            lora_layer.linear.weight.data = module.weight.data
            parent_module, curr_module = name.rsplit(".", 1)
            setattr(parent_module, curr_module, lora_layer)
    return