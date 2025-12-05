# Recupero Audio da Behringer X Air 16 - File 0 Byte

Guida per recuperare registrazioni perse quando il Behringer X Air 16 (o X32/Midas M32) crea file da **0 byte** con data **1970**.

## Il Problema

Il mixer Behringer X Air scrive l'audio sulla chiavetta USB in tempo reale, ma l'header WAV viene scritto solo quando premi **STOP**. Se:
- Togli la chiavetta troppo presto
- Il mixer si spegne
- Si blocca durante la registrazione

...i file risultano da **0 byte** perché manca l'header, ma **i dati audio sono ancora sul disco!**

## Perché i Tool Standard Non Funzionano

- **PhotoRec/Recuva**: cercano la firma "RIFF" dei file WAV → non trovano nulla
- **CHKDSK/fsck**: a volte funzionano, a volte no
- **Software commerciali**: stesso problema

I dati sono **PCM raw senza header**, invisibili ai tool di recupero standard.

## La Soluzione

### Requisiti
- Computer Mac, Windows o Linux
- **Audacity** (gratuito): https://www.audacityteam.org
- Spazio disco sufficiente per l'immagine (es. 32GB per chiavetta da 32GB)

### Parametri Audio X Air 16
| Parametro | Valore |
|-----------|--------|
| Sample Rate | 48000 Hz |
| Bit Depth | 16-bit |
| Canali | 2 (Stereo) |
| Encoding | PCM Signed Little-Endian |

---

## Workflow

### Step 1: Crea Immagine Raw del Disco

**⚠️ NON scrivere nulla sulla chiavetta USB!**

#### Mac
```bash
# Trova il disco
diskutil list

# Smonta (NON espellere!)
diskutil unmountDisk /dev/disk4

# Crea immagine raw (sostituisci disk4 con il tuo)
sudo dd if=/dev/rdisk4 of=/Users/TUONOME/Desktop/backup.raw bs=1m status=progress
```

#### Windows (con HDD Raw Copy Tool)
1. Scarica: https://hddguru.com/software/HDD-Raw-Copy-Tool/
2. Apri come Amministratore
3. SOURCE: seleziona la chiavetta USB
4. TARGET: seleziona FILE → `D:\backup.raw`
5. START

#### Linux
```bash
# Trova il disco
lsblk

# Crea immagine
sudo dd if=/dev/sdb of=~/Desktop/backup.raw bs=1M status=progress
```

---

### Step 2: Dividi in Chunk

L'immagine è troppo grande per Audacity. Dividila in pezzi da 1-2 GB:

#### Mac/Linux
```bash
# Crea cartella per i chunk
mkdir ~/Desktop/chunks
cd ~/Desktop/chunks

# Dividi in pezzi da 2GB
split -b 2g ~/Desktop/backup.raw chunk_
```

#### Windows (PowerShell)
```powershell
# Usa 7-Zip o questo script
$file = "D:\backup.raw"
$chunkSize = 2GB
$buffer = New-Object byte[] $chunkSize
$stream = [System.IO.File]::OpenRead($file)
$chunkNum = 0

while ($bytesRead = $stream.Read($buffer, 0, $chunkSize)) {
    $outFile = "D:\chunks\chunk_{0:D3}.raw" -f $chunkNum
    [System.IO.File]::WriteAllBytes($outFile, $buffer[0..($bytesRead-1)])
    $chunkNum++
}
$stream.Close()
```

---

### Step 3: Importa in Audacity come Raw

1. Apri **Audacity**
2. **File → Import → Raw Data**
3. Seleziona un file `chunk_xx`
4. Imposta questi parametri:

| Parametro | Valore |
|-----------|--------|
| Encoding | **Signed 16-bit PCM** |
| Byte order | **Little-endian** |
| Channels | **2 (Stereo)** |
| Sample rate | **48000** |

5. Clicca **Import**

---

### Step 4: Cerca le Tue Registrazioni

- Scorri la timeline cercando le forme d'onda
- **Rumore bianco** = spazio vuoto/dati corrotti → salta
- **Forme d'onda regolari** = audio reale → ascolta!
- Le registrazioni possono essere **frammentate** su più chunk

---

### Step 5: Esporta l'Audio Recuperato

1. Seleziona la porzione di audio valido
2. **File → Export → Export as WAV**
3. Salva con un nome descrittivo

---

## Script Automatico (Python)

Per automatizzare la ricerca dei blocchi con audio reale:

