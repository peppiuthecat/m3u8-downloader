#! /usr/bin/env python3

import argparse
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests


# ============================================================
# CONFIG
# ============================================================

MAX_RETRIES = 3
TIMEOUT = 30
SEGMENT_WORKERS = 8

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    )
})


# ============================================================
# HTTP
# ============================================================

def http_get(url, stream=False):

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            response = session.get(
                url,
                timeout=TIMEOUT,
                stream=stream,
            )

            response.raise_for_status()

            return response

        except Exception as e:

            last_error = e

            if attempt < MAX_RETRIES:
                print(
                    f"    retry "
                    f"{attempt}/{MAX_RETRIES - 1}"
                )

    raise RuntimeError(
        f"Request failed:\n{url}\n{last_error}"
    )


# ============================================================
# M3U8 ATTRIBUTE PARSER
# ============================================================

def parse_attrs(line):

    result = {}

    if ":" not in line:
        return result

    value = line.split(":", 1)[1]

    pattern = r'([A-Z0-9-]+)=("[^"]*"|[^,]*)'

    for key, val in re.findall(pattern, value):

        result[key] = val.strip('"')

    return result


# ============================================================
# MASTER PLAYLIST
# ============================================================

def parse_master(master_url, text):

    videos = []
    audios = []

    pending_video = None

    for raw in text.splitlines():

        line = raw.strip()

        if not line:
            continue

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        if line.startswith("#EXT-X-MEDIA:"):

            attrs = parse_attrs(line)

            if attrs.get("TYPE") == "AUDIO":

                uri = attrs.get("URI")

                if uri:

                    audios.append({
                        "url": urljoin(
                            master_url,
                            uri,
                        ),
                        "group": attrs.get(
                            "GROUP-ID",
                            "",
                        ),
                        "name": attrs.get(
                            "NAME",
                            "",
                        ),
                    })

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        elif line.startswith(
            "#EXT-X-STREAM-INF:"
        ):

            pending_video = parse_attrs(line)

        elif (
            pending_video is not None
            and not line.startswith("#")
        ):

            resolution = pending_video.get(
                "RESOLUTION",
                "0x0",
            )

            match = re.match(
                r"(\d+)x(\d+)",
                resolution,
            )

            width = 0
            height = 0

            if match:

                width = int(match.group(1))
                height = int(match.group(2))

            videos.append({
                "url": urljoin(
                    master_url,
                    line,
                ),
                "width": width,
                "height": height,
                "bandwidth": int(
                    pending_video.get(
                        "BANDWIDTH",
                        0,
                    )
                ),
                "audio_group": (
                    pending_video.get(
                        "AUDIO",
                        "",
                    )
                ),
            })

            pending_video = None

    return videos, audios


def choose_video(videos):

    if not videos:
        raise RuntimeError(
            "No video stream found."
        )

    return max(
        videos,
        key=lambda x: (
            x["width"] * x["height"],
            x["bandwidth"],
        ),
    )


def choose_audio(audios, video):

    if not audios:
        raise RuntimeError(
            "No audio stream found."
        )

    candidates = [
        audio
        for audio in audios
        if audio["group"]
        == video["audio_group"]
    ]

    if not candidates:
        candidates = audios

    def bitrate(audio):

        match = re.search(
            r"(\d+)",
            audio["group"],
        )

        if match:
            return int(match.group(1))

        return 0

    return max(
        candidates,
        key=bitrate,
    )


# ============================================================
# MEDIA PLAYLIST
# ============================================================

def parse_media_playlist(
    playlist_url,
    text,
):

    init_url = None
    segments = []

    current_byterange = None

    for raw in text.splitlines():

        line = raw.strip()

        if not line:
            continue

        # ----------------------------------------------------
        # Initialization segment
        # ----------------------------------------------------

        if line.startswith(
            "#EXT-X-MAP:"
        ):

            attrs = parse_attrs(line)

            uri = attrs.get("URI")

            if uri:

                init_url = urljoin(
                    playlist_url,
                    uri,
                )

        # ----------------------------------------------------
        # Media segment
        # ----------------------------------------------------

        elif (
            not line.startswith("#")
        ):

            segments.append({
                "url": urljoin(
                    playlist_url,
                    line,
                ),
            })

    return init_url, segments


# ============================================================
# DOWNLOAD ONE FILE
# ============================================================

def download_file(
    url,
    path,
):

    path = Path(path)

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:

            response = http_get(
                url,
                stream=True,
            )

            with open(
                path,
                "wb",
            ) as f:

                for chunk in response.iter_content(
                    chunk_size=1024 * 1024
                ):

                    if chunk:
                        f.write(chunk)

            return

        except Exception:

            if attempt >= MAX_RETRIES:
                raise


