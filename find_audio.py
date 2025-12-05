#!/usr/bin/env python3
"""
Script per trovare blocchi con audio PCM reale in un'immagine disco.
Salta le zone vuote (silenzio) e il rumore bianco, estrae solo audio valido.
"""

import sys
import struct
import os
from pathlib import Path

# Parametri audio X Air 16 - Behringer
SAMPLE_RATE = 48000
BIT_DEPTH = 16
CHANNELS = 2
BYTES_PER_SAMPLE = 2  # 16-bit = 2 bytes

# Dimensione blocco di analisi (1MB)
BLOCK_SIZE = 1024 * 1024

def analyze_block(data):
    """
    Analizza un blocco di dati per capire se contiene audio reale.
    Ritorna: 'audio', 'silence', 'noise', 'empty'
    """
    if len(data) < 1000:
        return 'empty', 0
    
    # Controlla se è tutto zero (vuoto)
    zero_count = data.count(b'\x00')
    zero_ratio = zero_count / len(data)
    
    if zero_ratio > 0.99:
        return 'empty', 0
    
    if zero_ratio > 0.90:
        return 'silence', zero_ratio
    
    # Analizza come PCM 16-bit signed little-endian stereo
    # Prende campioni ogni 4 byte (2 byte * 2 canali)
    samples = []
    for i in range(0, min(len(data), 40000), 4):
        if i + 2 <= len(data):
            # Legge 16-bit signed little-endian
            b = data[i:i+2]
            if len(b) == 2:
                val = struct.unpack('<h', b)[0]  # signed short little-endian
                samples.append(val)
    
    if len(samples) < 100:
        return 'empty', 0
    
    # Calcola statistiche
    avg = sum(samples) / len(samples)
    variance = sum((s - avg) ** 2 for s in samples) / len(samples)
    
    # Calcola "smoothness" - quanto i campioni vicini sono correlati
    # Audio reale ha alta correlazione, rumore bianco no
    diffs = [abs(samples[i] - samples[i-1]) for i in range(1, len(samples))]
    avg_diff = sum(diffs) / len(diffs) if diffs else 0
    max_val = max(abs(s) for s in samples)
    
    if max_val == 0:
        return 'silence', 0
    
    smoothness = 1.0 - (avg_diff / (max_val * 2)) if max_val > 0 else 0
    
    # Audio reale: varianza media, alta smoothness
    # Rumore: alta varianza, bassa smoothness  
    # Silenzio: bassa varianza
    
    if variance < 1000:
        return 'silence', smoothness
    
    if smoothness > 0.3 and variance > 10000:
        return 'audio', smoothness
    
    if smoothness < 0.2:
        return 'noise', smoothness
    
    # Probabilmente audio
    return 'audio', smoothness


def find_audio_blocks(image_path, output_dir):
    """
    Scansiona l'immagine e trova blocchi con audio reale.
    """
    file_size = os.path.getsize(image_path)
    total_blocks = file_size // BLOCK_SIZE
    
    print(f"File: {image_path}")
    print(f"Dimensione: {file_size / (1024**3):.2f} GB")
    print(f"Blocchi da analizzare: {total_blocks}")
    print("-" * 60)
    
    audio_blocks = []
    current_audio_start = None
    
    with open(image_path, 'rb') as f:
        block_num = 0
        
        while True:
            data = f.read(BLOCK_SIZE)
            if not data:
                break
            
            block_type, score = analyze_block(data)
            position_mb = (block_num * BLOCK_SIZE) / (1024 * 1024)
            
            if block_type == 'audio':
                if current_audio_start is None:
                    current_audio_start = block_num
                    print(f"[{position_mb:6.0f} MB] ▶ AUDIO TROVATO (score: {score:.2f})")
            else:
                if current_audio_start is not None:
                    # Fine blocco audio
                    audio_blocks.append((current_audio_start, block_num - 1))
                    print(f"[{position_mb:6.0f} MB] ◼ Fine audio")
                    current_audio_start = None
                
                if block_num % 100 == 0:  # Progresso ogni 100MB
                    print(f"[{position_mb:6.0f} MB] ... {block_type}", end='\r')
            
            block_num += 1
        
        # Chiudi ultimo blocco se necessario
        if current_audio_start is not None:
            audio_blocks.append((current_audio_start, block_num - 1))
    
    print("\n" + "=" * 60)
    print(f"TROVATI {len(audio_blocks)} BLOCCHI AUDIO:")
    print("=" * 60)
    
    # Crea directory output
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Estrai i blocchi audio
    with open(image_path, 'rb') as f:
        for i, (start, end) in enumerate(audio_blocks):
            start_mb = (start * BLOCK_SIZE) / (1024 * 1024)
            end_mb = ((end + 1) * BLOCK_SIZE) / (1024 * 1024)
            size_mb = end_mb - start_mb
            
            print(f"\nBlocco {i+1}: {start_mb:.0f} MB - {end_mb:.0f} MB ({size_mb:.0f} MB)")
            
            # Estrai blocco
            output_file = os.path.join(output_dir, f"audio_block_{i+1:03d}_{start_mb:.0f}MB.raw")
            
            f.seek(start * BLOCK_SIZE)
            block_data = f.read((end - start + 1) * BLOCK_SIZE)
            
            with open(output_file, 'wb') as out:
                out.write(block_data)
            
            print(f"   Salvato: {output_file}")
            
            # Crea anche WAV con header
            wav_file = output_file.replace('.raw', '.wav')
            create_wav_header(output_file, wav_file)
            print(f"   WAV: {wav_file}")
    
    return audio_blocks


