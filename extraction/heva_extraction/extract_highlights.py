import os
import glob
import json
import re

from extraction.heva_extraction.pdf_extractor import extract_colored_highlights
from extraction.heva_extraction.docx_extractor import extract_docx_highlights

if __name__ == "__main__":
    # 1. Define folder paths relative to the script's parent directory (repository root)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(os.path.dirname(script_dir), "data")
    
    # Auto-create the 'data' directory if it doesn't exist yet
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        print(f"Created a missing '{DATA_DIR}' folder. Drop your PDFs/DOCXs in it and rerun!")
        exit()

    # Find and loop through all PDF and DOCX files inside the /data directory
    pdf_files = [f for f in glob.glob(os.path.join(DATA_DIR, "*.pdf")) if not os.path.basename(f).startswith("~$")]
    docx_files = [f for f in glob.glob(os.path.join(DATA_DIR, "*.docx")) if not os.path.basename(f).startswith("~$")]
    all_files = sorted(pdf_files + docx_files)
    
    if not all_files:
        print(f"No PDF or DOCX files discovered inside the '{DATA_DIR}' directory. Please add files.")
    else:
        print(f"--- Batch Processing Started: Found {len(all_files)} target file(s) ---\n")
        
        for file_path in all_files:
            filename = os.path.basename(file_path)
            print(f"Processing target document: {filename}...")
            
            # Extract data based on file extension
            if file_path.lower().endswith(".pdf"):
                extracted_data = extract_colored_highlights(file_path)
            elif file_path.lower().endswith(".docx"):
                extracted_data = extract_docx_highlights(file_path)
            else:
                continue
            
            # Generate output JSON filename
            output_json_path = os.path.splitext(file_path)[0] + "_extracted.json"
            
            # Format JSON string with direct UTF-8 curly apostrophes and other characters
            json_str = json.dumps(extracted_data, indent=4, ensure_ascii=False)
            
            # Collapse list fields horizontally onto a single line
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
                
            with open(output_json_path, "w", encoding="utf-8") as f:
                f.write(json_str + "\n")
                
            print(f"   ↳ Progress Saved: {output_json_path}\n")
            
        print("--- All Documents Successfully Processed ---")