# ============================================================
# DOWNLOAD SEGMENTS
# ============================================================

def download_media(
    playlist_url,
    playlist_text,
    output_file,
    temp_dir,
    prefix,
):
    """
    Download:

        EXT-X-MAP
        +
        segment 0
        +
        segment 1
        +
        ...

    then concatenate the binary data into output_file.

    This is suitable for fragmented MP4 HLS
    such as the Twitter/X playlist in the example.
    """

    init_url, segments = (
        parse_media_playlist(
            playlist_url,
            playlist_text,
        )
    )

    if not init_url:

        raise RuntimeError(
            "Playlist does not contain EXT-X-MAP. "
            "This playlist may not be fMP4."
        )

    temp_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Download initialization segment
    # --------------------------------------------------------

    init_file = (
        temp_dir /
        f"{prefix}_init.bin"
    )

    print(
        f"  Downloading {prefix} init..."
    )

    download_file(
        init_url,
        init_file,
    )

    # --------------------------------------------------------
    # Download media segments
    # --------------------------------------------------------

    print(
        f"  Downloading "
        f"{len(segments)} {prefix} segments..."
    )

    segment_files = {}

    def worker(item):

        index, segment = item

        path = (
            temp_dir /
            f"{prefix}_{index:06d}.m4s"
        )

        download_file(
            segment["url"],
            path,
        )

        return index, path

    completed = 0

    with ThreadPoolExecutor(
        max_workers=SEGMENT_WORKERS
    ) as executor:

        futures = [
            executor.submit(
                worker,
                item,
            )
            for item in enumerate(
                segments
            )
        ]

        for future in as_completed(
            futures
        ):

            index, path = (
                future.result()
            )

            segment_files[index] = path

            completed += 1

            print(
                f"\r  {prefix}: "
                f"{completed}/{len(segments)}",
                end="",
                flush=True,
            )

    print()

    # --------------------------------------------------------
    # Build original media file
    # --------------------------------------------------------

    print(
        f"  Building {output_file.name}..."
    )

    with open(
        output_file,
        "wb",
    ) as output:

        # The initialization segment MUST come first.
        with open(
            init_file,
            "rb",
        ) as f:

            shutil.copyfileobj(
                f,
                output,
                length=1024 * 1024,
            )

        # Then append segments in playlist order.
        for index in range(
            len(segments)
        ):

            path = segment_files[index]

            with open(
                path,
                "rb",
            ) as f:

                shutil.copyfileobj(
                    f,
                    output,
                    length=1024 * 1024,
                )

    return output_file


# ============================================================
# MERGE VIDEO + AUDIO
# ============================================================

def merge_video_audio(
    video_file,
    audio_file,
    output_file,
):

    print(
        "  Merging video + audio..."
    )

    subprocess.run(
        [
            "ffmpeg",

            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",

            "-i",
            str(video_file),

            "-i",
            str(audio_file),

            "-map",
            "0:v:0",

            "-map",
            "1:a:0",

            "-c",
            "copy",

            "-movflags",
            "+faststart",

            str(output_file),
        ],
        check=True,
    )


# ============================================================
# ID FROM MASTER URL
# ============================================================

def get_video_id(url):

    path = urlparse(url).path

    filename = Path(path).name

    # S78oM9kVd5UYxrHa.m3u8
    if filename.lower().endswith(
        ".m3u8"
    ):

        filename = filename[:-5]

    # Safety
    filename = re.sub(
        r"[^A-Za-z0-9._-]",
        "_",
        filename,
    )

    if not filename:
        filename = "video"

    return filename


# ============================================================
# DOWNLOAD ONE URL
# ============================================================

