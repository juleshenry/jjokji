import os
import glob
import csv
import uuid

repos = ["../french_notes", "../korean_notes", "../portuguese_notes", "../castellano_notes"]
out_csv = "src/data/LanguageNotes.csv"

with open(out_csv, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['guid', 'Language', 'Topic', 'Front', 'Back', 'tags'])

    for repo in repos:
        lang = os.path.basename(repo).replace('_notes', '').capitalize()
        for md_file in glob.glob(f"{repo}/**/*.md", recursive=True):
            if 'README' in md_file.upper() or 'LICENSE' in md_file.upper():
                continue
            
            topic = "General Notes"
            front = os.path.basename(md_file).replace('.md', '').replace('_', ' ')
            
            with open(md_file, 'r', encoding='utf-8') as mf:
                back = mf.read()
            
            writer.writerow([str(uuid.uuid4()), lang, topic, front, back, lang.lower()])
