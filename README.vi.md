🇻🇳 Tiếng Việt | 🇬🇧 [English](README.md)

# HLS M3U8 Downloader

🇻🇳 Công cụ tải video HLS từ M3U8, hỗ trợ tải video/audio riêng biệt, tải nhiều URL song song và ghép bằng FFmpeg.
Script tự động tải video có độ phân giải cao nhất được cung cấp trong Master M3U8 playlist.

## Yêu cầu

- Python 3.8+
- FFmpeg
- Python package: `requests`

Install:

<pre><code>pip install requests</code></pre>

Check FFmpeg:

<pre><code>ffmpeg -version</code></pre>

## Cách sử dụng

### Tải một URL

<pre><code>python m3u8-downloader.py --url "https://example.com/video/master.m3u8"</code></pre>

### Tải nhiều URL từ file

Create `urls.txt`:

<pre><code>https://example.com/video/001/master.m3u8
https://example.com/video/002/master.m3u8
https://example.com/video/003/master.m3u8</code></pre>

Run:

<pre><code>python m3u8-downloader.py --file-path urls.txt</code></pre>

### Tải song song

<pre><code>python m3u8-downloader.py \
    --file-path urls.txt \
    --parallel 4</code></pre>

### Thư mục output

<pre><code>python m3u8-downloader.py \
    --file-path urls.txt \
    --parallel 4 \
    --output downloads</code></pre>

## Tùy chọn

| Option | Description |
|---|---|
| `--url URL` | Một URL M3U8 |
| `--file-path FILE` | File chứa danh sách URL |
| `--parallel N` |  Số URL chạy song song |
| `--output DIR` | Thư mục lưu kết quả |

Show help:

<pre><code>python m3u8-downloader.py --help</code></pre>

## Kết quả

<pre><code>downloads/
└── &lt;video-id&gt;/
    ├── video_original.mp4
    ├── audio_original.m4a
    └── merged.mp4</code></pre>

- `video_original.mp4` — Video stream
- `audio_original.m4a` — Audio stream
- `merged.mp4` — Final video + audio

## Lưu ý

🇻🇳 Script hỗ trợ HLS fragmented MP4 (`fMP4`) sử dụng `EXT-X-MAP`. Hãy đảm bảo bạn có quyền tải và sử dụng nội dung.
