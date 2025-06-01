import csv
import os
import re
import spacy # For Named Entity Recognition

# --- Configuration ---
# You can change the default spaCy model here.
# "en_core_web_sm" (small, fast, less accurate)
# "en_core_web_md" (medium, good balance) - Recommended if available
# "en_core_web_lg" (large, most accurate, slowest)
DEFAULT_SPACY_MODEL = "en_core_web_lg"

# --- Helper: Markdown Cleaning (for spaCy input) ---
def clean_text_from_markdown(raw_text):
    """
    Converts Markdown text to a cleaner plain text representation for NLP processing.
    Tries to use the 'markdown' library. Falls back to basic regex cleaning.
    """
    try:
        import markdown # Ensure 'Markdown' library is installed: pip install Markdown
        # Remove HTML comments first as they can interfere
        text_no_comments = re.sub(r'', '', raw_text, flags=re.DOTALL) # Corrected HTML comment removal
        html = markdown.markdown(text_no_comments, extensions=['nl2br', 'extra'])
        
        # Convert <br> and <p> to newlines for better structure
        html = html.replace('<br />', '\n').replace('<br>', '\n').replace('</p>', '</p>\n')
        
        # Strip all other HTML tags
        plain_text = re.sub(r'<[^>]+>', '', html)
        
        # Consolidate whitespace
        plain_text = re.sub(r'[ \t]+', ' ', plain_text)
        plain_text = re.sub(r'\n\s*\n', '\n\n', plain_text) # Consolidate multiple newlines
        
        # Decode HTML entities that might remain (e.g., &amp; -> &)
        try:
            import html as html_parser
            plain_text = html_parser.unescape(plain_text)
        except ImportError:
            print("Warning: 'html' module for unescaping not found. Some HTML entities might remain.")
            
        print("--- Successfully converted Markdown to Plain Text for NER (preview) ---")
        print(plain_text[:350] + ("..." if len(plain_text) > 350 else ""))
        print("-----------------------------------------------------------------------")
        return plain_text.strip()
    except ImportError:
        print("\nWarning: The 'Markdown' library is not installed (run: pip install Markdown).")
        print("         Attempting to treat input as plain text or with very basic regex cleaning.")
        # Basic fallback if markdown library isn't available
        text_no_comments = re.sub(r'', '', raw_text, flags=re.DOTALL) # Corrected HTML comment removal
        plain_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text_no_comments) # Remove links, keep text
        plain_text = re.sub(r'[*#`_~]', '', plain_text) # Remove some common markdown chars
        return plain_text.strip()
    except Exception as e:
        print(f"\nError during Markdown conversion: {e}.")
        print("         Attempting to treat input as plain text.")
        return raw_text.strip() # Fallback to raw text if all else fails

# --- 1. spaCy Entity Extraction Logic ---
def extract_entities_to_csv_data(text_content, spacy_model_name=DEFAULT_SPACY_MODEL):
    """
    Extracts named entities from text content using spaCy and returns a list
    of [placeholder, entity_text] pairs.
    Placeholders are simple (e.g., person_1), not bolded in the returned data.
    """
    try:
        nlp = spacy.load(spacy_model_name)
        print(f"spaCy model '{spacy_model_name}' loaded successfully for entity extraction.")
    except OSError:
        print(f"\nError: spaCy model '{spacy_model_name}' not found. Please download it, e.g.:")
        print(f"  python -m spacy download {spacy_model_name}")
        print(f"You can also try with 'en_core_web_sm'.")
        return None

    cleaned_text = clean_text_from_markdown(text_content)
    if not cleaned_text or not cleaned_text.strip(): # Check if cleaned_text is None or empty string after strip
        print("Error: Text content is empty or became empty after Markdown cleaning for NER.")
        return None
        
    doc = nlp(cleaned_text)
    
    extracted_map = {} # Key: entity_text, Value: base_placeholder
    # Initialize counts for all possible prefixes to avoid KeyError
    counts = {"person": 0, "org": 0, "place": 0, "group": 0, "event": 0, "misc": 0} 
    
    # Customize these labels as needed
    target_labels_map = {
        "PERSON": "person",
        "ORG": "org",
        "GPE": "place",  # Geopolitical entity
        "LOC": "place",  # Location
        "FAC": "place",  # Facility
        "NORP": "group", # Nationalities or religious or political groups
        "EVENT": "event",
        # Add more mappings if desired. Unmapped target labels will use 'misc'.
    }

    print("\nIdentifying Entities with spaCy...")
    for ent in doc.ents:
        entity_text = ent.text.strip()
        # Use 'misc' as a fallback prefix if the label is not in target_labels_map
        label_prefix = target_labels_map.get(ent.label_, "misc") 

        if not entity_text or len(entity_text) < 2: # Skip empty or very short
            continue
        
        # Avoid purely numeric entities unless they are specific types you want (e.g. MONEY, DATE)
        # This list can be expanded based on spaCy's entity types.
        if entity_text.isnumeric() and ent.label_ not in [
            "MONEY", "DATE", "TIME", "PERCENT", "QUANTITY", "ORDINAL", "CARDINAL"
            ]:
            continue

        if entity_text not in extracted_map:
            counts[label_prefix] = counts[label_prefix] + 1 # Increment count for the determined prefix
            base_placeholder = f"{label_prefix}_{counts[label_prefix]}"
            extracted_map[entity_text] = base_placeholder
            print(f"  - Found: '{entity_text}' (Type: {ent.label_}), Assigned Base Placeholder: '{base_placeholder}'")

    if not extracted_map:
        print("No relevant entities found by spaCy based on the criteria.")
        return [] # Return empty list, not None, if no entities found but no error

    # Return data as [base_placeholder, entity_text] for CSV writing
    return [[placeholder, entity] for entity, placeholder in extracted_map.items()]


