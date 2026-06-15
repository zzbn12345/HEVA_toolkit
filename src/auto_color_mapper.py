#!/usr/bin/env python3
"""
Automated Color-to-Value Mapping Script.
Uses Ollama (defaulting to Llama 3.1 8B) to analyze highlight groups semantically
and auto-classify highlight colors to heritage/urban planning values.

Requires Ollama running locally (http://localhost:11434).
"""

import os
import sys
import argparse
import json
import urllib.request
import urllib.error
import re

from pdf_extractor import extract_colored_highlights
from docx_extractor import extract_docx_highlights

# Standard/Default categories with descriptions
DEFAULT_CATEGORIES_WITH_DESC = {
    "social": "Community, social life, local people, public space, interaction, social activities, recreation, identity, sense of place. Examples: housing, community center, library, resident.",
    "economic": "Commercial, trade, tourism, cost, value, market, finances, business, industry, economic growth. Examples: too expensive, infrastructure, shops, harbor, business.",
    "political": "Policies, planning, rules, laws, government, administration, master plans, regulations, decisions, awareness, management, defense, security, fortifications, military control. Examples: master plan, municipality, policy, code, bastion, rampart, fort, defense.",
    "historic": "History, heritage, historic buildings, historical development, chronology, events, figures, memory. Examples: monument, heritage, historic building, historical event, historical period, century.",
    "aesthetical": "Beauty, architecture, views, style, design, visual quality, visual harmony, layout, scenery. Examples: attractive, beautiful, architectural style, view.",
    "scientific": "Research, archaeological value, building techniques, materials, educational value, information source, documentation. Examples: archaeological findings, building materials research, documentation.",
    "age": "Age of structures, dating, periods, old/new comparisons, timeframe, longevity. Examples: old building, dating from 1800, modern building, age.",
    "ecological": "Environment, green spaces, trees, plants, nature, conservation, climate, ecology, water, landscape. Examples: green areas, parks, nature, ecological balance."
}

# Normalization mapping for common LLM alternative outputs
NORMALIZATION_MAP = {
    "historical": "historic",
    "aesthetic": "aesthetical",
    "ecology": "ecological",
    "sociale": "social",
    "economical": "economic",
    "politica": "political",
    "science": "scientific",
    "environmental": "ecological",
    "environment": "ecological",
    "societal": "social"
}

def check_model_available(host, model):
    """Checks if the requested model is pulled in Ollama and returns the list of available models."""
    url = f"{host}/api/tags"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
            models = [m.get("name") for m in data.get("models", [])]
            
            # Check for direct or partial match
            found = model in models
            if not found:
                for m in models:
                    if m.startswith(model) or model.startswith(m):
                        found = True
                        break
            return found, models
    except Exception:
        return None, []

def query_ollama(prompt, host="http://localhost:11434", model="llama3.1:8b", available_models=None):
    """Queries local Ollama instance with streaming disabled, temperature=0, and optimized context length."""
    url = f"{host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
            "num_ctx": 32768
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data.get("response")
    except urllib.error.HTTPError as e:
        try:
            err_data = json.loads(e.read().decode("utf-8"))
            err_msg = err_data.get("error", str(e))
        except Exception:
            err_msg = str(e)
            
        print(f"\n[!] Ollama API Error (HTTP {e.code}): {err_msg}")
        if e.code == 404:
            print(f"    The model '{model}' could not be found.")
            if available_models:
                print(f"    Available models in your local Ollama: {available_models}")
                print("    Please run the script specifying one of these using the '-m' flag, e.g.:")
                suggested = available_models[0] if available_models else "llama3:8b"
                print(f"    python auto_color_mapper.py -f <file> -m {suggested}")
            else:
                print("    Please ensure the model name is correct, or pull it using: 'ollama pull <model_name>'")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"\n[!] Connection Error: Unable to reach Ollama at {host}.")
        print("    Please ensure that Ollama is running and accessible.")
        print(f"    Details: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[!] Unexpected Error querying Ollama: {e}")
        sys.exit(1)

