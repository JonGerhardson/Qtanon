import csv
import os
import re
import sys # Required for PyQt
import spacy # For Named Entity Recognition
import subprocess # For running spaCy download command
import threading 
import traceback # For detailed error logging

# Attempt to import document processing libraries
try:
    import docx # For .docx files
except ImportError:
    docx = None 
try:
    from odf import text as odf_text, teletype as odf_teletype # For .odt files
    from odf.opendocument import load as odf_load
except ImportError:
    odf_text = None
    odf_teletype = None
    odf_load = None

# --- PyQt6 Imports ---
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QFileDialog, QTextEdit, QTabWidget, QGroupBox,
    QCheckBox, QComboBox, QMessageBox, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer
from PyQt6.QtGui import QPalette, QKeySequence 

# --- Configuration ---
TARGET_LARGE_MODEL = "en_core_web_lg"
FALLBACK_MEDIUM_MODEL = "en_core_web_md"
FALLBACK_SMALL_MODEL = "en_core_web_sm"
DEFAULT_SPACY_MODEL = FALLBACK_MEDIUM_MODEL 

AVAILABLE_SPACY_MODELS = [FALLBACK_SMALL_MODEL, FALLBACK_MEDIUM_MODEL, TARGET_LARGE_MODEL] 

# Supported file types for input (excluding PDF)
SUPPORTED_INPUT_FILE_TYPES = "Text Files (*.txt *.md);;Word Documents (*.docx);;OpenDocument Text (*.odt);;All Files (*)"
# Filter for document types that need special reading logic
RICH_DOCUMENT_EXTENSIONS = ('.docx', '.odt') 

# Define spaCy labels for checkboxes and their display names
SPACY_ENTITY_LABELS_FOR_UI = {
    "PERSON": "Person",
    "ORG": "Organization",
    "GPE": "Geopolitical Entity (Countries, Cities)",
    "LOC": "Location (Non-GPE, e.g., mountains)",
    "FAC": "Facility (Buildings, Airports)",
    "NORP": "Group (Nationalities, Religious/Political)",
    "PRODUCT": "Product",
    "EVENT": "Event",
    "WORK_OF_ART": "Work of Art",
    "DATE": "Date",
    "MONEY": "Money",
    "OTHER_TYPES": "Other (Time, Quantity, Language, etc.)" # Catch-all for UI
}
# Labels that will fall under "OTHER_TYPES" if selected
OTHER_TYPE_SPACY_LABELS = ["TIME", "PERCENT", "QUANTITY", "ORDINAL", "CARDINAL", "LANGUAGE", "LAW"]


# --- Helper: Markdown Cleaning (for spaCy input) ---
def clean_text_from_markdown(raw_text):
    try:
        import markdown 
        # Corrected: Specifically remove HTML comments
        text_no_comments = re.sub(r'', '', raw_text, flags=re.DOTALL) 
        html = markdown.markdown(text_no_comments, extensions=['nl2br', 'extra'])
        html = html.replace('<br />', '\n').replace('<br>', '\n').replace('</p>', '</p>\n')
        plain_text = re.sub(r'<[^>]+>', '', html)
        plain_text = re.sub(r'[ \t]+', ' ', plain_text)
        plain_text = re.sub(r'\n\s*\n', '\n\n', plain_text)
        try:
            import html as html_parser
            plain_text = html_parser.unescape(plain_text)
        except ImportError:
            pass 
        return plain_text.strip()
    except ImportError:
        # Corrected: Specifically remove HTML comments
        text_no_comments = re.sub(r'', '', raw_text, flags=re.DOTALL)
        plain_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text_no_comments)
        plain_text = re.sub(r'[*#`_~]', '', plain_text)
        return plain_text.strip()
    except Exception: 
        return raw_text.strip()

# --- Document Reading Logic ---
def read_document_content(file_path, log_callback=None):
    if log_callback is None: log_callback = print
    _, file_extension = os.path.splitext(file_path)
    file_extension = file_extension.lower()
    content = None

    try:
        if file_extension in ['.txt', '.md']:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            log_callback(f"Read plain text/markdown file: {file_path}")
        elif file_extension == '.docx':
            if docx is None:
                log_callback("ERROR: 'python-docx' library is not installed. Please install it to read .docx files (pip install python-docx).")
                QMessageBox.warning(None, "Library Missing", "The 'python-docx' library is required to read .docx files. Please install it.")
                return None
            doc = docx.Document(file_path)
            full_text = []
            for para in doc.paragraphs:
                full_text.append(para.text)
            content = '\n'.join(full_text)
            log_callback(f"Read .docx file: {file_path}")
        elif file_extension == '.odt':
            if odf_load is None or odf_text is None or odf_teletype is None:
                log_callback("ERROR: 'odfpy' library is not installed. Please install it to read .odt files (pip install odfpy).")
                QMessageBox.warning(None, "Library Missing", "The 'odfpy' library is required to read .odt files. Please install it.")
                return None
            doc = odf_load(file_path)
            texts = []
            for element in doc.getElementsByType(odf_text.P): 
                texts.append(odf_teletype.extractText(element))
            content = '\n'.join(texts)
            log_callback(f"Read .odt file: {file_path}")
        elif file_extension == '.doc':
            log_callback(f"Warning: Direct processing of .doc files is not fully supported. Please convert '{os.path.basename(file_path)}' to .docx, .odt, or .txt for best results.")
            QMessageBox.information(None, "Limited Support", f"Direct reading of .doc files has limited support. Consider converting '{os.path.basename(file_path)}' to .docx or .txt.")
            return None 
        else:
            log_callback(f"Unsupported file type for direct content reading: {file_extension}. Attempting to read as plain text.")
            try: 
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                log_callback(f"Read unknown file type as plain text: {file_path}")
            except Exception as e_txt:
                 log_callback(f"Could not read file '{file_path}' as plain text either: {e_txt}")
                 QMessageBox.warning(None, "File Error", f"Unsupported file type: {file_extension}\nCould not read as plain text.")
                 return None
        return content
    except Exception as e:
        log_callback(f"Error reading document content from '{file_path}': {str(e)}\n{traceback.format_exc()}")
        QMessageBox.critical(None, "File Read Error", f"Could not read file: {file_path}\nError: {e}")
        return None