# --- 2. Anonymization Logic (Real Entities -> Bold Placeholders) ---
def anonymize_text(content, replacements_data, exclusions=None):
    """
    Anonymizes text by replacing real entities with **bolded** placeholders.
    Skips entities found in the exclusions list.
    CSV data: col1=base_placeholder, col2=real_entity_to_find_in_text
    exclusions: A list of lowercase strings to exclude from anonymization.
    """
    if exclusions is None:
        exclusions = []
    
    # Convert exclusions to lowercase for case-insensitive matching
    exclusions_lower = [ex.lower() for ex in exclusions]

    # Sort by length of entity_to_find (descending)
    replacements_data.sort(key=lambda x: len(x[1]), reverse=True)

    print(f"\nPerforming {len(replacements_data)} anonymization replacements (longest entities first)...")
    if exclusions:
        print(f"  Excluding the following terms (case-insensitive): {', '.join(exclusions)}")

    for base_placeholder, entity_to_find in replacements_data:
        original_content_snapshot = content
        
        # Check against exclusions (case-insensitive)
        if entity_to_find.lower() in exclusions_lower:
            print(f"  Skipping anonymization for excluded entity: '{entity_to_find}'")
            continue

        bold_placeholder = f"**{base_placeholder}**" # Apply bolding here
        try:
            # Case-insensitive, whole word/phrase matching
            # Ensure entity_to_find is not empty before creating pattern
            if not entity_to_find:
                print(f"  Skipping rule for placeholder '{base_placeholder}' due to empty 'entity_to_find'.")
                continue
            pattern = r'\b' + re.escape(entity_to_find) + r'\b'
            content = re.sub(pattern, bold_placeholder, content, flags=re.IGNORECASE)
        except re.error as e:
            print(f"  Regex error for entity '{entity_to_find}' (placeholder: '{base_placeholder}'): {e}. Skipping.")
            continue
            
        if content != original_content_snapshot:
            print(f"  Anonymized '{entity_to_find}' with '{bold_placeholder}'.")
    return content

# --- 3. De-anonymization Logic (Bold Placeholders -> Real Entities) ---
class PersonNameReplacer:
    """Helper class for re.sub for PERSON entities during de-anonymization."""
    def __init__(self, full_name_val, last_name_val):
        self.full_name = full_name_val
        self.last_name = last_name_val
        self.count = 0

    def __call__(self, matchobj):
        self.count += 1
        # Always return the full name or last name as is, without adding bolding
        return self.full_name if self.count == 1 else self.last_name

