import copy
import json
import os
import time

from create_dummy_models import COMPOSITE_MODELS, create_tiny_models
from huggingface_hub import ModelFilter, hf_api

import transformers
from transformers import AutoFeatureExtractor, AutoImageProcessor, AutoTokenizer
from transformers.image_processing_utils import BaseImageProcessor


def get_all_model_names():
    model_names = set()
    # Each auto modeling files contains multiple mappings. Let's get them in a dynamic way.
    for module_name in ["modeling_auto", "modeling_tf_auto", "modeling_flax_auto"]:
        module = getattr(transformers.models.auto, module_name, None)
        if module is None:
            continue
        # all mappings in a single auto modeling file
        mapping_names = [
            x
            for x in dir(module)
            if x.endswith("_MAPPING_NAMES")
            and (x.startswith("MODEL_") or x.startswith("TF_MODEL_") or x.startswith("FLAX_MODEL_"))
        ]
        for name in mapping_names:
            mapping = getattr(module, name)
            if mapping is not None:
                for v in mapping.values():
                    if isinstance(v, (list, tuple)):
                        model_names.update(v)
                    elif isinstance(v, str):
                        model_names.add(v)

    return sorted(model_names)


def get_tiny_model_names_from_repo():
    # All model names defined in auto mappings
    model_names = set(get_all_model_names())

    with open("tests/utils/tiny_model_summary.json") as fp:
        tiny_model_info = json.load(fp)
    tiny_models_names = set()
    for model_base_name in tiny_model_info:
        tiny_models_names.update(tiny_model_info[model_base_name]["model_classes"])

    # Remove a tiny model name if one of its framework implementation hasn't yet a tiny version on the Hub.
    not_on_hub = model_names.difference(tiny_models_names)
    for model_name in copy.copy(tiny_models_names):
        if not model_name.startswith("TF") and f"TF{model_name}" in not_on_hub:
            tiny_models_names.remove(model_name)
        elif model_name.startswith("TF") and model_name[2:] in not_on_hub:
            tiny_models_names.remove(model_name)

    return sorted(tiny_models_names)


def get_tiny_model_summary_from_hub(output_path):
    special_models = COMPOSITE_MODELS.values()

    # All tiny model base names on Hub
    model_names = get_all_model_names()
    models = hf_api.list_models(
        filter=ModelFilter(
            author="hf-internal-testing",
        )
    )
    _models = set()
    for x in models:
        model = x.modelId
        org, model = model.split("/")
        if not model.startswith("tiny-random-"):
            continue
        model = model.replace("tiny-random-", "")
        if not model[0].isupper():
            continue
        if model not in model_names and model not in special_models:
            continue
        _models.add(model)

    models = sorted(_models)
    # All tiny model names on Hub
    summary = {}
    for model in models:
        repo_id = f"hf-internal-testing/tiny-random-{model}"
        model = model.split("-")[0]
        try:
            repo_info = hf_api.repo_info(repo_id)
            content = {
                "tokenizer_classes": set(),
                "processor_classes": set(),
                "model_classes": set(),
                "sha": repo_info.sha,
            }
        except:
            continue
        try:
            time.sleep(1)
            tokenizer_fast = AutoTokenizer.from_pretrained(repo_id)
            content["tokenizer_classes"].add(tokenizer_fast.__class__.__name__)
        except:
            pass
        try:
            time.sleep(1)
            tokenizer_slow = AutoTokenizer.from_pretrained(repo_id, use_fast=False)
            content["tokenizer_classes"].add(tokenizer_slow.__class__.__name__)
        except:
            pass
        try:
            time.sleep(1)
            img_p = AutoImageProcessor.from_pretrained(repo_id)
            content["processor_classes"].add(img_p.__class__.__name__)
        except:
            pass
        try:
            time.sleep(1)
            feat_p = AutoFeatureExtractor.from_pretrained(repo_id)
            if not isinstance(feat_p, BaseImageProcessor):
                content["processor_classes"].add(feat_p.__class__.__name__)
        except:
            pass
        try:
            time.sleep(1)
            model_class = getattr(transformers, model)
            m = model_class.from_pretrained(repo_id)
            content["model_classes"].add(m.__class__.__name__)
        except:
            pass
        try:
            time.sleep(1)
            model_class = getattr(transformers, f"TF{model}")
            m = model_class.from_pretrained(repo_id)
            content["model_classes"].add(m.__class__.__name__)
        except:
            pass

        content["tokenizer_classes"] = sorted(content["tokenizer_classes"])
        content["processor_classes"] = sorted(content["processor_classes"])
        content["model_classes"] = sorted(content["model_classes"])

        summary[model] = content
        with open(os.path.join(output_path, "hub_tiny_model_summary.json"), "w") as fp:
            json.dump(summary, fp, ensure_ascii=False, indent=4)


def update_tiny_model_summary_file(report_path):
    with open(os.path.join(report_path, "tiny_model_summary.json")) as fp:
        new_data = json.load(fp)
    with open("tests/utils/tiny_model_summary.json") as fp:
        data = json.load(fp)
    for key, value in new_data.items():
        if key not in data:
            data[key] = value
        else:
            for attr in ["tokenizer_classes", "processor_classes", "model_classes"]:
                data[key][attr].extend(value[attr])
            new_sha = value["sha"]
            if new_sha is not None:
                data[key]["sha"] = new_sha

    updated_data = {}
    for key in sorted(data.keys()):
        updated_data[key] = {}
        for attr, value in data[key].items():
            updated_data[key][attr] = sorted(value) if attr != "sha" else value

    with open(os.path.join(report_path, "updated_tiny_model_summary.json"), "w") as fp:
        json.dump(updated_data, fp, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    output_path = "tiny_models"
    all = True
    model_types = None
    models_to_skip = get_tiny_model_names_from_repo()
    no_check = True
    upload = True
    organization = "hf-internal-testing"

    create_tiny_models(
        output_path,
        all,
        model_types,
        models_to_skip,
        no_check,
        upload,
        organization,
        token=os.environ.get("TOKEN", None),
    )

    update_tiny_model_summary_file(report_path=os.path.join(output_path, "reports"))