# --- spaCy Model Management ---
class SpacyModelManager(QObject):
    log_signal = pyqtSignal(str)
    download_finished_signal = pyqtSignal(bool, str) 
    _model_cache = {} 

    @classmethod
    def get_model(cls, model_name, log_callback=None):
        if log_callback is None: log_callback = print
        if model_name not in cls._model_cache or cls._model_cache[model_name] is None: 
            try:
                log_callback(f"Loading spaCy model '{model_name}'...")
                cls._model_cache[model_name] = spacy.load(model_name)
                log_callback(f"Model '{model_name}' loaded and cached.")
            except OSError as e:
                log_callback(f"Error loading spaCy model '{model_name}': {e}. It might not be installed.")
                cls._model_cache[model_name] = None 
                return None
            except Exception as e:
                log_callback(f"An unexpected error occurred loading model '{model_name}': {str(e)}\n{traceback.format_exc()}")
                cls._model_cache[model_name] = None
                return None
        return cls._model_cache.get(model_name)

    @staticmethod
    def is_model_installed_static(model_name):
        try:
            return spacy.util.is_package(model_name)
        except Exception:
            return False

    def is_model_installed(self, model_name): 
        return SpacyModelManager.is_model_installed_static(model_name)

    def download_model_sequence(self, models_to_try):
        if not models_to_try:
            self.log_signal.emit("All model download attempts failed or no models left to try.")
            self.download_finished_signal.emit(False, "None") 
            return

        model_to_download = models_to_try[0]
        remaining_models = models_to_try[1:]
        self.log_signal.emit(f"Attempting to download spaCy model: {model_to_download}...")
        
        self.download_worker = _SpacyDownloadWorker(model_to_download, remaining_models)
        self.download_thread = QThread()
        self.download_worker.moveToThread(self.download_thread)
        self.download_worker.log_signal.connect(self.log_signal)
        self.download_worker.finished_signal.connect(self._handle_download_worker_finished)
        self.download_thread.started.connect(self.download_worker.run)
        self.download_thread.finished.connect(self.download_thread.deleteLater)
        self.download_worker.finished_signal.connect(self.download_thread.quit)
        self.download_worker.finished_signal.connect(self.download_worker.deleteLater)
        self.download_thread.start()

    def _handle_download_worker_finished(self, success, model_name, remaining_models_on_fail):
        if success:
            self.log_signal.emit(f"Model '{model_name}' processed successfully (downloaded or already present).")
            if model_name in SpacyModelManager._model_cache:
                del SpacyModelManager._model_cache[model_name] 
            self.download_finished_signal.emit(True, model_name)
        else:
            self.log_signal.emit(f"Failed to process model '{model_name}'.")
            if remaining_models_on_fail:
                self.log_signal.emit(f"Falling back to try next model: {remaining_models_on_fail[0]}")
                self.download_model_sequence(remaining_models_on_fail)
            else:
                self.log_signal.emit("No fallback models left or download failed for the last attempted model.")
                self.download_finished_signal.emit(False, model_name)

class _SpacyDownloadWorker(QObject):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str, list) 

    def __init__(self, model_name, remaining_models_on_fail):
        super().__init__()
        self.model_name = model_name
        self.remaining_models_on_fail = remaining_models_on_fail
        self._is_running = True

    def run(self):
        if not self._is_running: return
        success = False
        try: 
            python_executable = sys.executable or "python"
            command = [python_executable, "-m", "spacy", "download", self.model_name]
            self.log_signal.emit(f"Executing command: {' '.join(command)}")
            
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creation_flags)
            
            stdout_lines = []
            for line in iter(process.stdout.readline, ''):
                if not self._is_running: 
                    try: process.terminate()
                    except ProcessLookupError: pass 
                    process.wait()
                    break
                stripped_line = line.strip()
                if stripped_line: self.log_signal.emit(f"[spaCy download] {stripped_line}"); stdout_lines.append(stripped_line)
            process.stdout.close()

            stderr_output = process.stderr.read()
            if stderr_output.strip(): self.log_signal.emit(f"[spaCy download stderr] {stderr_output.strip()}")
            process.stderr.close()
            
            return_code = process.wait()

            if not self._is_running: return 

            if return_code == 0:
                self.log_signal.emit(f"Download command for '{self.model_name}' finished.")
                success_indicators = ["download and installation successful", "already installed", "successfully downloaded"]
                QThread.msleep(500) 
                if SpacyModelManager.is_model_installed_static(self.model_name) or \
                   any(indicator in " ".join(stdout_lines).lower() for indicator in success_indicators):
                    self.log_signal.emit(f"Model '{self.model_name}' processed successfully.")
                    success = True
                else:
                    self.log_signal.emit(f"Warning: Model '{self.model_name}' download cmd code 0, but not verified by spaCy. Check logs.")
            else:
                self.log_signal.emit(f"Error downloading '{self.model_name}'. Code: {return_code}")
        except Exception as e:
            self.log_signal.emit(f"Exception during model download '{self.model_name}': {str(e)}\n{traceback.format_exc()}")
        
        if self._is_running:
            self.finished_signal.emit(success, self.model_name, self.remaining_models_on_fail if not success else [])
    
    def stop(self):
        self._is_running = False

