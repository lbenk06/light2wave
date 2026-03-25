import os
import logging
from pyrekordbox.anlz import AnlzFile

# Warnungen stumm schalten
logging.getLogger('pyrekordbox.anlz.file').setLevel(logging.ERROR)

def zeig_mir_alles(drive_letter):
    print("🔍 Okay, keine Geheimnisse mehr. Lese ALLE Blöcke der ersten Datei...")
    pioneer_folder = os.path.join(drive_letter, "PIONEER")
    
    for root, dirs, files in os.walk(pioneer_folder):
        for file in files:
            if file.endswith('.EXT'):
                filepath = os.path.join(root, file)
                print(f"\n📂 Analysiere Datei: {file}")
                
                try:
                    anlz = AnlzFile.parse_file(filepath)
                    
                    print("-" * 50)
                    # Wir lassen uns einfach ALLE Bausteine auflisten, die drin sind!
                    for tag in anlz.tags:
                        print(f" 📦 Gefundener Block: {tag.__class__.__name__}")
                        
                    print("-" * 50)
                    print("Das ist alles, was in dieser Datei steckt. Stoppe Skript!")
                    return  # SOFORT stoppen nach der ersten Datei!
                    
                except Exception as e:
                    print(f"❌ Fehler: {e}")
                    return

if __name__ == "__main__":
    zeig_mir_alles("D:/")