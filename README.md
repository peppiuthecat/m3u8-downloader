# HLS M3U8 Downloader

🇻🇳 Công cụ tải video HLS từ M3U8, hỗ trợ tải video/audio riêng biệt, tải nhiều URL song song và ghép bằng FFmpeg.
Script tự động tải video có độ phân giải cao nhất được cung cấp trong Master M3U8 playlist.

🇬🇧 An HLS M3U8 downloader supporting separate video/audio downloads, multiple URLs, parallel processing, and FFmpeg merging.
There is currently no manual video resolution selection option.

## Requirements / Yêu cầu

- Python 3.8+
- FFmpeg
- Python package: `requests`

Install:

<pre><code>pip install requests</code></pre>

Check FFmpeg:

<pre><code>ffmpeg -version</code></pre>

## Usage / Cách sử dụng

### Download one URL / Tải một URL

<pre><code>python m3u8-downloader.py --url "https://example.com/video/master.m3u8"</code></pre>

### Download URLs from a file / Tải nhiều URL từ file

Create `urls.txt`:

<pre><code>https://example.com/video/001/master.m3u8
https://example.com/video/002/master.m3u8
https://example.com/video/003/master.m3u8</code></pre>

Run:

<pre><code>python m3u8-downloader.py --file-path urls.txt</code></pre>

### Parallel downloads / Tải song song

<pre><code>python m3u8-downloader.py \
    --file-path urls.txt \
    --parallel 4</code></pre>

### Custom output directory / Thư mục output

<pre><code>python m3u8-downloader.py \
    --file-path urls.txt \
    --parallel 4 \
    --output downloads</code></pre>

## Options / Tùy chọn

| Option | Description |
|---|---|
| `--url URL` | Single M3U8 URL / Một URL M3U8 |
| `--file-path FILE` | File containing URLs / File chứa danh sách URL |
| `--parallel N` | Parallel URL count / Số URL chạy song song |
| `--output DIR` | Output directory / Thư mục lưu kết quả |

Show help:

<pre><code>python m3u8-downloader.py --help</code></pre>

## Output / Kết quả

<pre><code>downloads/
└── &lt;video-id&gt;/
    ├── video_original.mp4
    ├── audio_original.m4a
    └── merged.mp4</code></pre>

- `video_original.mp4` — Video stream
- `audio_original.m4a` — Audio stream
- `merged.mp4` — Final video + audio

## Notes / Lưu ý

🇻🇳 Script hỗ trợ HLS fragmented MP4 (`fMP4`) sử dụng `EXT-X-MAP`. Hãy đảm bảo bạn có quyền tải và sử dụng nội dung.

🇬🇧 The script supports HLS fragmented MP4 (`fMP4`) playlists using `EXT-X-MAP`. Make sure you have the necessary rights to download and use the content.
