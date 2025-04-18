import os
import re
import time
import json
import copy
import types
from os import listdir
from os.path import isfile, join
import argparse
import gradio as gr
import global_vars
from chats import central
from transformers import AutoModelForCausalLM
from miscs.styles import MODEL_SELECTION_CSS
from miscs.js import GET_LOCAL_STORAGE, UPDATE_LEFT_BTNS_STATE, UPDATE_PLACEHOLDERS
from miscs.templates import templates
from utils import get_chat_manager, get_global_context

from pingpong.pingpong import PingPong
from pingpong.gradio import GradioAlpacaChatPPManager
from pingpong.gradio import GradioKoAlpacaChatPPManager
from pingpong.gradio import GradioStableLMChatPPManager
from pingpong.gradio import GradioFlanAlpacaChatPPManager
from pingpong.gradio import GradioOSStableLMChatPPManager
from pingpong.gradio import GradioVicunaChatPPManager
from pingpong.gradio import GradioStableVicunaChatPPManager
from pingpong.gradio import GradioStarChatPPManager
from pingpong.gradio import GradioMPTChatPPManager
from pingpong.gradio import GradioRedPajamaChatPPManager
from pingpong.gradio import GradioBaizeChatPPManager

# no cpu for 
# - falcon families (too slow)

load_mode_list = ["cpu"]
table_data =[]

ex_file = open(r"examples.txt", "r")
examples = ex_file.read().split("\n")
ex_btns = []

chl_file = open(r"channels.txt", "r")
channels = chl_file.read().split("\n")
channel_btns = []

default_ppm = GradioAlpacaChatPPManager()
default_ppm.ctx = "Context at top"
default_ppm.pingpongs = [
    PingPong("user input #1...", "bot response #1..."),
    PingPong("user input #2...", "bot response #2..."),
]
chosen_ppm = copy.deepcopy(default_ppm)

prompt_styles = {
    "Alpaca": default_ppm,
    "Baize": GradioBaizeChatPPManager(),
    "Koalpaca": GradioKoAlpacaChatPPManager(),
    "MPT": GradioMPTChatPPManager(),
    "OpenAssistant StableLM": GradioOSStableLMChatPPManager(),
    "RedPajama": GradioRedPajamaChatPPManager(),
    "StableVicuna": GradioVicunaChatPPManager(),
    "StableLM": GradioStableLMChatPPManager(),
    "StarChat": GradioStarChatPPManager(),
    "Vicuna": GradioVicunaChatPPManager(),
}

response_configs = [
    f"configs/response_configs/{f}"
    for f in listdir("configs/response_configs")
    if isfile(join("configs/response_configs", f))
]

summarization_configs = [
    f"configs/summarization_configs/{f}"
    for f in listdir("configs/summarization_configs")
    if isfile(join("configs/summarization_configs", f))
]

with open("model_cards.json", "r", encoding="utf-8") as file:
    model_info = json.load(file)

for name, attributes in model_info.items():
    thumbnail = attributes["thumb-tiny"]
    parameters = float(attributes["parameters"])
    olld_avg = float(attributes["ollb_average"])
    olld_arc = float(attributes["ollb_arc"])
    ollb_hellaswag = float(attributes["ollb_hellaswag"])
    ollb_mmlu = float(attributes["ollb_mmlu"])
    ollb_truthfulqa = float(attributes["ollb_truthfulqa"])
    
    table_data.append(
        [f"![]({thumbnail})", name, parameters, olld_avg, olld_arc, ollb_hellaswag, ollb_mmlu, ollb_truthfulqa]
    )

table_data.sort(key=lambda elem: elem[3], reverse=True)
    
###

def move_to_second_view_from_tb(tb, evt: gr.SelectData):
    selected_model = tb.iloc[evt.index[0]]['Model']

    info = model_info[selected_model]

    guard_vram = 2 * 1024.
    vram_req_full = int(info["vram(full)"]) + guard_vram
    vram_req_8bit = int(info["vram(8bit)"]) + guard_vram
    vram_req_4bit = int(info["vram(4bit)"]) + guard_vram
    vram_req_gptq = info["vram(gptq)"]
    if vram_req_gptq != "N/A":
        vram_req_gptq = int(vram_req_gptq) + guard_vram
    
    load_mode_list = []
    
    if global_vars.cuda_availability:
        print(f"total vram = {global_vars.available_vrams_mb}")
        print(f"required vram(full={info['vram(full)']}, 8bit={info['vram(8bit)']}, 4bit={info['vram(4bit)']})")
        
        if global_vars.available_vrams_mb >= vram_req_full:
            load_mode_list.append("gpu(half)")
            
        if global_vars.available_vrams_mb >= vram_req_8bit:
            load_mode_list.append("gpu(load_in_8bit)")
            
        if global_vars.available_vrams_mb >= vram_req_4bit:
            load_mode_list.append("gpu(load_in_4bit)")
            
        if vram_req_gptq != "N/A" and global_vars.available_vrams_mb >= vram_req_gptq:
            load_mode_list.append("gpu(gptq)")

    if global_vars.mps_availability:
        load_mode_list.append("apple silicon")
        # load_mode_list.append("apple silicon(gptq)")

    # load_mode_list.append("cpu(gptq)")
    load_mode_list.append("cpu")
    load_mode_list.append("remote(TGI)")
    
    print(info['hub(gptq_base)'])
    vram_req_gptq_in_gb = vram_req_gptq
    if vram_req_gptq != "N/A":
        vram_req_gptq_in_gb = f"{round(vram_req_gptq_in_gb/1024., 1)}GiB"
    
    return (
        gr.update(visible=False),
        gr.update(visible=True),
        info["thumb"],
        f"## {selected_model}",
        f"**Parameters**\n: Approx. {info['parameters']}",
        f"**Hugging Face Hub(base)**\n: {info['hub(base)']}",
        f"**Hugging Face Hub(LoRA)**\n: {info['hub(ckpt)']}",
        f"**Hugging Face Hub(GPTQ)**\n: {info['hub(gptq)']}",
        f"**Hugging Face Hub(GPTQ_BASE)**\n: {info['hub(gptq_base)']}",
        info['desc'],
        f"""**Min VRAM requirements** :
|             half precision            |             load_in_8bit           |              load_in_4bit          |
| ------------------------------------- | ---------------------------------- | ---------------------------------- |
|   {round(vram_req_full/1024., 1)}GiB  | {round(vram_req_8bit/1024., 1)}GiB | {round(vram_req_4bit/1024., 1)}GiB |

|                 GPTQ                  | 
| ------------------------------------- |
|         {vram_req_gptq_in_gb}         |
""",
        info['default_gen_config'],
        info['example1'],
        info['example2'],
        info['example3'],
        info['example4'],
        info['thumb-tiny'],        
        gr.update(choices=load_mode_list, value=load_mode_list[0]),
        "",
    )    

def model_view_toggle(toggler):   
    if toggler == "Icon View(Recent)":
        return (gr.update(visible=True), gr.update(visible=False), gr.update(visible=False), "   ")
    elif toggler == "Icon View(Full)":
        return (gr.update(visible=False), gr.update(visible=True), gr.update(visible=False), "     ")
    else:
        return (gr.update(visible=False), gr.update(visible=False), gr.update(visible=True), "        ")
        

def get_placeholders(text):
    """Returns all substrings in between <placeholder> and </placeholder>."""
    pattern = r"\[([^\]]*)\]"
    matches = re.findall(pattern, text)
    return matches

def fill_up_placeholders(txt):
    placeholders = get_placeholders(txt)
    highlighted_txt = txt

    return (
        gr.update(
            visible=True,
            value=highlighted_txt
        ),
        gr.update(
            visible=True if len(placeholders) >= 1 else False,
            placeholder=placeholders[0] if len(placeholders) >= 1 else ""
        ),
        gr.update(
            visible=True if len(placeholders) >= 2 else False,
            placeholder=placeholders[1] if len(placeholders) >= 2 else ""
        ),
        gr.update(
            visible=True if len(placeholders) >= 3 else False,
            placeholder=placeholders[2] if len(placeholders) >= 3 else ""
        ),
        "" if len(placeholders) >= 1 else txt
    )