```python
#!/usr/bin/env python3
"""
Trova blocchi con audio PCM reale in un'immagine disco.
Salta automaticamente silenzio e rumore.
"""

import struct
import os
from pathlib import Path

# Parametri X Air 16
SAMPLE_RATE = 48000
BIT_DEPTH = 16
CHANNELS = 2
BLOCK_SIZE = 1024 * 1024  # 1MB

def analyze_block(data):
    """Analizza se un blocco contiene audio reale."""
    if len(data) < 1000:
        return 'empty', 0
    
    zero_count = data.count(b'\x00')
    zero_ratio = zero_count / len(data)
    
    if zero_ratio > 0.95:
        return 'silence', 0
    
    # Legge campioni 16-bit signed little-endian
    samples = []
    for i in range(0, min(len(data), 40000), 4):
        if i + 2 <= len(data):
            val = struct.unpack('<h', data[i:i+2])[0]
            samples.append(val)
    
    if len(samples) < 100:
        return 'empty', 0
    
    # Calcola smoothness (audio reale vs rumore)
    diffs = [abs(samples[i] - samples[i-1]) for i in range(1, len(samples))]
    avg_diff = sum(diffs) / len(diffs)
    max_val = max(abs(s) for s in samples) or 1
    smoothness = 1.0 - (avg_diff / (max_val * 2))
    
    if smoothness > 0.3:
        return 'audio', smoothness
    return 'noise', smoothness

def scan_image(image_path, output_dir):
    """Scansiona l'immagine ed estrae blocchi audio."""
    file_size = os.path.getsize(image_path)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    print(f"Scansione: {image_path}")
    print(f"Dimensione: {file_size / (1024**3):.2f} GB")
    
    audio_regions = []
    
    with open(image_path, 'rb') as f:
        block_num = 0
        in_audio = False
        audio_start = 0
        
        while True:
            data = f.read(BLOCK_SIZE)
            if not data:
                break
            
            block_type, score = analyze_block(data)
            pos_mb = block_num * BLOCK_SIZE / (1024**2)
            
            if block_type == 'audio' and not in_audio:
                in_audio = True
                audio_start = block_num
                print(f"[{pos_mb:.0f} MB] ▶ Audio trovato")
            elif block_type != 'audio' and in_audio:
                in_audio = False
                audio_regions.append((audio_start, block_num - 1))
                print(f"[{pos_mb:.0f} MB] ◼ Fine audio")
            
            block_num += 1
    
    # Estrai regioni audio
    print(f"\nTrovate {len(audio_regions)} regioni audio")
    
    with open(image_path, 'rb') as f:
        for i, (start, end) in enumerate(audio_regions):
            f.seek(start * BLOCK_SIZE)
            data = f.read((end - start + 1) * BLOCK_SIZE)
            
            out_file = os.path.join(output_dir, f"audio_{i+1:03d}.raw")
            with open(out_file, 'wb') as out:
                out.write(data)
            print(f"Salvato: {out_file}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Uso: python find_audio.py <immagine.raw> [cartella_output]")
        sys.exit(1)
    
    image = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else "./recovered_audio"
    scan_image(image, output)
```

---

## Troubleshooting

### L'audio suona distorto
- Prova parametri diversi in Audacity:
  - **24-bit** invece di 16-bit
  - **44100 Hz** invece di 48000 Hz
  - **Mono** invece di Stereo
  - **Big-endian** invece di Little-endian

### Non trovo le registrazioni
- I dati potrebbero essere frammentati su più chunk
- Prova a cercare in tutti i chunk, non solo i primi
- Il disco potrebbe essere stato sovrascritto

### CHKDSK/fsck non trova nulla
- Normale! Questo metodo funziona quando i tool standard falliscono

---

## Prevenzione Futura

1. **Premi sempre STOP** prima di rimuovere la chiavetta
2. **Aspetta 10 secondi** dopo lo stop (la luce smette di lampeggiare)
3. Usa chiavette **USB 2.0, max 32GB, FAT32**
4. Chiavette consigliate: **SanDisk Extreme, alta velocità scrittura**

---

## Credits

- Guida creata con l'aiuto di Claude (Anthropic)
- Testato su Behringer X Air 16
- Dovrebbe funzionare anche su: X32, Midas M32, X Air 18, XR18

---

## Licenza

MIT - Condividi liberamente!

---

## Contribuisci

Hai recuperato le tue registrazioni? Hai miglioramenti da suggerire?
- Apri una Issue
- Manda una Pull Request
- Condividi la tua esperienza!