def construct_prompt(color_groups, allowed_categories):
    """Builds a detailed classification prompt for Ollama based on allowed categories."""
    formatted_groups = ""
    for color, texts in color_groups.items():
        formatted_groups += f"Color: {color}\n"
        formatted_groups += "Highlighted Texts:\n"
        sample_texts = texts[:25]
        for t in sample_texts:
            formatted_groups += f"  - \"{t}\"\n"
        formatted_groups += "\n"

    category_list_str = ""
    for cat in allowed_categories:
        desc = DEFAULT_CATEGORIES_WITH_DESC.get(cat, "User defined category.")
        category_list_str += f"- {cat}: {desc}\n"

    keys_str = ", ".join(color_groups.keys())

    prompt = f"""You are an expert heritage valuation assistant.
We have extracted highlighted texts from a document, grouped by their raw hexadecimal highlight colors.
Each highlight color corresponds to exactly one of the following heritage/urban planning value categories:
{category_list_str}
Note: Do not use any categories other than the ones listed above.

The highlighted text might be in Dutch or English. Here is a translation and semantic guide:
Dutch examples:
- "sociale woningbouw" / "gemeenschap" / "wonen" -> social or economic
- "te duur" / "infrastructuur" -> economic
- "ambachtelijke bedrijfjes" / "handelswijk" / "pakhuizen" -> economic
- "begrip" / "bestemmingsplan" / "beleid" / "stadsbestuur" / "planning" -> political (since governance, administrative bodies, planning, and regulations represent political actions)
- "monumenten" -> historic
- "historisch" -> age (Important: under this framework, describing a structure/area simply as "historisch", e.g. "historisch gebied", refers to its age and physical longevity, and MUST be mapped to the AGE category, not the HISTORIC category!)
- "aantrekkelijke plek" / "architectuur" -> aesthetical
- "archeologie" / "onderzoek" -> scientific
- "eigentijds" / "oude" -> age
- "water" / "groene zones" -> ecological
- "bastion" / "rampart" / "fort" / "stadsmuren" / "schootsveld" / "military security" -> political (since fortifications, defense ranges, and military infrastructure represent physical control, administrative security, and defense policies)

English examples:
- "housing" / "community" / "resident" / "public space" / "living" -> social (since they represent community life, residents, and public interaction)
- "too expensive" / "harbor" / "shops" / "infrastructure" / "trade" / "tourism" -> economic (since they relate to commercial activity, markets, and financial values)
- "master plan" / "policy" / "regulations" / "bastion" / "rampart" / "fort" / "defense" -> political (since governance, administrative regulations, and military fortifications represent political/governance actions)
- "monument" / "historic building" / "historical development" / "street pattern" / "urban layout" / "traditional building style" -> historic (since historical building types and morphological layout patterns represent heritage structures and historical context)
- "attractive" / "beautiful" / "architectural style" / "view" / "scenery" / "layout of the city" -> aesthetical (since they represent visual design, layout, and aesthetic harmony)
- "archaeological findings" / "materials research" / "documentation" / "education" -> scientific (since they represent research, academic source materials, and investigations)
- "old building" / "modern building" / "dating from 1800" / "longevity" / "historical" / "historic" (when describing structural age or historic areas like "historisch gebied" rather than events/heritage significance) -> age (since they describe the age, chronology, or longevity of structures)
- "green areas" / "parks" / "nature" / "water" / "ecological balance" / "bay" / "peninsula" / "coast" / "terrain" -> ecological (since physical geography, natural landforms, environmental settings, and terrain layout represent ecological characteristics)

Here are the text highlights grouped by their hexadecimal color code:
{formatted_groups}

Return a JSON object with exactly two keys:
1. "reasoning": A JSON object mapping each color to a short explanation of how the highlights relate to the allowed categories.
2. "mapping": A JSON object mapping each color to its best single category from: {", ".join(allowed_categories)}.

You MUST include a key for every color: {keys_str} in both "reasoning" and "mapping". Do not omit any key.
"""
    return prompt

def format_json_output(extracted_data):
    """Formats JSON string with collapsed list fields horizontally onto a single line."""
    json_str = json.dumps(extracted_data, indent=4, ensure_ascii=False)
    for key in ["tokens", "values", "ner_tags"]:
        pattern = rf'("{key}":\s*\[)([^\]]*?)(\])'
        def replacer(match):
            prefix = match.group(1)
            content = match.group(2)
            suffix = match.group(3)
            cleaned_content = re.sub(r'\s*\n\s*', ' ', content)
            cleaned_content = re.sub(r'\s+', ' ', cleaned_content).strip()
            return f"{prefix}{cleaned_content}{suffix}"
        json_str = re.sub(pattern, replacer, json_str, flags=re.DOTALL)
    return json_str