def get_final_template(
    txt, placeholder_txt1, placeholder_txt2, placeholder_txt3
):
    placeholders = get_placeholders(txt)
    example_prompt = txt    

    if len(placeholders) >= 1:
        if placeholder_txt1 != "":
            example_prompt = example_prompt.replace(f"[{placeholders[0]}]", placeholder_txt1)
    if len(placeholders) >= 2:
        if placeholder_txt2 != "":
            example_prompt = example_prompt.replace(f"[{placeholders[1]}]", placeholder_txt2)
    if len(placeholders) >= 3:
        if placeholder_txt3 != "":
            example_prompt = example_prompt.replace(f"[{placeholders[2]}]", placeholder_txt3)

    return (
        example_prompt,
        "",
        "",
        ""
    )
    
###

def move_to_model_select_view():
    return (
        "move to model select view",
        gr.update(visible=False),
        gr.update(visible=True),
    )
    
def use_chosen_model():
    try:
        test = global_vars.model
    except AttributeError:
        try:
            test2 = global_vars.remote_addr
            if global_vars.remote_addr.strip() == "":
                raise gr.Error("There is no previously chosen model")
        except AttributeError:
            raise gr.Error("There is no previously chosen model")

    gen_config = global_vars.gen_config
    gen_sum_config = global_vars.gen_config_summarization

    if global_vars.model_type == "custom":
        ppmanager_type = chosen_ppm
    else:
        ppmanager_type = get_chat_manager(global_vars.model_type)

    return (
        "Preparation done!",
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(label=global_vars.model_name),
        {
            "ppmanager_type": ppmanager_type,
            "model_type": global_vars.model_type,
        },
        get_global_context(global_vars.model_type),
        gen_config.temperature,
        gen_config.top_p,
        gen_config.top_k,
        gen_config.repetition_penalty,
        gen_config.max_new_tokens,
        gen_config.num_beams,
        gen_config.use_cache,
        gen_config.do_sample,
        gen_config.eos_token_id,
        gen_config.pad_token_id,
        gen_sum_config.temperature,
        gen_sum_config.top_p,
        gen_sum_config.top_k,
        gen_sum_config.repetition_penalty,
        gen_sum_config.max_new_tokens,
        gen_sum_config.num_beams,
        gen_sum_config.use_cache,
        gen_sum_config.do_sample,
        gen_sum_config.eos_token_id,
        gen_sum_config.pad_token_id,
    )
    
def move_to_byom_view():
    load_mode_list = []
    if global_vars.cuda_availability:
        load_mode_list.extend(["gpu(half)", "gpu(load_in_8bit)", "gpu(load_in_4bit)"])

    if global_vars.mps_availability:
        load_mode_list.append("apple silicon")
        
    load_mode_list.append("cpu")
    
    return (
        "move to the byom view",
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(choices=load_mode_list, value=load_mode_list[0])
    )

def prompt_style_change(key):
    ppm = prompt_styles[key]
    ppm.ctx = "Context at top"
    ppm.pingpongs = [
        PingPong("user input #1...", "bot response #1..."),
        PingPong("user input #2...", "bot response #2..."),
    ]
    chosen_ppm = copy.deepcopy(ppm)
    chosen_ppm.ctx = ""
    chosen_ppm.pingpongs = []
    
    return ppm.build_prompts()

def byom_load(
    base, ckpt, model_cls, tokenizer_cls,
    bos_token_id, eos_token_id, pad_token_id, 
    load_mode,
):  
    # mode_cpu, model_mps, mode_8bit, mode_4bit, mode_full_gpu
    global_vars.initialize_globals_byom(
        base, ckpt, model_cls, tokenizer_cls,
        bos_token_id, eos_token_id, pad_token_id, 
        True if load_mode == "cpu" else False,
        True if load_mode == "apple silicon" else False,
        True if load_mode == "8bit" else False,
        True if load_mode == "4bit" else False,
        True if load_mode == "gpu(half)" else False,
    )
    
    return (
        ""
    )
    
def channel_num(btn_title):
    choice = 0

    for idx, channel in enumerate(channels):
        if channel == btn_title:
            choice = idx

    return choice


def set_chatbot(btn, ld, state):
    choice = channel_num(btn)

    res = [state["ppmanager_type"].from_json(json.dumps(ppm_str)) for ppm_str in ld]
    empty = len(res[choice].pingpongs) == 0
    return (res[choice].build_uis(), choice, gr.update(visible=empty), gr.update(interactive=not empty))


def set_example(btn):
    return btn, gr.update(visible=False)


def set_popup_visibility(ld, example_block):
    return example_block


def move_to_second_view(btn):
    info = model_info[btn]

    guard_vram = 2 * 1024.
    vram_req_full = int(info["vram(full)"]) + guard_vram
    vram_req_8bit = int(info["vram(8bit)"]) + guard_vram
    vram_req_4bit = int(info["vram(4bit)"]) + guard_vram
    vram_req_gptq = info["vram(gptq)"]
    if vram_req_gptq != "N/A":
        vram_req_gptq = int(vram_req_gptq) + guard_vram
    
    load_mode_list = []
    
    if global_vars.cuda_availability:
        print(f"total vram = {global_vars.available_vrams_mb}")
        print(f"required vram(full={info['vram(full)']}, 8bit={info['vram(8bit)']}, 4bit={info['vram(4bit)']})")
        
        if global_vars.available_vrams_mb >= vram_req_full:
            load_mode_list.append("gpu(half)")
            
        if global_vars.available_vrams_mb >= vram_req_8bit:
            load_mode_list.append("gpu(load_in_8bit)")
            
        if global_vars.available_vrams_mb >= vram_req_4bit:
            load_mode_list.append("gpu(load_in_4bit)")
            
        if vram_req_gptq != "N/A" and global_vars.available_vrams_mb >= vram_req_gptq:
            load_mode_list.append("gpu(gptq)")

    if global_vars.mps_availability:
        load_mode_list.append("apple silicon")
        # load_mode_list.append("apple silicon(gptq)")

    # load_mode_list.append("cpu(gptq)")
    load_mode_list.append("cpu")
    load_mode_list.append("remote(TGI)")
    
    print(info['hub(gptq_base)'])
    vram_req_gptq_in_gb = vram_req_gptq
    if vram_req_gptq != "N/A":
        vram_req_gptq_in_gb = f"{round(vram_req_gptq_in_gb/1024., 1)}GiB"
    
    return (
        gr.update(visible=False),
        gr.update(visible=True),
        info["thumb"],
        f"## {btn}",
        f"**Parameters**\n: Approx. {info['parameters']}",
        f"**Hugging Face Hub(base)**\n: {info['hub(base)']}",
        f"**Hugging Face Hub(LoRA)**\n: {info['hub(ckpt)']}",
        f"**Hugging Face Hub(GPTQ)**\n: {info['hub(gptq)']}",
        f"**Hugging Face Hub(GPTQ_BASE)**\n: {info['hub(gptq_base)']}",
        info['desc'],
        f"""**Min VRAM requirements** :
|             half precision            |             load_in_8bit           |              load_in_4bit          |
| ------------------------------------- | ---------------------------------- | ---------------------------------- |
|   {round(vram_req_full/1024., 1)}GiB  | {round(vram_req_8bit/1024., 1)}GiB | {round(vram_req_4bit/1024., 1)}GiB |

|                 GPTQ                  | 
| ------------------------------------- |
|         {vram_req_gptq_in_gb}         |
""",
        info['default_gen_config'],
        info['example1'],
        info['example2'],
        info['example3'],
        info['example4'],
        info['thumb-tiny'],        
        gr.update(choices=load_mode_list, value=load_mode_list[0]),
        "",
    )

def move_to_first_view():
    return (gr.update(visible=True), gr.update(visible=False))