def de_anonymize_text(content, replacements_data):
    """
    De-anonymizes text by replacing **bolded** placeholders with real entities.
    CSV data: col1=base_placeholder, col2=real_entity
    """
    print(f"\nPerforming {len(replacements_data)} de-anonymization replacements...")
    # Sort by length of placeholder (descending) to handle nested placeholders if they were possible (e.g. **org_1_detail** vs **org_1**)
    # Though our generated placeholders are flat. This primarily ensures consistent processing order.
    replacements_data.sort(key=lambda x: len(x[0]), reverse=True)

    for base_placeholder, real_entity in replacements_data:
        if not base_placeholder: continue
        
        original_content_snapshot = content
        # Construct the bolded placeholder pattern to find in the text
        # Escape the base_placeholder in case it has regex special chars (unlikely for generated ones)
        # Ensure base_placeholder is not empty
        if not base_placeholder:
            print(f"  Skipping rule for entity '{real_entity}' due to empty 'base_placeholder'.")
            continue
        bold_placeholder_pattern = r'\*\*' + re.escape(base_placeholder) + r'\*\*'

        try:
            if base_placeholder.startswith("person_"):
                name_parts = real_entity.split()
                last_name = name_parts[-1] if name_parts else real_entity

                if not name_parts or len(name_parts) == 1: # Single word name
                    content = re.sub(bold_placeholder_pattern, real_entity, content, flags=re.IGNORECASE)
                    if content != original_content_snapshot:
                        print(f"  De-anonymized '{base_placeholder}' (Person - single): Replaced with '{real_entity}'.")
                else:
                    replacer_instance = PersonNameReplacer(real_entity, last_name)
                    content = re.sub(bold_placeholder_pattern, replacer_instance, content, flags=re.IGNORECASE)
                    if content != original_content_snapshot:
                        print(f"  De-anonymized '{base_placeholder}' (Person - multi): First as '{real_entity}', then as '{last_name}'.")
            
            elif base_placeholder.startswith(("org_", "place_", "group_", "misc_", "entity_", "fac_", "event_")):
                content = re.sub(bold_placeholder_pattern, real_entity, content, flags=re.IGNORECASE)
                if content != original_content_snapshot:
                    print(f"  De-anonymized '{base_placeholder}' (Org/Place/etc.): Replaced with '{real_entity}'.")
            else:
                print(f"  Warning: Unknown placeholder prefix for '{base_placeholder}'. Applying simple replacement with '{real_entity}'.")
                content = re.sub(bold_placeholder_pattern, real_entity, content, flags=re.IGNORECASE)
        except re.error as e:
            print(f"  Regex error for placeholder '{base_placeholder}' (entity: '{real_entity}'): {e}. Skipping this rule.")
            continue
            
    return content