def main():
    parser = argparse.ArgumentParser(description="Auto-map highlight colors to categories using Ollama.")
    parser.add_argument("-f", "--file", required=True, help="Path to the PDF or DOCX file.")
    parser.add_argument("-m", "--model", default="llama3.1:8b", help="Ollama model to use (default: llama3.1:8b).")
    parser.add_argument("-H", "--host", default="http://localhost:11434", help="Ollama host (default: http://localhost:11434).")
    parser.add_argument("-o", "--output", help="Path to write the final extracted JSON. Defaults to <input_base>_extracted.json.")
    parser.add_argument("-c", "--categories", help="Comma-separated list of target categories (e.g. social,economic,political,historic,aesthetical,ecological).")
    
    args = parser.parse_args()
    
    file_path = args.file
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' does not exist.")
        sys.exit(1)
        
    # Determine allowed categories
    if args.categories:
        allowed_categories = [cat.strip().lower() for cat in args.categories.split(",")]
        for cat in allowed_categories:
            if cat not in DEFAULT_CATEGORIES_WITH_DESC:
                print(f"[i] Info: Custom category '{cat}' provided.")
    else:
        allowed_categories = list(DEFAULT_CATEGORIES_WITH_DESC.keys())
        
    print(f"[*] Step 1: Performing raw highlight extraction on: {os.path.basename(file_path)}...")
    
    # Run the raw extraction with empty color mapping to get actual color values
    if file_path.lower().endswith(".pdf"):
        raw_extraction = extract_colored_highlights(file_path, color_label_map={})
    elif file_path.lower().endswith(".docx"):
        raw_extraction = extract_docx_highlights(file_path, color_label_map={})
    else:
        print("Error: Unsupported file format. Please provide a .pdf or .docx file.")
        sys.exit(1)
        
    # Group the highlighted texts and their parent sentences by their raw colors
    color_groups = {}
    color_sentences = {}
    for item in raw_extraction:
        sentence = item.get("sentence", "").strip()
        for entity in item.get("entities", []):
            color = entity["label"]
            text = entity["text"].strip()
            if not text:
                continue
            if color not in color_groups:
                color_groups[color] = set()
            color_groups[color].add(text)
            
            if sentence:
                if color not in color_sentences:
                    color_sentences[color] = set()
                color_sentences[color].add(sentence)
            
    # Convert sets to sorted lists
    for color in color_groups:
        color_groups[color] = sorted(list(color_groups[color]))
    for color in color_sentences:
        color_sentences[color] = sorted(list(color_sentences[color]))
        
    if not color_groups:
        print("[!] No highlighted text detected in the document.")
        sys.exit(0)
        
    print(f"[*] Detected {len(color_groups)} highlight color(s): {list(color_groups.keys())}")
    for color, texts in color_groups.items():
        print(f"    ↳ {color}: {len(texts)} unique text fragment(s)")
        
    # Check Ollama connection and model availability
    print(f"[*] Step 2: Contacting Ollama at {args.host} (using model '{args.model}')...")
    status, available_models = check_model_available(args.host, args.model)
    if status is False:
        print(f"[!] Warning: Model '{args.model}' not found in your local Ollama repository.")
        if available_models:
            print(f"    Available local models: {available_models}")
        print(f"    We will still attempt to run it, but you may need to pull it first using: 'ollama pull {args.model}'")
        
    # Strip/replace U+0372 (Greek Capital Letter Heta 'Ͳ') with a standard hyphen in the text fragments
    cleaned_groups = {}
    for c, texts in color_groups.items():
        cleaned_groups[c] = [t.replace("Ͳ", "-") for t in texts]
        
    print("[*] Sending semantic content groups to LLM for classification (with Chain-of-Thought analysis)...")
    prompt = construct_prompt(cleaned_groups, allowed_categories)
    response_text = query_ollama(prompt, host=args.host, model=args.model, available_models=available_models)
    
    if not response_text:
        print("[!] Failed to get a response from Ollama.")
        sys.exit(1)
        
    try:
        inferred_map_obj = json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"[!] Error decoding JSON response from Ollama: {e}")
        print(f"Raw Response: {response_text}")
        sys.exit(1)
        
    # Print the reasoning explanation from Ollama for the user
    print("\n=== Ollama Reasoning and Analysis ===")
    reasoning = inferred_map_obj.get("reasoning", {})
    for color, explanation in reasoning.items():
        print(f"  {color}: {explanation}")
    print("======================================\n")
        
    inferred_map = inferred_map_obj.get("mapping", {})
        
    # Normalize the output
    final_mapping = {}
    for color in color_groups:
        category = inferred_map.get(color, "")
        if not category:
            # Try key match without '#' if model stripped it
            category = inferred_map.get(color.lstrip('#'), "")
            
        val = category.lower().strip()
        
        # If compound categories returned, parse it
        if "age" in val and "historic" in val:
            if "age" in allowed_categories:
                val = "age"
            else:
                val = "historic"
                
        if val in allowed_categories:
            final_mapping[color] = val
        elif val in NORMALIZATION_MAP and NORMALIZATION_MAP[val] in allowed_categories:
            final_mapping[color] = NORMALIZATION_MAP[val]
            print(f"    [i] Normalized mapping '{category}' -> '{NORMALIZATION_MAP[val]}' for color {color}")
        else:
            # Check if any allowed category is a substring of the returned label
            matched = False
            for allowed in allowed_categories:
                if allowed in val:
                    final_mapping[color] = allowed
                    print(f"    [i] Substring matched mapping '{category}' -> '{allowed}' for color {color}")
                    matched = True
                    break
            if not matched:
                print(f"    [!] Warning: Unknown or disallowed category '{category}' returned for color {color}. Defaulting to raw code.")
                final_mapping[color] = color

    print("=== Inferred Color-to-Value Mapping ===")
    for color, cat in final_mapping.items():
        print(f"  {color}  ==>  {cat}")
    print("========================================")
    
    # Save the mapping block to a sidecar JSON
    base_name, _ = os.path.splitext(file_path)
    map_output_path = f"{base_name}_color_map.json"
    
    # Save a rich mapping containing the category and a sample sentence
    rich_mapping = {}
    for color, category in final_mapping.items():
        sample_sentence = ""
        if color in color_sentences and color_sentences[color]:
            # Try to find a sentence of a reasonable length to avoid single words/numbers, excluding legend lines
            valid_sents = [s for s in color_sentences[color] if len(s) > 25 and "colour coding" not in s.lower()]
            if not valid_sents:
                valid_sents = [s for s in color_sentences[color] if len(s) > 10 and "colour coding" not in s.lower()]
            if not valid_sents:
                valid_sents = [s for s in color_sentences[color] if "colour coding" not in s.lower()]
            if not valid_sents:
                valid_sents = list(color_sentences[color])
            
            if valid_sents:
                # Stable sort alphabetically and take the first one
                sample_sentence = sorted(valid_sents)[0]
        
        color_reasoning = reasoning.get(color, "")
        if not color_reasoning:
            # Handle case where the LLM stripped the # character from the keys
            color_reasoning = reasoning.get(color.lstrip('#'), "")

        rich_mapping[color] = {
            "category": category,
            "reasoning": color_reasoning,
            "sentence": sample_sentence
        }
        
    with open(map_output_path, "w", encoding="utf-8") as mf:
        json.dump(rich_mapping, mf, indent=4)
    print(f"\n[✔] Color map configuration written to: {map_output_path}")
    
    # Step 3: Run extraction again using the inferred color map!
    print(f"[*] Step 3: Regenerating final extraction using inferred color map...")
    if file_path.lower().endswith(".pdf"):
        final_extraction = extract_colored_highlights(file_path, color_label_map=final_mapping)
    else:
        final_extraction = extract_docx_highlights(file_path, color_label_map=final_mapping)
        
    output_path = args.output or f"{base_name}_extracted.json"
    formatted_str = format_json_output(final_extraction)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(formatted_str + "\n")
        
    print(f"[✔] Successfully saved final parsed JSON highlights to: {output_path}")
    print("    Process complete!")

if __name__ == "__main__":
    main()
