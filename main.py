# import cv2
# from model import Detector

# # ---------------------------------------------------
# # INPUT SOURCE
# # ---------------------------------------------------

# # SOURCE = "rtsp://10.64.36.14:554/rtsp/streaming?channel=01&subtype=1"

# # For video file use:
# SOURCE = "/home/keshav/rajan/new_pipeline/input/shopping.mp4"


# CAMERA_NAME = "cam_entry"
# OUTPUT_PATH = "/home/keshav/rajan/new_pipeline/output_videos/output.avi"

# DISPLAY_SCALE = 0.8


# def main():

#     detector = Detector(camera_name=CAMERA_NAME)

#     cap = cv2.VideoCapture(SOURCE)

#     if not cap.isOpened():
#         print("[ERROR] Cannot open stream/video")
#         return

#     print("[INFO] Stream started")

#     cv2.namedWindow("Camera View", cv2.WINDOW_NORMAL)
#     cv2.namedWindow("Floor Map", cv2.WINDOW_NORMAL)

#     fourcc = cv2.VideoWriter_fourcc(*"XVID")
#     out = None

#     while True:

#         ret, frame = cap.read()

#         if not ret:
#             print("[INFO] Stream ended")
#             break

#         processed_frame, tracks, floor_map = detector.process_frame(frame)

#         # initialize writer
#         if out is None:
#             h, w = processed_frame.shape[:2]
#             out = cv2.VideoWriter(OUTPUT_PATH, fourcc, 8, (w, h))
#             print(f"[INFO] Recording → {OUTPUT_PATH}")

#         out.write(processed_frame)

#         # resize display
#         cam_display = cv2.resize(
#             processed_frame,
#             (0, 0),
#             fx=DISPLAY_SCALE,
#             fy=DISPLAY_SCALE
#         )

#         map_display = cv2.resize(
#             floor_map,
#             (0, 0),
#             fx=DISPLAY_SCALE,
#             fy=DISPLAY_SCALE
#         )

#         cv2.imshow("Camera View", cam_display)
#         cv2.imshow("Floor Map", map_display)

#         if cv2.waitKey(1) & 0xFF == ord("q"):
#             print("[INFO] Quit by user")
#             break

#     cap.release()

#     if out is not None:
#         out.release()

#     cv2.destroyAllWindows()

#     print("[INFO] Finished")


# if __name__ == "__main__":
#     main()
# -------------------------------------------------------------------------
"""
main.py — Entry point for multi-camera surveillance pipeline.

All stream capture (GStreamer), inference, and display logic lives in
camera_manager.py. This file only declares camera sources and kicks off
the manager.

Architecture (handled entirely by MultiCameraManager):
──────────────────────────────────────────────────────
  ┌───────────────────────────────────────────────────┐
  │  Per-camera StreamProcessor (multiprocessing)     │
  │  GStreamer RTSP/file pipeline → frame_queue       │
  └──────────────────┬────────────────────────────────┘
                     │  raw frames
  ┌──────────────────▼────────────────────────────────┐
  │  MultiCameraManager — main process                │
  │  Pulls frames → Detector(cam_name).process_frame  │
  │  CPU-only inference (no CUDA)                     │
  └──────────────────┬────────────────────────────────┘
                     │  (annotated_frame, floor_map)
  ┌──────────────────▼────────────────────────────────┐
  │  DisplayGrid — side-by-side [cam | floor_map]     │
  │  Stays open after streams end — press q to quit   │
  └───────────────────────────────────────────────────┘
"""

from camera_manager import MultiCameraManager

# ─── CAMERA SOURCES ──────────────────────────────────────────────────────────
# Each entry spawns its own GStreamer capture process and its own Detector.
# "name" must match the key in zones_runtime.json for correct zone loading.
# Use "source" for RTSP URLs or local file paths.

CAMERAS = [
    {
        "name":   "cam_entry",
        # "source": "rtsp://10.64.36.14:554/rtsp/streaming?channel=01&subtype=1",
        "source": "/home/keshav/rajan/new_pipeline/input/shopping.mp4",
        "output": "/home/keshav/rajan/new_pipeline/output_videos/cam_entry_output.avi",
    },
    # {
    #     "name":   "cam_exit",
    #     # "source": "rtsp://10.64.36.15:554/rtsp/streaming?channel=01&subtype=1",
    #     "source": "/home/keshav/rajan/new_pipeline/input/shopping.mp4",
    #     "output": "/home/keshav/rajan/new_pipeline/output_videos/cam_exit_output.avi",
    # },
]

# ─── TUNING ───────────────────────────────────────────────────────────────────

DISPLAY_SCALE  = 0.5    # scale each cell before compositing
RECORD_FPS     = 8       # output .avi frames-per-second
IMG_SIZE       = (640, 640)
BUFFER_SIZE    = 2       # per-camera GStreamer frame queue depth
STREAM_FPS     = 10     # target decode FPS for file/RTSP sources


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

def main():
    if not CAMERAS:
        print("[ERROR] No cameras defined in CAMERAS list")
        return

    manager = MultiCameraManager(
        cameras       = CAMERAS,
        buffer_size   = BUFFER_SIZE,
        fps           = STREAM_FPS,
        img_size      = IMG_SIZE,
        display_scale = DISPLAY_SCALE,
        record_fps    = RECORD_FPS,
    )

    manager.display_streams()


if __name__ == "__main__":
    main()