def download_completed(
    model_name,
    model_base,
    model_ckpt,
    model_gptq,
    model_gptq_base,
    gen_config_path,
    gen_config_sum_path,
    load_mode,
    thumbnail_tiny,
    force_download,
    remote_addr,
    remote_port,
    remote_token
):
    global local_files_only
    
    print(f"model_name: {model_name}")
    print(f"model_base: {model_base}")
    
    tmp_args = types.SimpleNamespace()
    tmp_args.model_name = model_name[3:]
    tmp_args.base_url = model_base.split(":")[-1].strip()
    tmp_args.ft_ckpt_url = model_ckpt.split(":")[-1].strip()
    tmp_args.gptq_url = model_gptq.split(":")[-1].strip()
    tmp_args.gptq_base_url = model_gptq_base.split(":")[-1].strip().replace(' ', '')
    tmp_args.gen_config_path = gen_config_path
    tmp_args.gen_config_summarization_path = gen_config_sum_path
    tmp_args.force_download_ckpt = force_download
    tmp_args.thumbnail_tiny = thumbnail_tiny
    
    tmp_args.mode_cpu = True if load_mode == "cpu" else False
    tmp_args.mode_mps = True if load_mode == "apple silicon" else False
    tmp_args.mode_8bit = True if load_mode == "gpu(load_in_8bit)" else False
    tmp_args.mode_4bit = True if load_mode == "gpu(load_in_4bit)" else False
    tmp_args.mode_gptq = True if load_mode == "gpu(gptq)" else False
    tmp_args.mode_mps_gptq = True if load_mode == "apple silicon(gptq)" else False
    tmp_args.mode_cpu_gptq = True if load_mode == "cpu(gptq)" else False
    tmp_args.mode_full_gpu = True if load_mode == "gpu(half)" else False
    tmp_args.mode_remote_tgi = True if load_mode == "remote(TGI)" else False
    tmp_args.local_files_only = local_files_only
    
    tmp_args.remote_addr = remote_addr
    tmp_args.remote_port = remote_port
    tmp_args.remote_token = remote_token
    
    try:
        global_vars.initialize_globals(tmp_args)
    except RuntimeError as e:
        raise gr.Error("GPU memory is not enough to load this model.")
        
    return "Download completed!"

def move_to_third_view():  
    gen_config = global_vars.gen_config
    gen_sum_config = global_vars.gen_config_summarization

    if global_vars.model_type == "custom":
        ppmanager_type = chosen_ppm
    else:
        ppmanager_type = get_chat_manager(global_vars.model_type)

    return (
        "Preparation done!",
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(label=global_vars.model_name),
        {
            "ppmanager_type": ppmanager_type,
            "model_type": global_vars.model_type,
        },
        get_global_context(global_vars.model_type),
        gen_config.temperature,
        gen_config.top_p,
        gen_config.top_k,
        gen_config.repetition_penalty,
        gen_config.max_new_tokens,
        gen_config.num_beams,
        gen_config.use_cache,
        gen_config.do_sample,
        gen_config.eos_token_id,
        gen_config.pad_token_id,
        gen_sum_config.temperature,
        gen_sum_config.top_p,
        gen_sum_config.top_k,
        gen_sum_config.repetition_penalty,
        gen_sum_config.max_new_tokens,
        gen_sum_config.num_beams,
        gen_sum_config.use_cache,
        gen_sum_config.do_sample,
        gen_sum_config.eos_token_id,
        gen_sum_config.pad_token_id,
    )


def toggle_inspector(view_selector):
    if view_selector == "with context inspector":
        return gr.update(visible=True)
    else:
        return gr.update(visible=False)


def reset_chat(idx, ld, state):
    res = [state["ppmanager_type"].from_json(json.dumps(ppm_str)) for ppm_str in ld]
    res[idx].pingpongs = []
        
    return (
        "",
        [],
        str(res),
        gr.update(visible=True),
        gr.update(interactive=False),
    )

def rollback_last(idx, ld, state):
    res = [state["ppmanager_type"].from_json(json.dumps(ppm_str)) for ppm_str in ld]
    last_user_message = res[idx].pingpongs[-1].ping
    res[idx].pingpongs = res[idx].pingpongs[:-1]
    
    return (
        last_user_message,
        res[idx].build_uis(),
        str(res),
        gr.update(interactive=False)
    )

