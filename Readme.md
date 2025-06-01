QTAnon - NER Anonymizer/De-Anonymizer Tool

QTAnon is a PyQt6-based application that enables users to anonymize and de-anonymize text documents using Named Entity Recognition (NER) powered by spaCy. This tool is particularly useful for protecting sensitive information in documents while preserving the overall structure and readability.
Features

    Entity Recognition: Automatically detects names, organizations, locations, and other entities using spaCy's NER capabilities

    Anonymization: Replaces identified entities with placeholders (e.g., person_1, org_1)

    De-anonymization: Restores original entities from anonymized text using a mapping file

    CSV Mapping: Generates and uses CSV files to track entity-placeholder relationships

    Exclusion Support: Allows specifying entities to skip during anonymization

    Multi-model Support: Works with different spaCy models (sm, md, lg)

    Markdown Processing: Handles Markdown-formatted documents while preserving structure

    Threaded Operations: Long-running processes run in background threads to keep UI responsive

Installation
Prerequisites

    Python 3.7+

    pip package manager

Steps

    Clone the repository:

bash

git clone https://github.com/yourusername/QTAnon.git
cd QTAnon

    Create and activate a virtual environment (recommended):

bash

python -m venv venv
source venv/bin/activate  # Linux/MacOS
venv\Scripts\activate     # Windows

    Install required dependencies:

bash

pip install -r requirements.txt

    Download the recommended spaCy model:

bash

python -m spacy download en_core_web_lg

Usage
1. Generate Entity Map (CSV)

    Select your input text file (supports .txt and .md formats)

    Choose output CSV path (default suggestion: [input]_entity_map.csv)

    Select a spaCy model (recommended: en_core_web_lg for best accuracy)

    Click "Generate Entity Map CSV"

    Review the generated CSV file containing entity-placeholder mappings

2. Anonymize Text

    Select the CSV mapping file generated in step 1

    Choose the original text file to anonymize

    Specify exclusions (comma-separated entities to skip)

    Set output file path (default: [input]_anonymized_output)

    Click "Anonymize Text" to create the anonymized document

3. De-anonymize Text

    Select the CSV mapping file

    Choose the anonymized text file

    Set output file path (default: [input]_de-anonymized_output)

    Click "De-anonymize Text" to restore original entities

File Formats

    Input Text: Plain text (.txt) or Markdown (.md) format

    CSV Mapping File:

        Header row: base_placeholder, real_entity_name

        Data rows: Placeholder and corresponding entity

    Output Files: Same format as input files

Technical Notes
Key Components

    spaCy Integration: Uses spaCy for entity recognition

    PyQt6 GUI: Provides intuitive tab-based interface

    Threading: Worker threads handle long operations

    Markdown Processing: Preserves document structure while processing content

    Model Management: Automatically checks for and downloads required spaCy models

Special Handling

    Person Names: Handles first/last name variations during de-anonymization

    Exclusions: Case-insensitive exclusion of specified entities

    Long Entity Priority: Processes longer entities first to avoid partial replacements

    Markdown Preservation: Maintains formatting during anonymization

Troubleshooting
Common Issues

    spaCy model not found:

        Ensure you've downloaded the model: python -m spacy download en_core_web_lg

        Verify the model is installed: python -m spacy validate

    CSV mapping issues:

        Ensure CSV has two columns: placeholder and entity

        Check for empty rows or missing values

    Unresponsive UI during long operations:

        The application uses background threads - wait for operation to complete

        Larger models and documents take more processing time

Logging

    All operations are logged in the "Status Log" section at the bottom of the application

    Log messages provide detailed information about each processing step

License

This project is licensed under the MIT License - see the LICENSE file for details.
