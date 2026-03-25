import xml.etree.ElementTree as ET

def roentgen_scanner(xml_path):
    print(f"Scanne XML: {xml_path} ...")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    tag_counts = {}
    
    # Geht durch alle 14.583 Tracks und sammelt alle Unter-Elemente
    for track in root.findall('.//TRACK'):
        for child in track:
            tag_counts[child.tag] = tag_counts.get(child.tag, 0) + 1
            
    print("\n--- ERGEBNIS DER DATEN-ANALYSE ---")
    if not tag_counts:
        print("Schockschwerenot: Rekordbox hat zu den Tracks KEINE Unter-Elemente (wie Cues oder Grids) exportiert!")
    else:
        print("Folgende Daten-Tags wurden in deiner gesamten Library gefunden:")
        for tag, count in tag_counts.items():
            print(f" 📂 {tag}: {count} mal vorhanden")

if __name__ == "__main__":
    roentgen_scanner("C:/Users/legol/Documents/MCI/3 semester/abschlussprojekt light2wave/light2wave/machinelearning/rekordboxlib.xml")