"""
Prüft MusicLibrary: Ordner/Dateien auflisten, Pfad-Sicherheit
(kein Verlassen des Musikverzeichnisses über "..") und
Shuffle-Playlist-Erstellung.
"""

import tempfile
from pathlib import Path

from player.music_library import MusicLibrary

with tempfile.TemporaryDirectory() as tmp_dir:

    root = Path(tmp_dir) / "music"
    root.mkdir()

    (root / "Rock").mkdir()
    (root / "Rock" / "song1.mp3").write_bytes(b"fake")
    (root / "Rock" / "song2.flac").write_bytes(b"fake")
    (root / "Rock" / "cover.jpg").write_bytes(b"fake")

    (root / "Jazz").mkdir()
    (root / "Jazz" / "song3.wav").write_bytes(b"fake")

    (root / "top.mp3").write_bytes(b"fake")

    outside = Path(tmp_dir) / "secret.mp3"
    outside.write_bytes(b"fake")

    library = MusicLibrary(root)

    # ---------------------------------------------------------
    # 1. Wurzelverzeichnis
    # ---------------------------------------------------------

    listing = library.browse("")
    assert listing is not None
    assert listing.folders == ["Jazz", "Rock"]
    assert listing.files == ["top.mp3"]
    print("OK: Wurzelverzeichnis gelistet")

    # ---------------------------------------------------------
    # 2. Unterordner, nur Audiodateien (kein cover.jpg)
    # ---------------------------------------------------------

    listing = library.browse("Rock")
    assert listing is not None
    assert listing.folders == []
    assert listing.files == ["song1.mp3", "song2.flac"]
    print("OK: Unterordner gelistet, Nicht-Audiodateien ausgeblendet")

    # ---------------------------------------------------------
    # 3. Pfad-Sicherheit: "../" darf das Verzeichnis nicht verlassen
    # ---------------------------------------------------------

    assert library.browse("../") is None
    assert library.resolve("../secret.mp3") is None
    print("OK: Verzeichnis-Ausbruch ('..') wird verhindert")

    # ---------------------------------------------------------
    # 4. Nicht existierender Ordner
    # ---------------------------------------------------------

    assert library.browse("Does/Not/Exist") is None
    print("OK: Nicht existierender Ordner liefert None")

    # ---------------------------------------------------------
    # 5. Rekursive Dateisuche + Shuffle
    # ---------------------------------------------------------

    files = library.find_audio_files(root)
    names = sorted(f.name for f in files)
    assert names == ["song1.mp3", "song2.flac", "song3.wav", "top.mp3"]
    print(f"OK: Rekursive Suche findet alle {len(files)} Audiodateien")

    playlist = library.build_shuffled_playlist(root)
    assert sorted(p.name for p in playlist) == names
    print("OK: Shuffle-Playlist enthält alle Dateien (nur andere Reihenfolge)")

print("Alle Tests erfolgreich.")