def gradio_main(args):
    global local_files_only
    local_files_only = args.local_files_only
    
    with gr.Blocks(css=MODEL_SELECTION_CSS, theme='gradio/soft') as demo:
        with gr.Column(visible=True, elem_id="landing-container") as landing_view:
            gr.Markdown("# Chat with LLM", elem_classes=["center"])
            with gr.Row(elem_id="landing-container-selection"):
                with gr.Column():
                    gr.Markdown(
                        "This is the landing page of the project, [LLM As Chatbot](https://github.com/deep-diver/LLM-As-Chatbot). "
                        "This appliction is designed for personal use only. A single model will be selected at a time even if you "
                        "open up a new browser or a tab. As an initial choice, please select one of the following menu"
                    )

                    gr.Markdown(
                        "**Bring your own model**: You can chat with arbitrary models. If your own custom model is based on "
                        "🤗 Hugging Face's [transformers](https://huggingface.co/docs/transformers/index) library, you will "
                        "propbably be able to bring it into this application with this menu \n\n"
                        "**Select a model from model pool**: You can chat with one of the popular open source Large Language Model \n\n"
                        "**Use currently selected model**: If you have already selected, but if you came back to this landing page "
                        "accidently, you can directly go back to the chatting mode with this menu"
                    )                    
                    with gr.Row():
                        byom = gr.Button("custom model", elem_id="go-byom-select", elem_classes=["square", "landing-btn"])
                        select_model = gr.Button("model selection", elem_id="go-model-select", elem_classes=["square", "landing-btn"])
                        chosen_model = gr.Button("back to current model", elem_id="go-use-selected-model", elem_classes=["square", "landing-btn"])

                    with gr.Column(elem_id="landing-bottom"):
                        progress_view0 = gr.Textbox(label="Progress", elem_classes=["progress-view"])
                        gr.Markdown("""[project](https://github.com/deep-diver/LLM-As-Chatbot)
    [developer](https://github.com/deep-diver)
    """, elem_classes=["center"])
    
        with gr.Column(visible=False, elem_id="model-selection-container") as model_choice_view:
            gr.Markdown("# Choose a Model", elem_classes=["center"])
            with gr.Row(elem_id="container"):
                with gr.Column():
                    recent_normal_toggler = gr.Radio(
                        choices=["Icon View(Recent)", "Table View", "Icon View(Full)"], value="Icon View(Recent)",
                        label="Model list view modes", info="If you want to explore all models, choose Full Models"
                    )
                    
                    with gr.Column(visible=False) as table_section:
                        gr.Markdown("## 🤗 Open LLM Leaderboard")
                        gr.Markdown(
                            "This view organizes the list of models based on [🤗 Open LLM Leaderboard](https://huggingface.co/spaces/HuggingFaceH4/open_llm_leaderboard). "
                            "Not all models are evaluated on the leader board, so those models' score is indicated with the value `-1`. Also, this application does not "
                            "come with all the open source LLMs on the leader board as well. That is because the actual functionalities are not fully tested, so if you "
                            "want to add more models in this application, please write an [issue](https://github.com/deep-diver/LLM-As-Chatbot/issues) for that."
                        )
                        gr.Markdown(
                            "If you are curious how the models are evaluated and what each score categories are, please find them on [🤗 Open LLM Leaderboard]"
                            "(https://huggingface.co/spaces/HuggingFaceH4/open_llm_leaderboard). For quick reference, please visit [ARC(AI2 Reasoning Challenge)]"
                            "(https://arxiv.org/abs/1803.05457), [HellaSwag](https://arxiv.org/abs/1905.07830), [MMLU(Measuring Massive Multitask Language Understanding)]"
                            "(https://arxiv.org/abs/2009.03300), and [TruthfulQA: Measuring How Models Mimic Human Falsehoods](https://arxiv.org/abs/2109.07958)."
                        )
                        
                        model_table_view = gr.Dataframe(
                            value=table_data,
                            headers=["Icon", "Model", "Params(B)", "Avg.", "ARC", "HellaSwag", "MMLU", "TruthfulQA"],
                            datatype=["markdown", "str", "number", "number", "number", "number", "number", "number"],
                            col_count=(8, "fixed"),
                            row_count=1,
                            #height=1000,
                            interactive=False,
                            wrap=True
                        )
                    
                    with gr.Column() as recent_section:
                        gr.Markdown("## Recent Releases")
                        with gr.Row(elem_classes=["sub-container"]):
                            with gr.Column(min_width=20):
                                mistral_7b_rr = gr.Button("mistral-7b", elem_id="mistral-7b", elem_classes=["square"])
                                gr.Markdown("Mistral (7B)", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                zephyr_7b_rr = gr.Button("zephyr-7b", elem_id="zephyr-7b", elem_classes=["square"])
                                gr.Markdown("Zephyr (7B)", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                mistral_trismegistus_7b_rr = gr.Button("mistral-trismegistus-7b", elem_id="mistral-trismegistus-7b", elem_classes=["square"])
                                gr.Markdown("Mistral Trismegistus (7B)", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                hermes_trismegistus_7b_rr = gr.Button("hermes-trismegistus-7b", elem_id="hermes-trismegistus-7b", elem_classes=["square"])
                                gr.Markdown("Hermes Trismegistus (7B)", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                mistral_openhermes_2_5_7b_rr = gr.Button("mistral-openherems-2-5-7b", elem_id="mistral-openherems-2-5-7b", elem_classes=["square"])
                                gr.Markdown("Mistral OpenHermes 2.5 (7B)", elem_classes=["center"])
                                
                    with gr.Column(visible=False) as full_section:                            
                        gr.Markdown("## ~ 10B Parameters")
                        with gr.Row(elem_classes=["sub-container"]):
                            with gr.Column(min_width=20):
                                t5_vicuna_3b = gr.Button("t5-vicuna-3b", elem_id="t5-vicuna-3b", elem_classes=["square"])
                                gr.Markdown("T5 Vicuna", elem_classes=["center"])

                            with gr.Column(min_width=20, visible=False):
                                flan3b = gr.Button("flan-3b", elem_id="flan-3b", elem_classes=["square"])
                                gr.Markdown("Flan-XL", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                camel5b = gr.Button("camel-5b", elem_id="camel-5b", elem_classes=["square"])
                                gr.Markdown("Camel", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                alpaca_lora7b = gr.Button("alpaca-lora-7b", elem_id="alpaca-lora-7b", elem_classes=["square"])
                                gr.Markdown("Alpaca-LoRA", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                stablelm7b = gr.Button("stablelm-7b", elem_id="stablelm-7b", elem_classes=["square"])
                                gr.Markdown("StableLM", elem_classes=["center"])

                            with gr.Column(min_width=20, visible=False):
                                os_stablelm7b = gr.Button("os-stablelm-7b", elem_id="os-stablelm-7b", elem_classes=["square"])
                                gr.Markdown("OA+StableLM", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                gpt4_alpaca_7b = gr.Button("gpt4-alpaca-7b", elem_id="gpt4-alpaca-7b", elem_classes=["square"])
                                gr.Markdown("GPT4-Alpaca-LoRA", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                mpt_7b = gr.Button("mpt-7b", elem_id="mpt-7b", elem_classes=["square"])
                                gr.Markdown("MPT", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                redpajama_7b = gr.Button("redpajama-7b", elem_id="redpajama-7b", elem_classes=["square"])
                                gr.Markdown("RedPajama", elem_classes=["center"])

                            with gr.Column(min_width=20, visible=False):
                                redpajama_instruct_7b = gr.Button("redpajama-instruct-7b", elem_id="redpajama-instruct-7b", elem_classes=["square"])
                                gr.Markdown("RedPajama Instruct", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                vicuna_7b = gr.Button("vicuna-7b", elem_id="vicuna-7b", elem_classes=["square"])
                                gr.Markdown("Vicuna", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                vicuna_7b_1_3 = gr.Button("vicuna-7b-1-3", elem_id="vicuna-7b-1-3", elem_classes=["square"])
                                gr.Markdown("Vicuna 1.3", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                llama_deus_7b = gr.Button("llama-deus-7b", elem_id="llama-deus-7b",elem_classes=["square"])
                                gr.Markdown("LLaMA Deus", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                evolinstruct_vicuna_7b = gr.Button("evolinstruct-vicuna-7b", elem_id="evolinstruct-vicuna-7b", elem_classes=["square"])
                                gr.Markdown("EvolInstruct Vicuna", elem_classes=["center"])

                            with gr.Column(min_width=20, visible=False):
                                alpacoom_7b = gr.Button("alpacoom-7b", elem_id="alpacoom-7b", elem_classes=["square"])
                                gr.Markdown("Alpacoom", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                baize_7b = gr.Button("baize-7b", elem_id="baize-7b", elem_classes=["square"])
                                gr.Markdown("Baize", elem_classes=["center"])                        

                            with gr.Column(min_width=20):
                                guanaco_7b = gr.Button("guanaco-7b", elem_id="guanaco-7b", elem_classes=["square"])
                                gr.Markdown("Guanaco", elem_classes=["center"])  

                            with gr.Column(min_width=20):
                                falcon_7b = gr.Button("falcon-7b", elem_id="falcon-7b", elem_classes=["square"])
                                gr.Markdown("Falcon", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                wizard_falcon_7b = gr.Button("wizard-falcon-7b", elem_id="wizard-falcon-7b", elem_classes=["square"])
                                gr.Markdown("Wizard Falcon", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                airoboros_7b = gr.Button("airoboros-7b", elem_id="airoboros-7b", elem_classes=["square"])
                                gr.Markdown("Airoboros", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                samantha_7b = gr.Button("samantha-7b", elem_id="samantha-7b", elem_classes=["square"])
                                gr.Markdown("Samantha", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                openllama_7b = gr.Button("openllama-7b", elem_id="openllama-7b", elem_classes=["square"])
                                gr.Markdown("OpenLLaMA", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                orcamini_7b = gr.Button("orcamini-7b", elem_id="orcamini-7b", elem_classes=["square"])
                                gr.Markdown("Orca Mini", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                xgen_7b = gr.Button("xgen-7b", elem_id="xgen-7b", elem_classes=["square"])
                                gr.Markdown("XGen", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                llama2_7b = gr.Button("llama2-7b", elem_id="llama2-7b", elem_classes=["square"])
                                gr.Markdown("LLaMA 2", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                nous_hermes_7b_v2 = gr.Button("nous-hermes-7b-llama2", elem_id="nous-hermes-7b-llama2", elem_classes=["square"])
                                gr.Markdown("Nous Hermes 2", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                codellama_7b = gr.Button("codellama-7b", elem_id="codellama-7b", elem_classes=["square"])
                                gr.Markdown("Code LLaMA", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                mistral_7b = gr.Button("mistral-7b", elem_id="mistral-7b", elem_classes=["square"])
                                gr.Markdown("Mistral", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                zephyr_7b = gr.Button("zephyr-7b", elem_id="zephyr-7b", elem_classes=["square"])
                                gr.Markdown("Zephyr", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                mistral_trismegistus_7b = gr.Button("mistral-trismegistus-7b", elem_id="mistral-trismegistus-7b", elem_classes=["square"])
                                gr.Markdown("Mistral Trismegistus (7B)", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                hermes_trismegistus_7b = gr.Button("hermes-trismegistus-7b", elem_id="hermes-trismegistus-7b", elem_classes=["square"])
                                gr.Markdown("Hermes Trismegistus (7B)", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                mistral_openhermes_2_5_7b = gr.Button("mistral-openherems-2-5-7b", elem_id="mistral-openherems-2-5-7b", elem_classes=["square"])
                                gr.Markdown("Mistral OpenHermes 2.5 (7B)", elem_classes=["center"])

                        gr.Markdown("## ~ 20B Parameters")
                        with gr.Row(elem_classes=["sub-container"]):
                            with gr.Column(min_width=20, visible=False):
                                flan11b = gr.Button("flan-11b", elem_id="flan-11b", elem_classes=["square"])
                                gr.Markdown("Flan-XXL", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                koalpaca = gr.Button("koalpaca", elem_id="koalpaca", elem_classes=["square"])
                                gr.Markdown("koalpaca", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                kullm = gr.Button("kullm", elem_id="kullm", elem_classes=["square"])
                                gr.Markdown("KULLM", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                alpaca_lora13b = gr.Button("alpaca-lora-13b", elem_id="alpaca-lora-13b", elem_classes=["square"])
                                gr.Markdown("Alpaca-LoRA", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                gpt4_alpaca_13b = gr.Button("gpt4-alpaca-13b", elem_id="gpt4-alpaca-13b", elem_classes=["square"])
                                gr.Markdown("GPT4-Alpaca-LoRA", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                stable_vicuna_13b = gr.Button("stable-vicuna-13b", elem_id="stable-vicuna-13b", elem_classes=["square"])
                                gr.Markdown("Stable-Vicuna", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                starchat_15b = gr.Button("starchat-15b", elem_id="starchat-15b", elem_classes=["square"])
                                gr.Markdown("StarChat", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                starchat_beta_15b = gr.Button("starchat-beta-15b", elem_id="starchat-beta-15b", elem_classes=["square"])
                                gr.Markdown("StarChat β", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                vicuna_13b = gr.Button("vicuna-13b", elem_id="vicuna-13b", elem_classes=["square"])
                                gr.Markdown("Vicuna", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                vicuna_13b_1_3 = gr.Button("vicuna-13b-1-3", elem_id="vicuna-13b-1-3", elem_classes=["square"])
                                gr.Markdown("Vicuna 1.3", elem_classes=["center"])                            

                            with gr.Column(min_width=20):
                                evolinstruct_vicuna_13b = gr.Button("evolinstruct-vicuna-13b", elem_id="evolinstruct-vicuna-13b", elem_classes=["square"])
                                gr.Markdown("EvolInstruct Vicuna", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                baize_13b = gr.Button("baize-13b", elem_id="baize-13b", elem_classes=["square"])
                                gr.Markdown("Baize", elem_classes=["center"])                          

                            with gr.Column(min_width=20):
                                guanaco_13b = gr.Button("guanaco-13b", elem_id="guanaco-13b", elem_classes=["square"])
                                gr.Markdown("Guanaco", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                nous_hermes_13b = gr.Button("nous-hermes-13b", elem_id="nous-hermes-13b", elem_classes=["square"])
                                gr.Markdown("Nous Hermes", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                airoboros_13b = gr.Button("airoboros-13b", elem_id="airoboros-13b", elem_classes=["square"])
                                gr.Markdown("Airoboros", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                samantha_13b = gr.Button("samantha-13b", elem_id="samantha-13b", elem_classes=["square"])
                                gr.Markdown("Samantha", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                chronos_13b = gr.Button("chronos-13b", elem_id="chronos-13b", elem_classes=["square"])
                                gr.Markdown("Chronos", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                wizardlm_13b = gr.Button("wizardlm-13b", elem_id="wizardlm-13b", elem_classes=["square"])
                                gr.Markdown("WizardLM", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                wizard_vicuna_13b = gr.Button("wizard-vicuna-13b", elem_id="wizard-vicuna-13b", elem_classes=["square"])
                                gr.Markdown("Wizard Vicuna (Uncensored)", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                wizard_coder_15b = gr.Button("wizard-coder-15b", elem_id="wizard-coder-15b", elem_classes=["square"])
                                gr.Markdown("Wizard Coder", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                openllama_13b = gr.Button("openllama-13b", elem_id="openllama-13b", elem_classes=["square"])
                                gr.Markdown("OpenLLaMA", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                orcamini_13b = gr.Button("orcamini-13b", elem_id="orcamini-13b", elem_classes=["square"])
                                gr.Markdown("Orca Mini", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                llama2_13b = gr.Button("llama2-13b", elem_id="llama2-13b", elem_classes=["square"])
                                gr.Markdown("LLaMA 2", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                nous_hermes_13b_v2 = gr.Button("nous-hermes-13b-llama2", elem_id="nous-hermes-13b-llama2", elem_classes=["square"])
                                gr.Markdown("Nous Hermes 2", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                nous_puffin_13b_v2 = gr.Button("nous-puffin-13b-llama2", elem_id="nous-puffin-13b-llama2", elem_classes=["square"])
                                gr.Markdown("Nous Puffin 2", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                wizardlm_13b_1_2 = gr.Button("wizardlm-13b-1-2", elem_id="wizardlm-13b-1-2", elem_classes=["square"])
                                gr.Markdown("WizardLM 1.2", elem_classes=["center"])
                                
                            with gr.Column(min_width=20):
                                codellama_13b = gr.Button("codellama-13b", elem_id="codellama-13b", elem_classes=["square"])
                                gr.Markdown("Code LLaMA", elem_classes=["center"])

                        gr.Markdown("## ~ 30B Parameters", visible=False)
                        with gr.Row(elem_classes=["sub-container"], visible=False):
                            with gr.Column(min_width=20):
                                camel20b = gr.Button("camel-20b", elem_id="camel-20b", elem_classes=["square"])
                                gr.Markdown("Camel", elem_classes=["center"])

                        gr.Markdown("## ~ 40B Parameters")
                        with gr.Row(elem_classes=["sub-container"]):
                            with gr.Column(min_width=20):
                                guanaco_33b = gr.Button("guanaco-33b", elem_id="guanaco-33b", elem_classes=["square"])
                                gr.Markdown("Guanaco", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                falcon_40b = gr.Button("falcon-40b", elem_id="falcon-40b", elem_classes=["square"])
                                gr.Markdown("Falcon", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                wizard_falcon_40b = gr.Button("wizard-falcon-40b", elem_id="wizard-falcon-40b", elem_classes=["square"])
                                gr.Markdown("Wizard Falcon", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                samantha_33b = gr.Button("samantha-33b", elem_id="samantha-33b", elem_classes=["square"])
                                gr.Markdown("Samantha", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                lazarus_30b = gr.Button("lazarus-30b", elem_id="lazarus-30b", elem_classes=["square"])
                                gr.Markdown("Lazarus", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                chronos_33b = gr.Button("chronos-33b", elem_id="chronos-33b", elem_classes=["square"])
                                gr.Markdown("Chronos", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                wizardlm_30b = gr.Button("wizardlm-30b", elem_id="wizardlm-30b", elem_classes=["square"])
                                gr.Markdown("WizardLM", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                wizard_vicuna_30b = gr.Button("wizard-vicuna-30b", elem_id="wizard-vicuna-30b", elem_classes=["square"])
                                gr.Markdown("Wizard Vicuna (Uncensored)", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                vicuna_33b_1_3 = gr.Button("vicuna-33b-1-3", elem_id="vicuna-33b-1-3", elem_classes=["square"])
                                gr.Markdown("Vicuna 1.3", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                mpt_30b = gr.Button("mpt-30b", elem_id="mpt-30b", elem_classes=["square"])
                                gr.Markdown("MPT", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                upstage_llama_30b = gr.Button("upstage-llama-30b", elem_id="upstage-llama-30b", elem_classes=["square"])
                                gr.Markdown("Upstage LLaMA", elem_classes=["center"])
                                
                            with gr.Column(min_width=20):
                                codellama_34b = gr.Button("codellama-34b", elem_id="codellama-34b", elem_classes=["square"])
                                gr.Markdown("Code LLaMA", elem_classes=["center"])

                        gr.Markdown("## ~ 70B Parameters")
                        with gr.Row(elem_classes=["sub-container"]):
                            with gr.Column(min_width=20):
                                stable_beluga2_70b = gr.Button("stable-beluga2-70b", elem_id="stable-beluga2-70b", elem_classes=["square"])
                                gr.Markdown("Stable Beluga 2", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                upstage_llama2_70b = gr.Button("upstage-llama2-70b", elem_id="upstage-llama2-70b", elem_classes=["square"])
                                gr.Markdown("Upstage2", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                upstage_llama2_70b_2 = gr.Button("upstage-llama2-70b-2", elem_id="upstage-llama2-70b-2", elem_classes=["square"])
                                gr.Markdown("Upstage2 v2", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                platypus2_70b = gr.Button("platypus2-70b", elem_id="platypus2-70b", elem_classes=["square"])
                                gr.Markdown("Platypus2", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                wizardlm_70b = gr.Button("wizardlm-70b", elem_id="wizardlm-70b", elem_classes=["square"])
                                gr.Markdown("WizardLM", elem_classes=["center"])
                                
                            with gr.Column(min_width=20):
                                orcamini_70b = gr.Button("orcamini-70b", elem_id="orcamini-70b", elem_classes=["square"])
                                gr.Markdown("Orca Mini", elem_classes=["center"])
                                
                            with gr.Column(min_width=20):
                                samantha_70b = gr.Button("samantha-70b", elem_id="samantha-70b", elem_classes=["square"])
                                gr.Markdown("Samantha", elem_classes=["center"])
                                
                            with gr.Column(min_width=20):
                                godzilla_70b = gr.Button("godzilla-70b", elem_id="godzilla-70b", elem_classes=["square"])
                                gr.Markdown("GadziLLa", elem_classes=["center"])

                            with gr.Column(min_width=20):
                                nous_hermes_70b = gr.Button("nous-hermes-70b", elem_id="nous-hermes-70b", elem_classes=["square"])
                                gr.Markdown("Nous Hermes 2", elem_classes=["center"])               

                    progress_view = gr.Textbox(label="Progress", elem_classes=["progress-view"])

        with gr.Column(visible=False) as byom_input_view:
            with gr.Column(elem_id="container3"):
                gr.Markdown("# Bring Your Own Model", elem_classes=["center"])
                
                gr.Markdown("### Model configuration")
                byom_base = gr.Textbox(label="Base", placeholder="Enter path or 🤗 hub ID of the base model", interactive=True)
                byom_ckpt = gr.Textbox(label="LoRA ckpt", placeholder="Enter path or 🤗 hub ID of the LoRA checkpoint", interactive=True)
                
                with gr.Accordion("Advanced options", open=False):
                    gr.Markdown("If you leave the below textboxes empty, `transformers.AutoModelForCausalLM` and `transformers.AutoTokenizer` classes will be used by default. If you need any specific class, please type them below.")
                    byom_model_cls = gr.Textbox(label="Base model class", placeholder="Enter base model class", interactive=True)
                    byom_tokenizer_cls = gr.Textbox(label="Base tokenizer class", placeholder="Enter base tokenizer class", interactive=True)

                    with gr.Column():
                        gr.Markdown("If you leave the below textboxes empty, any token ids for bos, eos, and pad will not be specified in `GenerationConfig`. If you think that you need to specify them. please type them below in decimal format.")                        
                        with gr.Row():
                            byom_bos_token_id = gr.Textbox(label="bos_token_id", placeholder="for GenConfig")
                            byom_eos_token_id = gr.Textbox(label="eos_token_id", placeholder="for GenConfig")
                            byom_pad_token_id = gr.Textbox(label="pad_token_id", placeholder="for GenConfig")
                    
                    with gr.Row():
                        byom_load_mode = gr.Radio(
                            load_mode_list,
                            value=load_mode_list[0],
                            label="load mode",
                            elem_classes=["load-mode-selector"]
                        )                        
                
                gr.Markdown("### Prompt configuration")
                prompt_style_selector = gr.Dropdown(
                    label="Prompt style", 
                    interactive=True,
                    choices=list(prompt_styles.keys()), 
                    value="Alpaca"
                )
                with gr.Accordion("Prompt style preview", open=False):
                    prompt_style_previewer = gr.Textbox(
                        label="How prompt is actually structured",
                        lines=16,
                        value=default_ppm.build_prompts())
                    
                with gr.Row():
                    byom_back_btn = gr.Button("Back")
                    byom_confirm_btn = gr.Button("Confirm")

                with gr.Column(elem_classes=["progress-view"]):
                    txt_view3 = gr.Textbox(label="Status")
                    progress_view3 = gr.Textbox(label="Progress")
        
        with gr.Column(visible=False) as model_review_view:
            gr.Markdown("# Confirm the chosen model", elem_classes=["center"])

            with gr.Column(elem_id="container2"):
                gr.Markdown(
                    "Expect that loading time could take very long depending on the model type and the size of the model of your choice. "
                    "Especially, if your model has not been downloaded yet, it will take very long time from downloading to loading up "
                    "the model since each model's size varies between 13GB ~ 150GB. So expect loading time at least 100 seconds, and it "
                    "could take more than several minitues."
                )

                with gr.Row():
                    model_image = gr.Image(None, interactive=False, show_label=False)
                    with gr.Column():
                        model_name = gr.Markdown("**Model name**")
                        model_desc = gr.Markdown("...")                        
                        model_params = gr.Markdown("Parameters\n: ...")             
                        model_base = gr.Markdown("🤗 Hub(base)\n: ...")
                        model_ckpt = gr.Markdown("🤗 Hub(LoRA)\n: ...")
                        model_gptq = gr.Markdown("🤗 Hub(GPTQ)\n: ...")
                        model_gptq_base = gr.Markdown("🤗 Hub(GPTQ_BASE\n: ...")
                        model_vram = gr.Markdown(f"""**Minimal VRAM requirement** :
|          half precision        |        load_in_8bit       |         load_in_4bit      |            GTPQ           |
| ------------------------------ | ------------------------- | ------------------------- | ------------------------- |
|   {round(7830/1024., 1)}GiB    | {round(5224/1024., 1)}GiB | {round(4324/1024., 1)}GiB | {round(4324/1024., 1)}GiB |
""")
                        model_thumbnail_tiny = gr.Textbox("", visible=False)
    
                with gr.Column():
                    gen_config_path = gr.Dropdown(
                        response_configs,
                        value=response_configs[0],
                        interactive=True,
                        label="Gen Config(response)",
                    )
                    gen_config_sum_path = gr.Dropdown(
                        summarization_configs,
                        value=summarization_configs[0],
                        interactive=True,
                        label="Gen Config(summarization)",
                        visible=False,
                    )
                    with gr.Row():
                        load_mode = gr.Radio(
                            load_mode_list,
                            value=load_mode_list[0],
                            label="load mode",
                            elem_classes=["load-mode-selector"]
                        )
                        force_redownload = gr.Checkbox(label="Force Re-download", interactive=False, visible=False)
                        
                    with gr.Column(visible=False) as remote_config_view:
                        remote_addr = gr.Textbox("", label="address", placeholder="to destination")
                        with gr.Row():
                            remote_port = gr.Textbox("", label="port", placeholder="to destination")
                            remote_token = gr.Textbox("", label="token", placeholder="for authorization")

                    with gr.Accordion("Example showcases", open=False):
                        with gr.Tab("Ex1"):
                            example_showcase1 = gr.Chatbot(
                                [("hello", "world"), ("damn", "good")]
                            )
                        with gr.Tab("Ex2"):
                            example_showcase2 = gr.Chatbot(
                                [("hello", "world"), ("damn", "good")]
                            )
                        with gr.Tab("Ex3"):
                            example_showcase3 = gr.Chatbot(
                                [("hello", "world"), ("damn", "good")]
                            )
                        with gr.Tab("Ex4"):
                            example_showcase4 = gr.Chatbot(
                                [("hello", "world"), ("damn", "good")]
                            )
                
                with gr.Row():
                    back_to_model_choose_btn = gr.Button("Back")
                    confirm_btn = gr.Button("Confirm")
    
                with gr.Column(elem_classes=["progress-view"]):
                    txt_view = gr.Textbox(label="Status")
                    progress_view2 = gr.Textbox(label="Progress")
    
        with gr.Column(visible=False) as chat_view:
            idx = gr.State(0)
            chat_state = gr.State()
            local_data = gr.JSON({}, visible=False)
    
            with gr.Row():
                with gr.Column(scale=1, min_width=180):
                    gr.Markdown("GradioChat", elem_id="left-top")
    
                    with gr.Column(elem_id="left-pane"):
                        chat_back_btn = gr.Button("Back", elem_id="chat-back-btn")
                        
                        with gr.Accordion("Histories", elem_id="chat-history-accordion", open=False):
                            channel_btns.append(gr.Button(channels[0], elem_classes=["custom-btn-highlight"]))

                            for channel in channels[1:]:
                                channel_btns.append(gr.Button(channel, elem_classes=["custom-btn"]))
    
                with gr.Column(scale=8, elem_id="right-pane"):
                    with gr.Column(
                        elem_id="initial-popup", visible=False
                    ) as example_block:
                        with gr.Row():
                            with gr.Column(elem_id="initial-popup-left-pane"):
                                gr.Markdown("GradioChat", elem_id="initial-popup-title")
                                gr.Markdown("Making the community's best AI chat models available to everyone.")
                            with gr.Column(elem_id="initial-popup-right-pane"):
                                gr.Markdown("Chat UI is now open sourced on Hugging Face Hub")
                                gr.Markdown("check out the [↗ repository](https://huggingface.co/spaces/chansung/test-multi-conv)")
    
                        with gr.Column(scale=1):
                            gr.Markdown("Examples")
                            with gr.Row():
                                for example in examples:
                                    ex_btns.append(gr.Button(example, elem_classes=["example-btn"]))
    
                    with gr.Column(elem_id="aux-btns-popup", visible=True):
                        with gr.Row():
                            stop = gr.Button("Stop", elem_classes=["aux-btn"])
                            regenerate = gr.Button("Regen", interactive=False, elem_classes=["aux-btn"])
                            clean = gr.Button("Clean", elem_classes=["aux-btn"])
    
                    with gr.Accordion("Context Inspector", elem_id="aux-viewer", open=False):
                        context_inspector = gr.Textbox(
                            "",
                            elem_id="aux-viewer-inspector",
                            label="",
                            lines=30,
                            max_lines=50,
                        )                        
                            
                    chatbot = gr.Chatbot(elem_id='chatbot')
                    instruction_txtbox = gr.Textbox(placeholder="Ask anything", label="", elem_id="prompt-txt")
    
            with gr.Accordion("Example Templates", open=False):
                template_txt = gr.Textbox(visible=False)
                template_md = gr.Markdown(label="Chosen Template", visible=False, elem_classes="template-txt")

                with gr.Row():
                    placeholder_txt1 = gr.Textbox(label="placeholder #1", visible=False, interactive=True)
                    placeholder_txt2 = gr.Textbox(label="placeholder #2", visible=False, interactive=True)
                    placeholder_txt3 = gr.Textbox(label="placeholder #3", visible=False, interactive=True)

                for template in templates:
                    with gr.Tab(template['title']):
                        gr.Examples(
                            template['template'],
                            inputs=[template_txt],
                            outputs=[template_md, placeholder_txt1, placeholder_txt2, placeholder_txt3, instruction_txtbox],
                            run_on_click=True,
                            fn=fill_up_placeholders,          
                        )

            with gr.Accordion("Control Panel", open=False) as control_panel:
                with gr.Column():
                    with gr.Column():
                        gr.Markdown("#### Global context")
                        with gr.Accordion("global context will persist during conversation, and it is placed at the top of the prompt", open=False):
                            global_context = gr.Textbox(
                                "global context",
                                lines=5,
                                max_lines=10,
                                interactive=True,
                                elem_id="global-context"
                            )
                        
                        gr.Markdown("#### Internet search")
                        with gr.Row():
                            internet_option = gr.Radio(choices=["on", "off"], value="off", label="mode")
                            serper_api_key = gr.Textbox(
                                value= "" if args.serper_api_key is None else args.serper_api_key,
                                placeholder="Get one by visiting serper.dev", 
                                label="Serper api key"
                            )
                        
                        gr.Markdown("#### GenConfig for **response** text generation")
                        with gr.Row():
                            res_temp = gr.Slider(0.0, 2.0, 0, step=0.1, label="temp", interactive=True)
                            res_topp = gr.Slider(0.0, 2.0, 0, step=0.1, label="top_p", interactive=True)
                            res_topk = gr.Slider(20, 1000, 0, step=1, label="top_k", interactive=True)
                            res_rpen = gr.Slider(0.0, 2.0, 0, step=0.1, label="rep_penalty", interactive=True)
                            res_mnts = gr.Slider(64, 8192, 0, step=1, label="new_tokens", interactive=True)                            
                            res_beams = gr.Slider(1, 4, 0, step=1, label="beams")
                            res_cache = gr.Radio([True, False], value=0, label="cache", interactive=True)
                            res_sample = gr.Radio([True, False], value=0, label="sample", interactive=True)
                            res_eosid = gr.Number(value=0, visible=False, precision=0)
                            res_padid = gr.Number(value=0, visible=False, precision=0)
    
                    with gr.Column(visible=False):
                        gr.Markdown("#### GenConfig for **summary** text generation")
                        with gr.Row():
                            sum_temp = gr.Slider(0.0, 2.0, 0, step=0.1, label="temp", interactive=True)
                            sum_topp = gr.Slider(0.0, 2.0, 0, step=0.1, label="top_p", interactive=True)
                            sum_topk = gr.Slider(20, 1000, 0, step=1, label="top_k", interactive=True)
                            sum_rpen = gr.Slider(0.0, 2.0, 0, step=0.1, label="rep_penalty", interactive=True)
                            sum_mnts = gr.Slider(64, 8192, 0, step=1, label="new_tokens", interactive=True)
                            sum_beams = gr.Slider(1, 8, 0, step=1, label="beams", interactive=True)
                            sum_cache = gr.Radio([True, False], value=0, label="cache", interactive=True)
                            sum_sample = gr.Radio([True, False], value=0, label="sample", interactive=True)
                            sum_eosid = gr.Number(value=0, visible=False, precision=0)
                            sum_padid = gr.Number(value=0, visible=False, precision=0)
    
                    with gr.Column():
                        gr.Markdown("#### Context managements")
                        with gr.Row():
                            ctx_num_lconv = gr.Slider(2, 10, 3, step=1, label="number of recent talks to keep", interactive=True)
                            ctx_sum_prompt = gr.Textbox(
                                "summarize our conversations. what have we discussed about so far?",
                                label="design a prompt to summarize the conversations",
                                visible=False
                            )

            recent_normal_toggler.change(
                model_view_toggle,
                recent_normal_toggler,
                [recent_section, full_section, table_section, progress_view]
            )
            
            model_table_view.select(
                move_to_second_view_from_tb,
                model_table_view,
                [
                    model_choice_view, model_review_view,
                    model_image, model_name, model_params, model_base, model_ckpt, model_gptq, model_gptq_base,
                    model_desc, model_vram, gen_config_path, 
                    example_showcase1, example_showcase2, example_showcase3, example_showcase4,
                    model_thumbnail_tiny, load_mode, 
                    progress_view
                ]
            )

            btns = [
                t5_vicuna_3b, flan3b, camel5b, alpaca_lora7b, stablelm7b,
                gpt4_alpaca_7b, os_stablelm7b, mpt_7b, redpajama_7b, redpajama_instruct_7b, llama_deus_7b, 
                evolinstruct_vicuna_7b, alpacoom_7b, baize_7b, guanaco_7b, vicuna_7b_1_3,
                falcon_7b, wizard_falcon_7b, airoboros_7b, samantha_7b, openllama_7b, orcamini_7b,
                xgen_7b, llama2_7b, nous_hermes_7b_v2, codellama_7b, mistral_7b, zephyr_7b,
                mistral_trismegistus_7b, hermes_trismegistus_7b, mistral_openhermes_2_5_7b,
                
                flan11b, koalpaca, kullm, alpaca_lora13b, gpt4_alpaca_13b, stable_vicuna_13b,
                starchat_15b, starchat_beta_15b, vicuna_7b, vicuna_13b, evolinstruct_vicuna_13b, 
                baize_13b, guanaco_13b, nous_hermes_13b, airoboros_13b, samantha_13b, chronos_13b,
                wizardlm_13b, wizard_vicuna_13b, wizard_coder_15b, vicuna_13b_1_3, openllama_13b, orcamini_13b,
                llama2_13b, nous_hermes_13b_v2, nous_puffin_13b_v2, wizardlm_13b_1_2, codellama_13b, camel20b,
                
                guanaco_33b, falcon_40b, wizard_falcon_40b, samantha_33b, lazarus_30b, chronos_33b,
                wizardlm_30b, wizard_vicuna_30b, vicuna_33b_1_3, mpt_30b, upstage_llama_30b, codellama_34b,
                
                stable_beluga2_70b, upstage_llama2_70b, upstage_llama2_70b_2, platypus2_70b, wizardlm_70b, orcamini_70b,
                samantha_70b, godzilla_70b, nous_hermes_70b,
                
                mistral_7b_rr, zephyr_7b_rr, mistral_trismegistus_7b_rr, hermes_trismegistus_7b_rr, mistral_openhermes_2_5_7b_rr
            ]
            for btn in btns:
                btn.click(
                    move_to_second_view,
                    btn,
                    [
                        model_choice_view, model_review_view,
                        model_image, model_name, model_params, model_base, model_ckpt, model_gptq, model_gptq_base,
                        model_desc, model_vram, gen_config_path, 
                        example_showcase1, example_showcase2, example_showcase3, example_showcase4,
                        model_thumbnail_tiny, load_mode, 
                        progress_view
                    ]
                )

            load_mode.change(
                lambda mode: gr.update(visible=True) if mode == "remote(TGI)" else gr.update(visible=False),
                load_mode,
                remote_config_view
            )
                
            select_model.click(
                move_to_model_select_view,
                None,
                [progress_view0, landing_view, model_choice_view]
            )
            
            chosen_model.click(
                use_chosen_model,
                None,
                [progress_view0, landing_view, chat_view, chatbot, chat_state, global_context,
                res_temp, res_topp, res_topk, res_rpen, res_mnts, res_beams, res_cache, res_sample, res_eosid, res_padid,
                sum_temp, sum_topp, sum_topk, sum_rpen, sum_mnts, sum_beams, sum_cache, sum_sample, sum_eosid, sum_padid]
            )
          
            byom.click(
                move_to_byom_view,
                None,
                [progress_view0, landing_view, byom_input_view, byom_load_mode]
            )

            byom_back_btn.click(
                move_to_first_view,
                None,
                [landing_view, byom_input_view]
            )

            byom_confirm_btn.click(
                lambda: "Start downloading/loading the model...", None, txt_view3
            ).then(
                byom_load,
                [byom_base, byom_ckpt, byom_model_cls, byom_tokenizer_cls,
                byom_bos_token_id, byom_eos_token_id, byom_pad_token_id, 
                byom_load_mode],
                [progress_view3]
            ).then(
                lambda: "Model is fully loaded...", None, txt_view3
            ).then(
                move_to_third_view,
                None,
                [progress_view3, byom_input_view, chat_view, chatbot, chat_state, global_context,
                res_temp, res_topp, res_topk, res_rpen, res_mnts, res_beams, res_cache, res_sample, res_eosid, res_padid,
                sum_temp, sum_topp, sum_topk, sum_rpen, sum_mnts, sum_beams, sum_cache, sum_sample, sum_eosid, sum_padid]
            )

            prompt_style_selector.change(
                prompt_style_change,
                prompt_style_selector,
                prompt_style_previewer
            )
            
            back_to_model_choose_btn.click(
                move_to_first_view,
                None,
                [model_choice_view, model_review_view]
            )
    
            confirm_btn.click(
                lambda: "Start downloading/loading the model...", None, txt_view
            ).then(
                download_completed,
                [model_name, model_base, model_ckpt, model_gptq, model_gptq_base,
                 gen_config_path, gen_config_sum_path, load_mode, model_thumbnail_tiny, force_redownload,
                 remote_addr, remote_port, remote_token],
                [progress_view2]
            ).then(
                lambda: "Model is fully loaded...", None, txt_view
            ).then(
                lambda: time.sleep(2), None, None
            ).then(
                move_to_third_view,
                None,
                [progress_view2, model_review_view, chat_view, chatbot, chat_state, global_context,
                res_temp, res_topp, res_topk, res_rpen, res_mnts, res_beams, res_cache, res_sample, res_eosid, res_padid,
                sum_temp, sum_topp, sum_topk, sum_rpen, sum_mnts, sum_beams, sum_cache, sum_sample, sum_eosid, sum_padid]
            )
             
            for btn in channel_btns:
                btn.click(
                    set_chatbot,
                    [btn, local_data, chat_state],
                    [chatbot, idx, example_block, regenerate]
                ).then(
                    None, btn, None, 
                    js=UPDATE_LEFT_BTNS_STATE        
                )
            
            for btn in ex_btns:
                btn.click(
                    set_example,
                    [btn],
                    [instruction_txtbox, example_block]  
                )
    
            instruction_txtbox.submit(
                lambda: [
                    gr.update(visible=False),
                    gr.update(interactive=True)
                ],
                None,
                [example_block, regenerate]
            )
            
            send_event = instruction_txtbox.submit(
                central.chat_stream,
                [idx, local_data, instruction_txtbox, chat_state,
                global_context, ctx_num_lconv, ctx_sum_prompt,
                res_temp, res_topp, res_topk, res_rpen, res_mnts, res_beams, res_cache, res_sample, res_eosid, res_padid,
                sum_temp, sum_topp, sum_topk, sum_rpen, sum_mnts, sum_beams, sum_cache, sum_sample, sum_eosid, sum_padid,
                internet_option, serper_api_key],
                [instruction_txtbox, chatbot, context_inspector, local_data],
            )
            
            instruction_txtbox.submit(
                None, local_data, None, 
                js="(v)=>{ setStorage('local_data',v) }"
            )
    
            regenerate.click(
                rollback_last,
                [idx, local_data, chat_state],
                [instruction_txtbox, chatbot, local_data, regenerate]
            ).then(
                central.chat_stream,
                [idx, local_data, instruction_txtbox, chat_state,
                global_context, ctx_num_lconv, ctx_sum_prompt,
                res_temp, res_topp, res_topk, res_rpen, res_mnts, res_beams, res_cache, res_sample, res_eosid, res_padid,
                sum_temp, sum_topp, sum_topk, sum_rpen, sum_mnts, sum_beams, sum_cache, sum_sample, sum_eosid, sum_padid,
                internet_option, serper_api_key],
                [instruction_txtbox, chatbot, context_inspector, local_data],
            ).then(
                lambda: gr.update(interactive=True),
                None,
                regenerate
            ).then(
                None, local_data, None, 
                js="(v)=>{ setStorage('local_data',v) }"  
            )
            
            stop.click(
                None, None, None,
                cancels=[send_event]
            )
    
            clean.click(
                reset_chat,
                [idx, local_data, chat_state],
                [instruction_txtbox, chatbot, local_data, example_block, regenerate]
            ).then(
                None, local_data, None, 
                js="(v)=>{ setStorage('local_data',v) }"
            )

            chat_back_btn.click(
                lambda: [gr.update(visible=False), gr.update(visible=True)],
                None,
                [chat_view, landing_view]
            )
            

            placeholder_txt1.change(
                inputs=[template_txt, placeholder_txt1, placeholder_txt2, placeholder_txt3],
                outputs=[template_md],
                show_progress=False,
                js=UPDATE_PLACEHOLDERS,
                fn=None
            )

            placeholder_txt2.change(
                inputs=[template_txt, placeholder_txt1, placeholder_txt2, placeholder_txt3],
                outputs=[template_md],
                show_progress=False,
                js=UPDATE_PLACEHOLDERS,
                fn=None
            )

            placeholder_txt3.change(
                inputs=[template_txt, placeholder_txt1, placeholder_txt2, placeholder_txt3],
                outputs=[template_md],
                show_progress=False,
                js=UPDATE_PLACEHOLDERS,
                fn=None
            )

            placeholder_txt1.submit(
                inputs=[template_txt, placeholder_txt1, placeholder_txt2, placeholder_txt3],
                outputs=[instruction_txtbox, placeholder_txt1, placeholder_txt2, placeholder_txt3],
                fn=get_final_template
            )

            placeholder_txt2.submit(
                inputs=[template_txt, placeholder_txt1, placeholder_txt2, placeholder_txt3],
                outputs=[instruction_txtbox, placeholder_txt1, placeholder_txt2, placeholder_txt3],
                fn=get_final_template
            )

            placeholder_txt3.submit(
                inputs=[template_txt, placeholder_txt1, placeholder_txt2, placeholder_txt3],
                outputs=[instruction_txtbox, placeholder_txt1, placeholder_txt2, placeholder_txt3],
                fn=get_final_template
            )
          
            demo.load(
              None,
              inputs=None,
              outputs=[chatbot, local_data],
              js=GET_LOCAL_STORAGE,
            ) 
            
    demo.queue().launch(
        server_port=8000, 
        server_name="0.0.0.0", 
        debug=args.debug,
        share=args.share,
        root_path=f"{args.root_path}"
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--root-path', default="")
    parser.add_argument('--local-files-only', default=False, action=argparse.BooleanOptionalAction)
    parser.add_argument('--share', default=False, action=argparse.BooleanOptionalAction)
    parser.add_argument('--debug', default=False, action=argparse.BooleanOptionalAction)
    parser.add_argument('--serper-api-key', default=None, type=str)
    args = parser.parse_args()
    
    gradio_main(args)