# --- 1. spaCy Entity Extraction Logic ---
def extract_entities_to_csv_data(text_content, spacy_model_name=DEFAULT_SPACY_MODEL, selected_spacy_labels=None, log_callback=None):
    if log_callback is None: log_callback = print
    if selected_spacy_labels is None: selected_spacy_labels = ["PERSON"] 

    nlp = SpacyModelManager.get_model(spacy_model_name, log_callback)
    if nlp is None: 
        log_callback(f"Failed to get or load spaCy model '{spacy_model_name}'. Cannot extract entities.")
        return None 
    cleaned_text = clean_text_from_markdown(text_content) 
    if not cleaned_text or not cleaned_text.strip():
        log_callback("Error: Text content is empty or became empty after Markdown cleaning for NER.")
        return None
    doc = nlp(cleaned_text)
    extracted_map = {} 
    counts = {"person": 0, "org": 0, "place": 0, "thing": 0, "misc": 0} 
    
    placeholder_prefix_map = {
        "PERSON": "person", "ORG": "org", "GPE": "place", "LOC": "place",  
        "FAC": "place", "PRODUCT": "thing", "EVENT": "thing", 
        "WORK_OF_ART": "thing", "LAW": "thing", "LANGUAGE": "thing",
    }
    log_callback(f"\nIdentifying Entities with spaCy (Selected types: {', '.join(selected_spacy_labels)})...")
    for ent in doc.ents:
        if ent.label_ not in selected_spacy_labels: 
            if "OTHER_TYPES" in selected_spacy_labels and ent.label_ in OTHER_TYPE_SPACY_LABELS:
                pass 
            else:
                continue

        entity_text = ent.text.strip()
        label_prefix = placeholder_prefix_map.get(ent.label_, "misc") 
                                        
        if not entity_text or len(entity_text) < 2 : continue
        
        if entity_text.isnumeric() and label_prefix in ["person", "org", "place", "thing"]:
            label_prefix = "misc" 

        if entity_text not in extracted_map:
            counts[label_prefix] = counts.get(label_prefix, 0) + 1
            base_placeholder = f"{label_prefix}_{counts[label_prefix]:03d}"
            
            extracted_map[entity_text] = base_placeholder
            log_callback(f"  - Found: '{entity_text}' (Type: {ent.label_}), Placeholder: '{base_placeholder}'")
            
    if not extracted_map: log_callback("No relevant entities found by spaCy based on selected types."); return []
    return [[placeholder, entity] for entity, placeholder in extracted_map.items()]

# --- 2. Anonymization Logic ---
def anonymize_text_logic(content, replacements_data, exclusions=None, log_callback=None):
    if log_callback is None: log_callback = print
    if exclusions is None: exclusions = []
    exclusions_lower = [ex.lower() for ex in exclusions]
    replacements_data.sort(key=lambda x: len(x[1]), reverse=True)
    log_callback(f"\nPerforming {len(replacements_data)} anonymization replacements (longest entities first)...")
    if exclusions: log_callback(f"  Excluding (case-insensitive): {', '.join(exclusions)}")
    for base_placeholder, entity_to_find in replacements_data:
        original_content_snapshot = content
        if entity_to_find.lower() in exclusions_lower:
            log_callback(f"  Skipping excluded entity: '{entity_to_find}'"); continue
        bold_placeholder = f"**{base_placeholder}**"
        try:
            if not entity_to_find: continue
            pattern = r'\b' + re.escape(entity_to_find) + r'\b'
            content = re.sub(pattern, bold_placeholder, content, flags=re.IGNORECASE)
        except re.error as e: log_callback(f"  Regex error for '{entity_to_find}': {str(e)}\n{traceback.format_exc()}"); continue
        if content != original_content_snapshot: log_callback(f"  Anonymized '{entity_to_find}' with '{bold_placeholder}'.")
    return content

# --- 3. De-anonymization Logic ---
class PersonNameReplacer:
    def __init__(self, full_name_val, last_name_val):
        self.full_name = full_name_val; self.last_name = last_name_val; self.count = 0
    def __call__(self, matchobj):
        self.count += 1; return self.full_name if self.count == 1 else self.last_name

def de_anonymize_text_logic(content, replacements_data, log_callback=None):
    if log_callback is None: log_callback = print
    log_callback(f"\nPerforming {len(replacements_data)} de-anonymization replacements...")
    replacements_data.sort(key=lambda x: len(x[0]), reverse=True) 
    for base_placeholder, real_entity in replacements_data:
        if not base_placeholder: continue
        original_content_snapshot = content
        escaped_base = re.escape(base_placeholder)
        bold_placeholder_pattern = r'\*\*' + escaped_base + r'\*\*'
        
        try:
            if base_placeholder.startswith("person_"):
                name_parts = real_entity.split(); last_name = name_parts[-1] if name_parts else real_entity
                if not name_parts or len(name_parts) == 1:
                    content = re.sub(bold_placeholder_pattern, real_entity, content, flags=re.IGNORECASE) 
                    if content != original_content_snapshot: log_callback(f"  De-anonymized '{base_placeholder}' (Person - single) to '{real_entity}'.")
                else:
                    replacer_instance = PersonNameReplacer(real_entity, last_name)
                    content = re.sub(bold_placeholder_pattern, replacer_instance, content, flags=re.IGNORECASE)
                    if content != original_content_snapshot: log_callback(f"  De-anonymized '{base_placeholder}' (Person - multi) to '{real_entity}'/'{last_name}'.")
            elif base_placeholder.startswith(("org_", "place_", "thing_", "misc_", "group_")): 
                content = re.sub(bold_placeholder_pattern, real_entity, content, flags=re.IGNORECASE)
                if content != original_content_snapshot: log_callback(f"  De-anonymized '{base_placeholder}' to '{real_entity}'.")
            else: 
                log_callback(f"  Warning: Unknown placeholder prefix for '{base_placeholder}' during de-anonymization. Applying simple replacement with '{real_entity}'.")
                content = re.sub(bold_placeholder_pattern, real_entity, content, flags=re.IGNORECASE)
        except re.error as e: log_callback(f"  Regex error for placeholder '{base_placeholder}': {str(e)}\n{traceback.format_exc()}"); continue
    return content

