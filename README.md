# Behringer X Air 16 Audio Recovery - 0 Byte Files

Guide to recover lost recordings when Behringer X Air 16 (or X32/Midas M32) creates **0 byte files** with **1970 date**.

## The Problem

The Behringer X Air mixer writes audio to the USB drive in real-time, but the WAV header is only written when you press **STOP**. If:
- You remove the USB drive too early
- The mixer powers off
- It crashes during recording

...the files show as **0 bytes** because the header is missing, but **the audio data is still on the disk!**

## Why Standard Tools Don't Work

- **PhotoRec/Recuva**: look for "RIFF" WAV signature → find nothing
- **CHKDSK/fsck**: sometimes work, sometimes don't
- **Commercial software**: same problem

The data is **raw PCM without header**, invisible to standard recovery tools.

## The Solution

### Requirements
- Mac, Windows, or Linux computer
- **Audacity** (free): https://www.audacityteam.org
- Enough disk space for the image (e.g., 32GB for a 32GB drive)

### X Air 16 Audio Parameters
| Parameter | Value |
|-----------|-------|
| Sample Rate | 48000 Hz |
| Bit Depth | 16-bit |
| Channels | 2 (Stereo) |
| Encoding | PCM Signed Little-Endian |

---

## Workflow

### Step 1: Create Raw Disk Image

**⚠️ DO NOT write anything to the USB drive!**

#### Mac
```bash
# Find the disk
diskutil list

# Unmount (DO NOT eject!)
diskutil unmountDisk /dev/disk4

# Create raw image (replace disk4 with yours)
sudo dd if=/dev/rdisk4 of=/Users/YOURNAME/Desktop/backup.raw bs=1m status=progress
```

#### Windows (using HDD Raw Copy Tool)
1. Download: https://hddguru.com/software/HDD-Raw-Copy-Tool/
2. Run as Administrator
3. SOURCE: select the USB drive
4. TARGET: select FILE → `D:\backup.raw`
5. START

#### Linux
```bash
# Find the disk
lsblk

# Create image
sudo dd if=/dev/sdb of=~/Desktop/backup.raw bs=1M status=progress
```

---

### Step 2: Split into Chunks

The image is too large for Audacity. Split it into 1-2 GB pieces:

#### Mac/Linux
```bash
# Create folder for chunks
mkdir ~/Desktop/chunks
cd ~/Desktop/chunks

# Split into 2GB pieces
split -b 2g ~/Desktop/backup.raw chunk_
```

#### Windows (PowerShell)
```powershell
# Use 7-Zip or this script
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

### Step 3: Import in Audacity as Raw

1. Open **Audacity**
2. **File → Import → Raw Data**
3. Select a `chunk_xx` file
4. Set these parameters:

| Parameter | Value |
|-----------|-------|
| Encoding | **Signed 16-bit PCM** |
| Byte order | **Little-endian** |
| Channels | **2 (Stereo)** |
| Sample rate | **48000** |

5. Click **Import**

---

### Step 4: Find Your Recordings

- Scroll through the timeline looking for waveforms
- **White noise** = empty space/corrupted data → skip
- **Regular waveforms** = real audio → listen!
- Recordings may be **fragmented** across multiple chunks

---

### Step 5: Export Recovered Audio

1. Select the valid audio portion
2. **File → Export → Export as WAV**
3. Save with a descriptive name

---

## Automatic Script (Python)

To automate finding blocks with real audio:

```python
#!/usr/bin/env python3
"""
Find blocks with real PCM audio in a disk image.
Automatically skips silence and noise.
"""

import struct
import os
from pathlib import Path

# X Air 16 parameters
SAMPLE_RATE = 48000
BIT_DEPTH = 16
CHANNELS = 2
BLOCK_SIZE = 1024 * 1024  # 1MB

def analyze_block(data):
    """Analyze if a block contains real audio."""
    if len(data) < 1000:
        return 'empty', 0
    
    zero_count = data.count(b'\x00')
    zero_ratio = zero_count / len(data)
    
    if zero_ratio > 0.95:
        return 'silence', 0
    
    # Read 16-bit signed little-endian samples
    samples = []
    for i in range(0, min(len(data), 40000), 4):
        if i + 2 <= len(data):
            val = struct.unpack('<h', data[i:i+2])[0]
            samples.append(val)
    
    if len(samples) < 100:
        return 'empty', 0
    
    # Calculate smoothness (real audio vs noise)
    diffs = [abs(samples[i] - samples[i-1]) for i in range(1, len(samples))]
    avg_diff = sum(diffs) / len(diffs)
    max_val = max(abs(s) for s in samples) or 1
    smoothness = 1.0 - (avg_diff / (max_val * 2))
    
    if smoothness > 0.3:
        return 'audio', smoothness
    return 'noise', smoothness

def scan_image(image_path, output_dir):
    """Scan the image and extract audio blocks."""
    file_size = os.path.getsize(image_path)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    print(f"Scanning: {image_path}")
    print(f"Size: {file_size / (1024**3):.2f} GB")
    
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
                print(f"[{pos_mb:.0f} MB] ▶ Audio found")
            elif block_type != 'audio' and in_audio:
                in_audio = False
                audio_regions.append((audio_start, block_num - 1))
                print(f"[{pos_mb:.0f} MB] ◼ Audio ends")
            
            block_num += 1
    
    # Extract audio regions
    print(f"\nFound {len(audio_regions)} audio regions")
    
    with open(image_path, 'rb') as f:
        for i, (start, end) in enumerate(audio_regions):
            f.seek(start * BLOCK_SIZE)
            data = f.read((end - start + 1) * BLOCK_SIZE)
            
            out_file = os.path.join(output_dir, f"audio_{i+1:03d}.raw")
            with open(out_file, 'wb') as out:
                out.write(data)
            print(f"Saved: {out_file}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python find_audio.py <image.raw> [output_folder]")
        sys.exit(1)
    
    image = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else "./recovered_audio"
    scan_image(image, output)
```

---

## Troubleshooting

### Audio sounds distorted
- Try different parameters in Audacity:
  - **24-bit** instead of 16-bit
  - **44100 Hz** instead of 48000 Hz
  - **Mono** instead of Stereo
  - **Big-endian** instead of Little-endian

### Can't find the recordings
- Data may be fragmented across multiple chunks
- Try searching all chunks, not just the first ones
- The disk may have been overwritten

### CHKDSK/fsck finds nothing
- Normal! This method works when standard tools fail

---

## Future Prevention

1. **Always press STOP** before removing the USB drive
2. **Wait 10 seconds** after stop (light stops blinking)
3. Use **USB 2.0 drives, max 32GB, FAT32 formatted**
4. Recommended drives: **SanDisk Extreme, high write speed**

---

## Credits

- Guide created with help from Claude (Anthropic)
- Tested on Behringer X Air 16
- Should also work on: X32, Midas M32, X Air 18, XR18

---

## License

MIT - Share freely!

---

## Contribute

Did you recover your recordings? Have improvements to suggest?
- Open an Issue
- Send a Pull Request
- Share your experience!