def download_one(
    master_url,
    output_root,
    index,
):

    video_id = get_video_id(
        master_url
    )

    output_dir = (
        output_root /
        video_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    video_file = (
        output_dir /
        "video_original.mp4"
    )

    audio_file = (
        output_dir /
        "audio_original.m4a"
    )

    merged_file = (
        output_dir /
        "merged.mp4"
    )

    print()
    print("=" * 70)
    print(
        f"[{index}] {video_id}"
    )
    print(
        f"URL: {master_url}"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Master
    # --------------------------------------------------------

    print(
        "[1/4] Reading master playlist..."
    )

    master = http_get(
        master_url
    ).text

    videos, audios = parse_master(
        master_url,
        master,
    )

    video = choose_video(
        videos
    )

    audio = choose_audio(
        audios,
        video,
    )

    print(
        f"Video: "
        f"{video['width']}x"
        f"{video['height']}"
    )

    print(
        f"Video playlist: "
        f"{video['url']}"
    )

    print(
        f"Audio playlist: "
        f"{audio['url']}"
    )

    # --------------------------------------------------------
    # Get media playlists
    # --------------------------------------------------------

    print(
        "[2/4] Reading media playlists..."
    )

    video_playlist = http_get(
        video["url"]
    ).text

    audio_playlist = http_get(
        audio["url"]
    ).text

    # --------------------------------------------------------
    # Temporary directory
    # --------------------------------------------------------

    temp_dir = (
        output_dir /
        ".temp"
    )

    if temp_dir.exists():

        shutil.rmtree(
            temp_dir
        )

    temp_dir.mkdir(
        parents=True
    )

    try:

        # ----------------------------------------------------
        # Video
        # ----------------------------------------------------

        print(
            "[3/4] Downloading video..."
        )

        download_media(
            video["url"],
            video_playlist,
            video_file,
            temp_dir / "video",
            "video",
        )

        print(
            f"  Saved: {video_file}"
        )

        # ----------------------------------------------------
        # Audio
        # ----------------------------------------------------

        print(
            "[3/4] Downloading audio..."
        )

        download_media(
            audio["url"],
            audio_playlist,
            audio_file,
            temp_dir / "audio",
            "audio",
        )

        print(
            f"  Saved: {audio_file}"
        )

        # ----------------------------------------------------
        # Merge
        # ----------------------------------------------------

        print(
            "[4/4] Merging..."
        )

        merge_video_audio(
            video_file,
            audio_file,
            merged_file,
        )

        print()
        print(
            "DONE"
        )

        print(
            f"  Video : {video_file}"
        )

        print(
            f"  Audio : {audio_file}"
        )

        print(
            f"  Final : {merged_file}"
        )

    finally:

        # Remove temporary .m4s files.
        if temp_dir.exists():

            shutil.rmtree(
                temp_dir,
                ignore_errors=True,
            )


# ============================================================
# LOAD URLS
# ============================================================

def load_urls(
    file_path
):

    urls = []

    with open(
        file_path,
        "r",
        encoding="utf-8",
    ) as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            found = re.findall(
                r'https?://[^\s<>"\']+',
                line,
            )

            urls.extend(
                found
            )

    # Remove duplicate URLs.
    return list(
        dict.fromkeys(
            urls
        )
    )


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "HLS M3U8 downloader"
        )
    )

    group = parser.add_mutually_exclusive_group(
        required=True
    )

    group.add_argument(
        "--url",
        help="M3U8 URL",
    )

    group.add_argument(
        "--file-path",
        help="Text file containing URLs",
    )

    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help=(
            "Number of URLs to process "
            "simultaneously. Default: 1"
        ),
    )

    parser.add_argument(
        "--output",
        default="downloads",
        help=(
            "Output directory. "
            "Default: ./downloads"
        ),
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # FFmpeg
    # --------------------------------------------------------

    if shutil.which("ffmpeg") is None:

        print(
            "ERROR: ffmpeg was not found."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if args.parallel < 1:

        parser.error(
            "--parallel must be >= 1"
        )

    # --------------------------------------------------------
    # URLs
    # --------------------------------------------------------

    if args.url:

        urls = [
            args.url
        ]

    else:

        file_path = Path(
            args.file_path
        )

        if not file_path.exists():

            print(
                f"ERROR: File not found: "
                f"{file_path}"
            )

            sys.exit(1)

        urls = load_urls(
            file_path
        )

    if not urls:

        print(
            "No URLs found."
        )

        return

    output_root = Path(
        args.output
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"Found {len(urls)} URL(s)"
    )

    print(
        f"Parallel: {args.parallel}"
    )

    print(
        f"Output: {output_root}"
    )

    # --------------------------------------------------------
    # Sequential
    # --------------------------------------------------------

    if args.parallel == 1:

        for index, url in enumerate(
            urls,
            start=1,
        ):

            try:

                download_one(
                    url,
                    output_root,
                    index,
                )

            except Exception as e:

                print()
                print(
                    f"FAILED [{index}]"
                )
                print(e)

    # --------------------------------------------------------
    # Parallel
    # --------------------------------------------------------

    else:

        with ThreadPoolExecutor(
            max_workers=args.parallel
        ) as executor:

            futures = {}

            for index, url in enumerate(
                urls,
                start=1,
            ):

                future = executor.submit(
                    download_one,
                    url,
                    output_root,
                    index,
                )

                futures[future] = (
                    index,
                    url,
                )

            for future in as_completed(
                futures
            ):

                index, url = futures[
                    future
                ]

                try:

                    future.result()

                except Exception as e:

                    print()
                    print(
                        f"FAILED [{index}]"
                    )
                    print(e)

    print()
    print("=" * 70)
    print("ALL TASKS FINISHED")
    print("=" * 70)


if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "\nCancelled."
        )

        sys.exit(130)
