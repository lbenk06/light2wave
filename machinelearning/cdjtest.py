import os

def check_cdj_usb(drive_letter):
    print(f"🚀 Starte USB-Scanner auf Laufwerk {drive_letter}...")
    
    pioneer_folder = os.path.join(drive_letter, "PIONEER")
    contents_folder = os.path.join(drive_letter, "Contents")
    
    if not os.path.exists(pioneer_folder) or not os.path.exists(contents_folder):
        print(f"❌ Fehler: Konnte die Ordner 'PIONEER' oder 'Contents' auf {drive_letter} nicht finden.")
        print("Ist der Buchstabe richtig und ist es ein echter Rekordbox-Export-Stick?")
        return

    print("✅ PIONEER und Contents Ordner gefunden! Der Stick ist legitim.")
    print("Suche nach den versteckten Drop-Analysen (.DAT / .EXT Dateien)...")
    
    anlz_count = 0
    for root, dirs, files in os.walk(pioneer_folder):
        for file in files:
            if file.endswith('.DAT') or file.endswith('.EXT'):
                anlz_count += 1
                
    print(f"✅ BINGO! {anlz_count} Analyse-Dateien gefunden.")
    print("-" * 50)
    print("Wenn hier tausende Dateien gefunden wurden, sind wir bereit für den Slicer!")

if __name__ == "__main__":
    # WICHTIG: Ändere das "E:/" zu dem Buchstaben, den dein Stick in Windows hat!
    check_cdj_usb("D:/")