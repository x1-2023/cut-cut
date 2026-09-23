"""
capcut_chunk_engine.py - Stream-copy video splitter and seamless concat demuxer.
High-speed, zero-transcode chunking engine for rendering long videos (>5 mins)
on ByteDance / CapCut Cloud without triggering timeout / error 19070005.
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable


def get_media_duration(file_path: str) -> float:
    """Return total media duration in seconds using ffprobe."""
    if not os.path.isfile(file_path):
        return 0.0
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[!] ffprobe duration error on {file_path}: {e}")
        return 0.0


def split_video(
    input_path: str,
    chunk_duration: int = 60,
    temp_dir: Optional[str] = None,
    max_chunks: Optional[int] = None,
    log_cb: Optional[Callable[[str], None]] = None
) -> List[Dict[str, Any]]:
    """
    Split a video into non-reencoded chunks using ffmpeg stream copy.
    - If total duration <= chunk_duration + 10s: returns original file directly.
    - If total duration > chunk_duration: slices video into chunks <= chunk_duration.
    
    Returns list of dicts:
    [
        {
            "index": 0,
            "path": "/path/to/part_000.mp4",
            "start": 0.0,
            "duration": 60.0,
            "is_chunk": True
        },
        ...
    ]
    """
    def log(msg: str):
        if log_cb:
            log_cb(msg)
        else:
            print(msg)

    in_file = Path(input_path).resolve()
    if not in_file.is_file():
        raise FileNotFoundError(f"Video input not found: {input_path}")

    total_dur = get_media_duration(str(in_file))
    if total_dur <= 0.0:
        log(f"[!] Warning: Cannot probe duration for {in_file.name}, proceeding without chunking.")
        return [{
            "index": 0,
            "path": str(in_file),
            "start": 0.0,
            "duration": 0.0,
            "is_chunk": False
        }]

    # If within safe limit, no splitting needed
    if total_dur <= (chunk_duration + 10):
        log(f"[*] Video duration: {total_dur:.1f}s (<= {chunk_duration+10}s). Direct cloud render without chunking.")
        return [{
            "index": 0,
            "path": str(in_file),
            "start": 0.0,
            "duration": total_dur,
            "is_chunk": False
        }]

    # Establish temp directory for chunks
    if not temp_dir:
        temp_dir = str(in_file.parent / f".chunks_{in_file.stem}")
    out_dir = Path(temp_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = []
    current_start = 0.0
    idx = 0

    log(f"[*] Video duration: {total_dur/60:.1f} minutes. Slicing into {chunk_duration}s chunks (zero re-encode)...")

    while current_start < total_dur:
        dur_segment = min(float(chunk_duration), total_dur - current_start)
        chunk_name = f"{in_file.stem}_chunk_{idx:03d}.mp4"
        chunk_path = out_dir / chunk_name

        # ffmpeg fast stream copy slice
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{current_start:.3f}",
            "-i", str(in_file),
            "-t", f"{dur_segment:.3f}",
            "-map", "0:v:0",
            "-map", "0:a?",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(chunk_path)
        ]

        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if res.returncode != 0 or not chunk_path.is_file() or chunk_path.stat().st_size == 0:
            log(f"[!] Error cutting chunk {idx}: {res.stderr[:200]}")
            raise RuntimeError(f"FFmpeg failed to slice chunk {idx}: {res.stderr}")

        chunks.append({
            "index": idx,
            "path": str(chunk_path),
            "start": current_start,
            "duration": dur_segment,
            "is_chunk": True
        })

        idx += 1
        current_start += dur_segment

        if max_chunks and idx >= max_chunks:
            log(f"[*] Reached max_chunks limit ({max_chunks}). Stopping slice.")
            break

    log(f"[+] Sliced {len(chunks)} chunks successfully in {out_dir.name}")
    return chunks


def concat_videos(
    chunk_paths: List[str],
    output_path: str,
    log_cb: Optional[Callable[[str], None]] = None
) -> str:
    """
    Concat multiple rendered MP4 chunks into a single final MP4 file
    using ffmpeg concat demuxer with stream copy (no re-encoding, near-instant).
    """
    def log(msg: str):
        if log_cb:
            log_cb(msg)
        else:
            print(msg)

    if not chunk_paths:
        raise ValueError("chunk_paths is empty.")

    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    if len(chunk_paths) == 1:
        # Just copy or rename
        shutil.copy2(chunk_paths[0], str(out_file))
        return str(out_file)

    # Prepare concat list file
    list_file = out_file.parent / f"concat_list_{out_file.stem}.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for p in chunk_paths:
            # Escape path for ffmpeg concat demuxer
            safe_p = str(Path(p).resolve()).replace("\\", "/")
            f.write(f"file '{safe_p}'\n")

    log(f"[*] Concat {len(chunk_paths)} rendered parts into final MP4: {out_file.name}...")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(out_file)
    ]

    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )

    try:
        list_file.unlink(missing_ok=True)
    except Exception:
        pass

    if res.returncode != 0 or not out_file.is_file() or out_file.stat().st_size == 0:
        log(f"[!] Concat failed: {res.stderr}")
        raise RuntimeError(f"FFmpeg concat demuxer failed: {res.stderr}")

    log(f"[+] Seamless concat complete: {out_file.stat().st_size / (1024*1024):.2f} MB")
    return str(out_file)


def cleanup_chunks(chunks_dir: str):
    """Remove temporary chunk folder and intermediate files."""
    try:
        p = Path(chunks_dir)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    except Exception as e:
        print(f"[!] Note: Could not fully delete chunk dir {chunks_dir}: {e}")


def compress_video_crf(
    input_path: str,
    output_path: Optional[str] = None,
    crf: int = 24,
    preset: str = "veryfast",
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> str:
    """
    Compress video using H.264 CRF (Constant Rate Factor) to drastically reduce file size
    while preserving visual fidelity and keeping audio stream intact.
    - crf=24: Optimal balance between quality and high compression (~60-80% size reduction).
    - preset='veryfast': Fast encoding on CPU.
    """
    import time

    def log(msg: str):
        if log_cb:
            log_cb(msg)
        else:
            try:
                print(msg)
            except UnicodeEncodeError:
                print(msg.encode("ascii", errors="replace").decode("ascii"))

    in_file = Path(input_path).resolve()
    if not in_file.is_file():
        raise FileNotFoundError(f"File to compress not found: {in_file}")

    if output_path:
        out_file = Path(output_path).resolve()
    else:
        out_file = in_file  # In-place compression by default

    orig_size_mb = in_file.stat().st_size / (1024 * 1024)
    log(f"[*] Bắt đầu nén video (CRF {crf}, preset {preset})...")
    log(f"[*] Dung lượng gốc: {orig_size_mb:.2f} MB")
    if progress_cb:
        progress_cb(96, f"Đang nén video tối ưu dung lượng (CRF {crf})...")

    # Temp file in case input == output
    is_replace = (out_file == in_file)
    tmp_out = in_file.parent / f".compress_tmp_{in_file.stem}_{int(time.time())}.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_file),
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-c:a", "copy",
        str(tmp_out)
    ]

    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )

    if res.returncode != 0 or not tmp_out.is_file() or tmp_out.stat().st_size == 0:
        log(f"[!] Lỗi khi nén video: {res.stderr}")
        if tmp_out.exists():
            tmp_out.unlink()
        return str(in_file)

    comp_size_mb = tmp_out.stat().st_size / (1024 * 1024)
    saved_pct = (1.0 - (comp_size_mb / orig_size_mb)) * 100.0 if orig_size_mb > 0 else 0.0

    if is_replace and comp_size_mb >= orig_size_mb:
        log(f"[i] Dung lượng sau nén ({comp_size_mb:.2f} MB) không tối ưu hơn gốc ({orig_size_mb:.2f} MB). Giữ nguyên file ban đầu.")
        tmp_out.unlink()
        return str(in_file)

    if is_replace:
        try:
            in_file.unlink()
            tmp_out.rename(out_file)
        except Exception as e:
            # Fallback if Windows file lock delay
            time.sleep(0.5)
            if in_file.exists():
                in_file.unlink()
            tmp_out.rename(out_file)
    else:
        tmp_out.rename(out_file)

    log(f"[+] Nén thành công! Dung lượng mới: {comp_size_mb:.2f} MB (Tiết kiệm {saved_pct:.1f}%)")
    return str(out_file)
