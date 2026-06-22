# AIO Core Vision 360 — Crop, Trim & Loop Tool

A simple but powerful Python GUI tool to **crop, trim, and automatically find seamless loops in videos**, optimized for square outputs (480×480) — perfect for AIO LCD screens like the Core Vision 360.

## ✨ Features

* 🎬 **Video preview player** with timeline scrubbing
* ✂️ **Trim IN / OUT controls**
* 🔲 **Smart square crop (portrait & landscape support)**
* 🔍 **Automatic loop detection** using frame similarity
* 🔁 **Loop preview mode**
* 💾 **Export to optimized 480×480 MP4 (H.264 + AAC)**
* ⚡ Fast processing via ffmpeg

## 🧠 How it works

The loop finder samples frames within a selected range and compares them using pixel differences.
It automatically finds the **best matching start and end points** to create a smooth, seamless loop.

## 📦 Requirements

* Python 3.x
* ffmpeg (must be available in PATH)
* Python packages:

  ```
  pip install Pillow opencv-python
  ```

## 🚀 Usage

Run the script:

```
python main.py
```

Steps:

1. Load a video
2. Set trim range
3. Adjust crop position
4. (Optional) Define loop search range
5. Click **"Zoek beste loop"**
6. Preview and export

## 📁 Output

* Standard clip → `*_480x480.mp4`
* Loop clip → `*_loop480.mp4`

## 🎯 Use case

Designed for:

* AIO cooler displays
* Looping background visuals
* Clean, square-format video content

## ⚠️ Notes

* Requires ffmpeg installed or bundled
* Works best with videos that have subtle motion or repeating patterns

---

Made for people who want **clean loops without manual frame-by-frame editing**.