def create_wav_header(raw_file, wav_file):
    """
    Aggiunge header WAV a un file PCM raw.
    """
    raw_size = os.path.getsize(raw_file)
    
    with open(raw_file, 'rb') as f_in:
        raw_data = f_in.read()
    
    with open(wav_file, 'wb') as f_out:
        # RIFF header
        f_out.write(b'RIFF')
        f_out.write(struct.pack('<I', raw_size + 36))  # File size - 8
        f_out.write(b'WAVE')
        
        # fmt chunk
        f_out.write(b'fmt ')
        f_out.write(struct.pack('<I', 16))  # Chunk size
        f_out.write(struct.pack('<H', 1))   # Audio format (1 = PCM)
        f_out.write(struct.pack('<H', CHANNELS))
        f_out.write(struct.pack('<I', SAMPLE_RATE))
        
        byte_rate = SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE
        f_out.write(struct.pack('<I', byte_rate))
        
        block_align = CHANNELS * BYTES_PER_SAMPLE
        f_out.write(struct.pack('<H', block_align))
        f_out.write(struct.pack('<H', BIT_DEPTH))
        
        # data chunk
        f_out.write(b'data')
        f_out.write(struct.pack('<I', raw_size))
        f_out.write(raw_data)


if __name__ == '__main__':
    
    # ============================================================
    # CONFIGURAZIONE - Modifica qui i percorsi per uso diretto
    # ============================================================
    
    # Imposta su True per usare i percorsi hardcoded sotto
    USA_PERCORSI_MANUALI = True
    
    # Percorsi manuali (modifica questi!)
    PERCORSO_IMMAGINE = "/Volumes/ROMEO/P_BIANCA.dmg"      # Mac
    # PERCORSO_IMMAGINE = r"D:\P_BIANCA.dmg"               # Windows
    
    CARTELLA_OUTPUT = os.path.expanduser("~/Desktop/recovered_audio")  # Mac/Linux
    # CARTELLA_OUTPUT = r"D:\recovered_audio"              # Windows
    
    # ============================================================
    
    if USA_PERCORSI_MANUALI:
        image_path = PERCORSO_IMMAGINE
        output_dir = CARTELLA_OUTPUT
        print(f"Usando percorsi manuali:")
        print(f"  Input:  {image_path}")
        print(f"  Output: {output_dir}")
        print("")
    elif len(sys.argv) >= 2:
        image_path = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/Desktop/recovered_audio")
    else:
        print("Uso: python find_audio.py <immagine.dmg> [cartella_output]")
        print("")
        print("Oppure modifica USA_PERCORSI_MANUALI = True nello script")
        print("e imposta PERCORSO_IMMAGINE e CARTELLA_OUTPUT")
        sys.exit(1)
    
    if not os.path.exists(image_path):
        print(f"Errore: file non trovato: {image_path}")
        sys.exit(1)
    
    find_audio_blocks(image_path, output_dir)
    
    print("\n" + "=" * 60)
    print("FATTO!")
    print(f"I file sono stati salvati in: {output_dir}")
    print("")
    print("Apri i file .wav in qualsiasi player audio.")
    print("Se l'audio è distorto, prova a importare i .raw in Audacity")
    print("con parametri diversi (16-bit invece di 24-bit, ecc.)")