# --- File Operations & Main Orchestration ---
def read_csv_mapping(csv_path, has_header=False):
    """Reads the CSV mapping file."""
    replacements_map = []
    try:
        with open(csv_path, mode='r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            if has_header:
                try: next(reader); print("CSV header row skipped.")
                except StopIteration: print("Warning: CSV empty after skipping header.")
            for i, row in enumerate(reader):
                rn = (i + 2) if has_header else (i + 1)
                if len(row) >= 2:
                    col1, col2 = row[0].strip(), row[1].strip()
                    if not col1 or not col2: # Both columns must have content
                        print(f"Warning: Skipping row {rn} in CSV (empty placeholder or entity text).")
                        continue
                    replacements_map.append((col1, col2))
                else:
                    print(f"Warning: Skipping row {rn} in CSV (insufficient columns).")
        if not replacements_map:
            print("Warning: No valid data rows found in CSV.")
        return replacements_map
    except FileNotFoundError: print(f"Error: CSV file not found at '{csv_path}'."); return None
    except Exception as e: print(f"Error reading CSV: {e}"); return None

def main():
    print("--- Comprehensive Text Processing Tool ---")
    print("Modes: 1. Generate Entity Map (CSV) | 2. Anonymize Text | 3. De-anonymize Text")
    print("Ensure spaCy and Markdown libraries are installed for full functionality.")
    print("CSV format: Column 1 = base_placeholder, Column 2 = real_entity/full_name.\n")

    # --- Get Operation Mode ---
    operation = ""
    while True:
        mode_input = input("Choose operation (1, 2, or 3): ").strip()
        if mode_input == '1': operation = 'generate_csv'; break
        elif mode_input == '2': operation = 'anonymize'; break
        elif mode_input == '3': operation = 'de_anonymize'; break
        else: print("Invalid choice. Please enter 1, 2, or 3.")
    
    print(f"Selected mode: {operation.replace('_', ' ').title()}")

    # --- Mode 1: Generate Entity Map (CSV) ---
    if operation == 'generate_csv':
        input_text_file = get_file_path("Enter path to the original text/Markdown file to extract entities from: ")
        if not input_text_file: return

        default_csv_name = os.path.join(os.path.dirname(input_text_file) or ".", 
                                        os.path.splitext(os.path.basename(input_text_file))[0] + "_entity_map.csv")
        output_csv_path = input(f"Enter path for the output CSV entity map (default: '{default_csv_name}'): ").strip() or default_csv_name
        
        spacy_model_to_use = input(f"Enter spaCy model name (default: '{DEFAULT_SPACY_MODEL}'): ").strip() or DEFAULT_SPACY_MODEL

        try:
            with open(input_text_file, 'r', encoding='utf-8') as f: text_content = f.read()
            if not text_content.strip(): print("Error: Input file is empty."); return
        except Exception as e: print(f"Error reading input file: {e}"); return

        entity_data_for_csv = extract_entities_to_csv_data(text_content, spacy_model_to_use)
        
        if entity_data_for_csv is None: # Error during extraction (e.g. model not found)
            print("Failed to extract entities (an error occurred).")
            return
        if not entity_data_for_csv: # Empty list returned (no entities found)
             print("No entities extracted to write to CSV based on current criteria.")
             return

        try:
            with open(output_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["base_placeholder", "real_entity_name"]) # CSV Header
                writer.writerows(entity_data_for_csv)
            print(f"\nSuccessfully generated entity map and saved to '{output_csv_path}'")
        except Exception as e:
            print(f"Error writing CSV file: {e}")
        return # End after CSV generation

    # --- Modes 2 & 3: Anonymize or De-anonymize ---
    csv_map_file = get_file_path("Enter path to the CSV mapping file: ")
    if not csv_map_file: return
    
    csv_has_header = input("Does CSV have a header row? (yes/no, default: no): ").strip().lower() in ['yes', 'y']
    
    replacements_map_data = read_csv_mapping(csv_map_file, csv_has_header)
    if replacements_map_data is None or not replacements_map_data: # Check if None (error) or empty list
        print("Could not load or found no valid data in CSV mapping file. Aborting.")
        return

    input_prompt_msg = "Enter path to the original text file (to be anonymized): " if operation == 'anonymize' \
              else "Enter path to the anonymized text file (containing bold placeholders): "
    input_text_file = get_file_path(input_prompt_msg)
    if not input_text_file: return

    # --- Get Exclusions for Anonymization Mode ---
    anonymization_exclusions = []
    if operation == 'anonymize':
        exclusions_input = input("Enter any terms/entities to EXCLUDE from anonymization, separated by commas (e.g., United States, FBI). Press Enter for no exclusions: ").strip()
        if exclusions_input:
            anonymization_exclusions = [term.strip() for term in exclusions_input.split(',')]

    current_content = ""
    try:
        with open(input_text_file, 'r', encoding='utf-8') as f: current_content = f.read()
        if not current_content.strip() and operation == 'de_anonymize':
            print("Input file for de-anonymization is empty. Nothing to process.")
            try:
                with open(get_output_file_path(input_text_file, operation), 'w', encoding='utf-8') as outfile:
                    outfile.write("")
                print("Empty output file written.")
            except Exception as e: print(f"Error writing empty output file: {e}")
            return
    except Exception as e: print(f"Error reading input file: {e}"); return

    processed_content = ""
    if operation == 'anonymize':
        processed_content = anonymize_text(current_content, replacements_map_data, anonymization_exclusions)
    elif operation == 'de_anonymize':
        processed_content = de_anonymize_text(current_content, replacements_map_data)

    # --- Outputting the result ---
    output_file_path = get_output_file_path(input_text_file, operation, True) # Get path with prompt

    try:
        with open(output_file_path, 'w', encoding='utf-8') as outfile:
            outfile.write(processed_content)
        print(f"\nSuccessfully processed text. Output saved to '{output_file_path}'")
    except Exception as e:
        print(f"Error writing output file: {e}")

def get_file_path(prompt_message):
    """Utility to get a valid file path from user."""
    while True:
        file_path = input(prompt_message).strip()
        if not file_path: print("File path cannot be empty."); continue
        # For output files, we don't check os.path.exists here, just get the string.
        # For input files, the check is more critical.
        if "output" not in prompt_message.lower() and "csv entity map" not in prompt_message.lower() : # Heuristic for input files
             if not (os.path.exists(file_path) and os.path.isfile(file_path)):
                print(f"Error: Input file not found or is not a file at '{file_path}'.")
                continue
        return file_path


def get_output_file_path(input_text_file_path, operation_mode, prompt_user=False):
    """Generates a suggested output file path and optionally prompts the user."""
    input_dir, input_filename = os.path.split(input_text_file_path)
    input_name_part, input_ext_part = os.path.splitext(input_filename)
    suggested_output_dir = input_dir if input_dir else "."
    
    suffix_map = {
        'anonymize': "_anonymized_output",
        'de_anonymize': "_de-anonymized_output",
        'generate_csv': "_entity_map.csv" # Though this case is handled separately
    }
    filename_suffix = suffix_map.get(operation_mode, "_processed_output")
    
    # Adjust extension for CSV generation specifically if it were called from here
    if operation_mode == 'generate_csv':
        actual_ext = ".csv"
    else:
        actual_ext = input_ext_part

    suggested_filename = os.path.join(suggested_output_dir, f"{input_name_part}{filename_suffix}{actual_ext}")

    if prompt_user:
        output_prompt = f"Enter path for the output ({operation_mode.replace('_', '-')}) file (default: '{suggested_filename}'): "
        user_path = input(output_prompt).strip()
        return user_path if user_path else suggested_filename
    return suggested_filename


if __name__ == "__main__":
    main()