# --- FileLineEdit for Drag and Drop ---
class FileLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Drag & Drop file or Browse")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0] 
            if url.isLocalFile():
                self.setText(url.toLocalFile())
            event.acceptProposedAction()
        else:
            event.ignore()

# --- File Operations ---
def read_csv_mapping_for_gui(csv_path, has_header=False, log_callback=None):
    if log_callback is None: log_callback = print
    replacements_map = []
    try:
        with open(csv_path, mode='r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            if has_header:
                try: next(reader); log_callback("CSV header row skipped.")
                except StopIteration: log_callback("Warning: CSV empty after skipping header.")
            for i, row in enumerate(reader):
                rn = (i + 2) if has_header else (i + 1)
                if len(row) >= 2:
                    col1, col2 = row[0].strip(), row[1].strip()
                    if not col1 or not col2: log_callback(f"Warning: Skipping row {rn} in CSV (empty placeholder or entity)."); continue
                    replacements_map.append((col1, col2))
                else: log_callback(f"Warning: Skipping row {rn} in CSV (insufficient columns).")
        if not replacements_map: log_callback("Warning: No valid data rows found in CSV.")
        return replacements_map
    except FileNotFoundError: log_callback(f"Error: CSV file not found at '{csv_path}'."); return None
    except Exception as e: log_callback(f"Error reading CSV: {str(e)}\n{traceback.format_exc()}"); return None

# --- Worker QThread for Long Operations ---
class Worker(QObject): 
    finished = pyqtSignal(object) 
    progress = pyqtSignal(str)   
    def __init__(self, mode, **kwargs): super().__init__(); self.mode = mode; self.kwargs = kwargs; self._is_running = True
    def run(self):
        result = None
        try:
            if not self._is_running: return
            if self.mode == 'generate_csv':
                text_content = self.kwargs['text_content']
                spacy_model = self.kwargs['spacy_model']
                # Corrected: Use 'selected_spacy_labels' as the key from kwargs
                selected_labels_arg = self.kwargs['selected_spacy_labels'] 
                result = extract_entities_to_csv_data(text_content, spacy_model, selected_spacy_labels=selected_labels_arg, log_callback=self.progress.emit)
            elif self.mode == 'anonymize':
                content = self.kwargs['content']; replacements_map = self.kwargs['replacements_map']; exclusions = self.kwargs['exclusions']
                result = anonymize_text_logic(content, replacements_map, exclusions, log_callback=self.progress.emit)
            elif self.mode == 'de_anonymize':
                content = self.kwargs['content']; replacements_map = self.kwargs['replacements_map']
                result = de_anonymize_text_logic(content, replacements_map, log_callback=self.progress.emit)
            if self._is_running: self.finished.emit(result)
        except Exception as e:
            if self._is_running: self.progress.emit(f"Error in worker ({self.mode}): {str(e)}\n{traceback.format_exc()}"); self.finished.emit(None)
    def stop(self): self._is_running = False

# --- Main Application Window ---
class NERAnonymizerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QTAnon - NER Anonymizer/De-Anonymizer Tool v1.6") # Version bump
        self.setGeometry(100, 100, 800, 750) 
        self.worker_thread = None; self.worker_object = None 
        self.spacy_manager = SpacyModelManager()
        self.spacy_manager.log_signal.connect(self.log_message)
        self.spacy_manager.download_finished_signal.connect(self.on_model_download_finished)
        self.gen_csv_entity_type_checkboxes = {} 
        # Store last used paths
        self.last_original_doc_path_for_csv = ""
        self.last_generated_csv_path = ""
        self.init_ui()
        QTimer.singleShot(100, self.check_and_prompt_for_initial_model_setup) 

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget(); # Make tabs an instance variable
        self.tabs.currentChanged.connect(self.on_tab_changed) # Connect signal
        self.tabs.addTab(self.create_generate_csv_tab(), "1. Generate Entity Map (CSV)")
        self.tabs.addTab(self.create_anonymize_tab(), "2. Anonymize Text")
        self.tabs.addTab(self.create_de_anonymize_tab(), "3. De-anonymize Text")
        main_layout.addWidget(self.tabs)
        log_group = QGroupBox("Status Log"); log_layout = QVBoxLayout()
        self.log_text_edit = QTextEdit(); self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        log_layout.addWidget(self.log_text_edit); log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        self.log_message("Application started. Select a mode. Tool will check for spaCy models.")

    def on_tab_changed(self, index):
        """Called when the current tab changes. Auto-populates fields if applicable."""
        current_tab_text = self.tabs.tabText(index)
        if current_tab_text == "2. Anonymize Text":
            if self.last_generated_csv_path and os.path.exists(self.last_generated_csv_path):
                self.anon_csv_map_path.setText(self.last_generated_csv_path)
                self.log_message(f"Auto-filled CSV path for Anonymize tab: {self.last_generated_csv_path}")
            if self.last_original_doc_path_for_csv and os.path.exists(self.last_original_doc_path_for_csv):
                self.anon_input_text_path.setText(self.last_original_doc_path_for_csv)
                self.log_message(f"Auto-filled Original Document path for Anonymize tab: {self.last_original_doc_path_for_csv}")
                # Suggest output name based on this newly set input
                self.suggest_output_filename_direct(
                    os.path.join(os.path.dirname(self.last_original_doc_path_for_csv), 
                                 os.path.splitext(os.path.basename(self.last_original_doc_path_for_csv))[0] + "_anonymized" + 
                                 (".md" if self.last_original_doc_path_for_csv.lower().endswith(".md") else ".txt")),
                    self.anon_output_text_path
                )


        elif current_tab_text == "3. De-anonymize Text":
            if self.last_generated_csv_path and os.path.exists(self.last_generated_csv_path):
                self.deanon_csv_map_path.setText(self.last_generated_csv_path)
                self.log_message(f"Auto-filled CSV path for De-anonymize tab: {self.last_generated_csv_path}")
            # De-anonymize input path is usually the output of anonymization, so not auto-filled from original doc.


    def check_and_prompt_for_initial_model_setup(self):
        if not SpacyModelManager.is_model_installed_static(TARGET_LARGE_MODEL):
            reply = QMessageBox.question(self, "SpaCy Large Model Recommended",
                                         f"The large spaCy model ('{TARGET_LARGE_MODEL}') is recommended for best accuracy and is not found.\n"
                                         "Would you like to attempt to download it now? This may take several minutes.\n"
                                         f"(If this fails, the tool will try '{FALLBACK_MEDIUM_MODEL}', then '{FALLBACK_SMALL_MODEL}'.)",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.Yes) 
            if reply == QMessageBox.StandardButton.Yes:
                self.set_buttons_enabled(False) 
                self.spacy_manager.download_model_sequence([TARGET_LARGE_MODEL, FALLBACK_MEDIUM_MODEL, FALLBACK_SMALL_MODEL])
            else:
                self.log_message(f"User opted not to download '{TARGET_LARGE_MODEL}' automatically. Ensure models are installed or select from list.")
                self.update_model_combo_with_installed_models() 
        else:
            self.log_message(f"SpaCy model '{TARGET_LARGE_MODEL}' is already installed.")
            self.update_model_combo_with_installed_models()


    def on_model_download_finished(self, success, model_name_processed):
        self.set_buttons_enabled(True) 
        self.update_model_combo_with_installed_models() 
        if success:
            QMessageBox.information(self, "Model Processed", f"SpaCy model '{model_name_processed}' is now available.")
            self.gen_csv_spacy_model_combo.setCurrentText(model_name_processed)
        else:
            if model_name_processed != "None": 
                 QMessageBox.warning(self, "Model Issue", f"Could not ensure availability of '{model_name_processed}'. Check logs. Try manual install or select another model.")
            else:
                 QMessageBox.critical(self, "Model Downloads Failed", "All attempts to download spaCy models failed. Please install one manually and restart.")
        self.log_message(f"Model download/check process for '{model_name_processed}' finished. Success: {success}")

    def update_model_combo_with_installed_models(self):
        installed_models = [m for m in AVAILABLE_SPACY_MODELS if SpacyModelManager.is_model_installed_static(m)]
        try:
            all_spacy_models = spacy.util.get_installed_models()
            for m_name in all_spacy_models:
                if m_name.startswith("en_core_web_") and m_name not in installed_models:
                    installed_models.append(m_name)
        except Exception as e:
            self.log_message(f"Could not list all spaCy models: {str(e)}\n{traceback.format_exc()}")

        current_selection = self.gen_csv_spacy_model_combo.currentText()
        self.gen_csv_spacy_model_combo.clear()
        
        if installed_models:
            self.gen_csv_spacy_model_combo.addItems(sorted(list(set(installed_models)))) 
            if current_selection in installed_models: self.gen_csv_spacy_model_combo.setCurrentText(current_selection)
            elif TARGET_LARGE_MODEL in installed_models: self.gen_csv_spacy_model_combo.setCurrentText(TARGET_LARGE_MODEL)
            elif FALLBACK_MEDIUM_MODEL in installed_models: self.gen_csv_spacy_model_combo.setCurrentText(FALLBACK_MEDIUM_MODEL)
            elif FALLBACK_SMALL_MODEL in installed_models: self.gen_csv_spacy_model_combo.setCurrentText(FALLBACK_SMALL_MODEL)
            elif self.gen_csv_spacy_model_combo.count() > 0: self.gen_csv_spacy_model_combo.setCurrentIndex(0)
        else:
            self.log_message("No spaCy English models found installed. Please download one (e.g., en_core_web_md).")
            self.gen_csv_spacy_model_combo.addItem("No models found - Download one")

        for model in AVAILABLE_SPACY_MODELS: 
            if self.gen_csv_spacy_model_combo.findText(model) == -1:
                self.gen_csv_spacy_model_combo.addItem(model)


    def create_file_input_group(self, label_text): 
        group = QHBoxLayout(); label = QLabel(label_text); 
        line_edit = FileLineEdit() 
        browse_button = QPushButton("Browse...")
        group.addWidget(label); group.addWidget(line_edit); group.addWidget(browse_button)
        return group, line_edit, browse_button

    def create_generate_csv_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        input_group, self.gen_csv_input_text_path, btn1 = self.create_file_input_group("Original Text/MD/Docx/Odt File:")
        btn1.clicked.connect(lambda: self.browse_file(self.gen_csv_input_text_path, "Open Document File", file_filter=SUPPORTED_INPUT_FILE_TYPES))
        layout.addLayout(input_group)
        
        output_group, self.gen_csv_output_csv_path, btn2 = self.create_file_input_group("Output CSV Entity Map:")
        btn2.clicked.connect(lambda: self.browse_file(self.gen_csv_output_csv_path, "Save CSV File As", save_mode=True, file_filter="CSV Files (*.csv)"))
        layout.addLayout(output_group)
        
        model_layout = QHBoxLayout(); model_layout.addWidget(QLabel("SpaCy Model:"))
        self.gen_csv_spacy_model_combo = QComboBox(); 
        self.update_model_combo_with_installed_models() 
        self.gen_csv_spacy_model_combo.setEditable(True)
        model_layout.addWidget(self.gen_csv_spacy_model_combo); layout.addLayout(model_layout)

        entity_types_group = QGroupBox("Entity Types to Extract (for CSV Generation)")
        entity_types_layout = QGridLayout() 
        self.gen_csv_entity_type_checkboxes = {} 
        
        row, col = 0, 0
        for spacy_label, display_name in SPACY_ENTITY_LABELS_FOR_UI.items():
            checkbox = QCheckBox(display_name)
            if spacy_label == "PERSON": 
                checkbox.setChecked(True)
            self.gen_csv_entity_type_checkboxes[spacy_label] = checkbox
            entity_types_layout.addWidget(checkbox, row, col)
            col += 1
            if col >= 2: 
                col = 0
                row += 1
        
        entity_types_group.setLayout(entity_types_layout)
        layout.addWidget(entity_types_group)
        
        self.gen_csv_process_button = QPushButton("&Generate Entity Map CSV")
        self.gen_csv_process_button.setShortcut(QKeySequence("Ctrl+G")) 
        self.gen_csv_process_button.clicked.connect(self.run_generate_csv)
        layout.addWidget(self.gen_csv_process_button, alignment=Qt.AlignmentFlag.AlignCenter); layout.addStretch()
        
        QWidget.setTabOrder(self.gen_csv_input_text_path, btn1)
        QWidget.setTabOrder(btn1, self.gen_csv_output_csv_path)
        QWidget.setTabOrder(self.gen_csv_output_csv_path, btn2)
        QWidget.setTabOrder(btn2, self.gen_csv_spacy_model_combo)
        current_tab_focus_widget = self.gen_csv_spacy_model_combo
        for spacy_label in SPACY_ENTITY_LABELS_FOR_UI.keys(): 
            if spacy_label in self.gen_csv_entity_type_checkboxes:
                cb = self.gen_csv_entity_type_checkboxes[spacy_label]
                QWidget.setTabOrder(current_tab_focus_widget, cb)
                current_tab_focus_widget = cb
        QWidget.setTabOrder(current_tab_focus_widget, self.gen_csv_process_button)
        return tab

    def create_anonymize_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        csv_map_group, self.anon_csv_map_path, btn1 = self.create_file_input_group("CSV Mapping File:")
        btn1.clicked.connect(lambda: self.browse_file(self.anon_csv_map_path, "Open CSV Mapping File", file_filter="CSV Files (*.csv)"))
        layout.addLayout(csv_map_group)
        
        self.anon_csv_header_checkbox = QCheckBox("CSV has header row"); layout.addWidget(self.anon_csv_header_checkbox)
        
        input_text_group, self.anon_input_text_path, btn2 = self.create_file_input_group("Original Text/MD/Docx/Odt File (to anonymize):")
        btn2.clicked.connect(lambda: self.browse_file(self.anon_input_text_path, "Open Document File", file_filter=SUPPORTED_INPUT_FILE_TYPES))
        layout.addLayout(input_text_group)
        
        exclusions_layout = QHBoxLayout(); exclusions_layout.addWidget(QLabel("Exclusions (comma-separated):"))
        self.anon_exclusions_edit = QLineEdit(); exclusions_layout.addWidget(self.anon_exclusions_edit); layout.addLayout(exclusions_layout)
        
        output_text_group, self.anon_output_text_path, btn3 = self.create_file_input_group("Output Anonymized File (as .txt or .md):")
        btn3.clicked.connect(lambda: self.browse_file(self.anon_output_text_path, "Save Anonymized File As", save_mode=True, file_filter="Text Files (*.txt *.md);;All Files (*)"))
        layout.addLayout(output_text_group)
        
        self.anon_process_button = QPushButton("&Anonymize Text")
        self.anon_process_button.setShortcut(QKeySequence("Ctrl+A"))
        self.anon_process_button.clicked.connect(self.run_anonymize)
        layout.addWidget(self.anon_process_button, alignment=Qt.AlignmentFlag.AlignCenter); layout.addStretch()
        
        QWidget.setTabOrder(self.anon_csv_map_path, btn1)
        QWidget.setTabOrder(btn1, self.anon_csv_header_checkbox)
        QWidget.setTabOrder(self.anon_csv_header_checkbox, self.anon_input_text_path)
        QWidget.setTabOrder(self.anon_input_text_path, btn2)
        QWidget.setTabOrder(btn2, self.anon_exclusions_edit)
        QWidget.setTabOrder(self.anon_exclusions_edit, self.anon_output_text_path)
        QWidget.setTabOrder(self.anon_output_text_path, btn3)
        QWidget.setTabOrder(btn3, self.anon_process_button)
        return tab

    def create_de_anonymize_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        csv_map_group, self.deanon_csv_map_path, btn1 = self.create_file_input_group("CSV Mapping File:")
        btn1.clicked.connect(lambda: self.browse_file(self.deanon_csv_map_path, "Open CSV Mapping File", file_filter="CSV Files (*.csv)"))
        layout.addLayout(csv_map_group)
        
        self.deanon_csv_header_checkbox = QCheckBox("CSV has header row"); layout.addWidget(self.deanon_csv_header_checkbox)
        
        input_text_group, self.deanon_input_text_path, btn2 = self.create_file_input_group("Anonymized Text/MD File (with placeholders):")
        btn2.clicked.connect(lambda: self.browse_file(self.deanon_input_text_path, "Open Anonymized Text File", file_filter="Text Files (*.txt *.md);;All Files (*)"))
        layout.addLayout(input_text_group)
        
        output_text_group, self.deanon_output_text_path, btn3 = self.create_file_input_group("Output De-anonymized File (as .txt or .md):")
        btn3.clicked.connect(lambda: self.browse_file(self.deanon_output_text_path, "Save De-anonymized File As", save_mode=True, file_filter="Text Files (*.txt *.md);;All Files (*)"))
        layout.addLayout(output_text_group)
        
        self.deanon_process_button = QPushButton("&De-anonymize Text")
        self.deanon_process_button.setShortcut(QKeySequence("Ctrl+D"))
        self.deanon_process_button.clicked.connect(self.run_de_anonymize)
        layout.addWidget(self.deanon_process_button, alignment=Qt.AlignmentFlag.AlignCenter); layout.addStretch()

        QWidget.setTabOrder(self.deanon_csv_map_path, btn1)
        QWidget.setTabOrder(btn1, self.deanon_csv_header_checkbox)
        QWidget.setTabOrder(self.deanon_csv_header_checkbox, self.deanon_input_text_path)
        QWidget.setTabOrder(self.deanon_input_text_path, btn2)
        QWidget.setTabOrder(btn2, self.deanon_output_text_path)
        QWidget.setTabOrder(self.deanon_output_text_path, btn3)
        QWidget.setTabOrder(btn3, self.deanon_process_button)
        return tab

    def browse_file(self, line_edit_widget, caption, save_mode=False, file_filter="All Files (*)"):
        if save_mode: file_path, _ = QFileDialog.getSaveFileName(self, caption, "", file_filter)
        else: file_path, _ = QFileDialog.getOpenFileName(self, caption, "", file_filter)
        if file_path:
            line_edit_widget.setText(file_path); self.log_message(f"Selected file: {file_path}")
            base_name, orig_ext = os.path.splitext(os.path.basename(file_path))
            input_dir = os.path.dirname(file_path)

            if line_edit_widget == self.gen_csv_input_text_path:
                self.suggest_output_filename_direct(os.path.join(input_dir, base_name + "_entity_map.csv"), self.gen_csv_output_csv_path)
            elif line_edit_widget == self.anon_input_text_path:
                self.suggest_output_filename_direct(os.path.join(input_dir, base_name + "_anonymized" + (".md" if orig_ext.lower() == ".md" else ".txt")), self.anon_output_text_path)
            elif line_edit_widget == self.deanon_input_text_path:
                 self.suggest_output_filename_direct(os.path.join(input_dir, base_name + "_de-anonymized" + (".md" if orig_ext.lower() == ".md" else ".txt")), self.deanon_output_text_path)


    def suggest_output_filename_direct(self, suggested_path, output_line_edit):
        if not output_line_edit.text(): 
            output_line_edit.setText(suggested_path)
            self.log_message(f"Suggested output: {suggested_path}")


    def log_message(self, message): self.log_text_edit.append(message); QApplication.processEvents()
    
    def set_buttons_enabled(self, enabled):
        if hasattr(self, 'gen_csv_process_button'): self.gen_csv_process_button.setEnabled(enabled)
        if hasattr(self, 'anon_process_button'): self.anon_process_button.setEnabled(enabled)
        if hasattr(self, 'deanon_process_button'): self.deanon_process_button.setEnabled(enabled)
    
    def start_worker(self, mode, **kwargs):
        if self.worker_thread is not None and self.worker_thread.isRunning():
            QMessageBox.warning(self, "Busy", "A process is already running. Please wait.")
            return False
        self.worker_thread = QThread(self) 
        self.worker_object = Worker(mode, **kwargs)
        self.worker_object.moveToThread(self.worker_thread)
        self.worker_object.progress.connect(self.log_message)
        self.worker_object.finished.connect(self.on_worker_finished)
        self.worker_thread.started.connect(self.worker_object.run)
        self.worker_object.finished.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker_object.deleteLater) 
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.set_buttons_enabled(False); self.worker_thread.start()
        return True

    def on_worker_finished(self, result):
        self.set_buttons_enabled(True)
        if self.worker_object: 
            mode = self.worker_object.mode
            if mode == 'generate_csv': 
                self.handle_generate_csv_finished_from_worker(result)
                # Store paths if CSV generation was successful
                if result is not None and result: # Check if result is not None and not an empty list
                    self.last_original_doc_path_for_csv = self.gen_csv_input_text_path.text()
                    self.last_generated_csv_path = self.gen_csv_output_csv_path.text()
                    self.log_message(f"Stored for auto-fill: Original Doc='{self.last_original_doc_path_for_csv}', Generated CSV='{self.last_generated_csv_path}'")

            elif mode == 'anonymize': 
                self.handle_text_processing_finished_from_worker(result, self.anon_output_text_path.text(), "Anonymization")
            elif mode == 'de_anonymize': 
                self.handle_text_processing_finished_from_worker(result, self.deanon_output_text_path.text(), "De-anonymization")
        self.worker_thread = None; self.worker_object = None

    def run_generate_csv(self):
        input_file = self.gen_csv_input_text_path.text(); output_csv = self.gen_csv_output_csv_path.text()
        spacy_model = self.gen_csv_spacy_model_combo.currentText()
        if not input_file or not output_csv or not spacy_model or "No models found" in spacy_model :
            QMessageBox.warning(self, "Input Error", "Provide all paths and select a valid/installed spaCy model."); return
        
        if not SpacyModelManager.is_model_installed_static(spacy_model): 
            if spacy_model in [TARGET_LARGE_MODEL, FALLBACK_MEDIUM_MODEL, FALLBACK_SMALL_MODEL]:
                self.log_message(f"Selected model '{spacy_model}' not installed. Attempting download sequence...")
                self.set_buttons_enabled(False)
                self.spacy_manager.download_model_sequence([model for model in [spacy_model, TARGET_LARGE_MODEL, FALLBACK_MEDIUM_MODEL, FALLBACK_SMALL_MODEL] if model]) 
                return 
            else:
                QMessageBox.warning(self, "Model Error", f"Custom spaCy model '{spacy_model}' is not installed or recognized. Please install it or select an available one."); return

        text_content = read_document_content(input_file, self.log_message)
        if text_content is None: return 
        if not text_content.strip(): QMessageBox.warning(self, "Input Error", "Input text file is empty or content could not be extracted."); return
        
        selected_labels_for_extraction = []
        for spacy_label, checkbox in self.gen_csv_entity_type_checkboxes.items():
            if checkbox.isChecked():
                if spacy_label == "OTHER_TYPES":
                    selected_labels_for_extraction.extend(OTHER_TYPE_SPACY_LABELS)
                    # Add a generic catch-all if needed, or rely on spaCy's default label if not in placeholder_prefix_map
                    # For now, OTHER_TYPES checkbox enables a set of specific labels.
                else:
                    selected_labels_for_extraction.append(spacy_label)
        
        if not selected_labels_for_extraction:
            QMessageBox.warning(self, "Input Error", "Please select at least one entity type to extract."); return

        self.log_message(f"Starting CSV generation: Input='{input_file}', Output='{output_csv}', Model='{spacy_model}', Types='{', '.join(selected_labels_for_extraction)}'")
        if not self.start_worker(mode='generate_csv', text_content=text_content, spacy_model=spacy_model, selected_spacy_labels=list(set(selected_labels_for_extraction))): 
            self.set_buttons_enabled(True) 

    def handle_generate_csv_finished_from_worker(self, entity_data_for_csv):
        output_csv = self.gen_csv_output_csv_path.text()
        if entity_data_for_csv is None:
            self.log_message("CSV generation failed."); QMessageBox.critical(self, "Error", "CSV generation failed."); return
        if not entity_data_for_csv:
            self.log_message("No entities extracted."); QMessageBox.information(self, "Info", "No entities extracted."); return
        try:
            with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile); writer.writerow(["base_placeholder", "real_entity_name"]); writer.writerows(entity_data_for_csv)
            self.log_message(f"Successfully generated entity map: '{output_csv}'"); 
            QMessageBox.information(self, "Success", f"Entity map CSV saved to:\n{output_csv}")
            # Store paths for auto-fill
            self.last_original_doc_path_for_csv = self.gen_csv_input_text_path.text()
            self.last_generated_csv_path = output_csv
            self.log_message(f"Stored for auto-fill: Original Doc='{self.last_original_doc_path_for_csv}', Generated CSV='{self.last_generated_csv_path}'")
            # Trigger a tab change event manually if the user is still on the first tab,
            # to ensure fields are populated if they immediately switch.
            # Or, just let the natural tab switch handle it.
            # self.on_tab_changed(self.tabs.currentIndex()) # This might be too aggressive
        except Exception as e: self.log_message(f"Error writing CSV: {str(e)}\n{traceback.format_exc()}"); QMessageBox.critical(self, "File Error", f"Error writing CSV: {e}")

    def run_anonymize(self):
        csv_file = self.anon_csv_map_path.text(); input_file = self.anon_input_text_path.text(); output_file = self.anon_output_text_path.text()
        has_header = self.anon_csv_header_checkbox.isChecked(); exclusions_str = self.anon_exclusions_edit.text()
        exclusions = [term.strip() for term in exclusions_str.split(',') if term.strip()] if exclusions_str else []
        if not csv_file or not input_file or not output_file: QMessageBox.warning(self, "Input Error", "Provide all file paths for anonymization."); return
        replacements_map = read_csv_mapping_for_gui(csv_file, has_header, self.log_message)
        if replacements_map is None or not replacements_map: QMessageBox.critical(self, "CSV Error", "Could not load CSV or CSV is empty. Aborting."); return
        
        content = read_document_content(input_file, self.log_message)
        if content is None: return
        
        self.log_message(f"Starting anonymization: Input='{input_file}', Output='{output_file}', CSV='{csv_file}'")
        if not self.start_worker(mode='anonymize', content=content, replacements_map=replacements_map, exclusions=exclusions):
            self.set_buttons_enabled(True)

    def run_de_anonymize(self):
        csv_file = self.deanon_csv_map_path.text(); input_file = self.deanon_input_text_path.text(); output_file = self.deanon_output_text_path.text()
        has_header = self.deanon_csv_header_checkbox.isChecked()
        if not csv_file or not input_file or not output_file: QMessageBox.warning(self, "Input Error", "Provide all file paths for de-anonymization."); return
        replacements_map = read_csv_mapping_for_gui(csv_file, has_header, self.log_message)
        if replacements_map is None or not replacements_map: QMessageBox.critical(self, "CSV Error", "Could not load CSV or CSV is empty. Aborting."); return
        
        try:
            with open(input_file, 'r', encoding='utf-8') as f: content = f.read()
            if not content.strip():
                 QMessageBox.information(self, "Info", "Input file empty. Output will be empty.");
                 with open(output_file, 'w', encoding='utf-8') as outfile: outfile.write("")
                 self.log_message(f"Input file empty. Empty output: '{output_file}'."); return
        except Exception as e: QMessageBox.critical(self, "File Error", f"Error reading input file: {str(e)}\n{traceback.format_exc()}"); return
        
        self.log_message(f"Starting de-anonymization: Input='{input_file}', Output='{output_file}', CSV='{csv_file}'")
        if not self.start_worker(mode='de_anonymize', content=content, replacements_map=replacements_map):
            self.set_buttons_enabled(True)

    def handle_text_processing_finished_from_worker(self, processed_content, output_file_path, operation_name):
        if processed_content is None:
            self.log_message(f"{operation_name} failed."); QMessageBox.critical(self, "Error", f"{operation_name} failed."); return
        try:
            with open(output_file_path, 'w', encoding='utf-8') as outfile: outfile.write(processed_content)
            self.log_message(f"Completed {operation_name.lower()}. Output: '{output_file_path}'"); QMessageBox.information(self, "Success", f"{operation_name} complete!\nOutput:\n{output_file_path}")
        except Exception as e: self.log_message(f"Error writing output: {str(e)}\n{traceback.format_exc()}"); QMessageBox.critical(self, "File Error", f"Error writing output: {e}")
    
    def closeEvent(self, event):
        if self.worker_thread and self.worker_thread.isRunning():
            self.log_message("Attempting to stop worker thread on close...")
            if self.worker_object: self.worker_object.stop()
            self.worker_thread.quit()
            if not self.worker_thread.wait(1500): 
                 self.log_message("Worker thread did not stop gracefully.")
            else:
                 self.log_message("Worker thread stopped.")
        super().closeEvent(event)

if __name__ == "__main__":
    if QApplication.instance() is None: app = QApplication(sys.argv)
    else: app = QApplication.instance()
    window = NERAnonymizerApp()
    window.show()
    try: sys.exit(app.exec())
    except SystemExit: print("Closing application...")
