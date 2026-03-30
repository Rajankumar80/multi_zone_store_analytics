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
import os

# ─── PIN MAIN THREAD TO CORE 0 ───────────────────────────────────────────────
# The OS scheduler was freely migrating the display/UI thread across multiple
# cores, causing variable CPU usage. We hard-pin the main process to core 0
# so it never moves. Capture processes start from core 1 (start_core_id=1)
# and are pinned to their own cores inside CaptureGroupProcess.run().
try:
    os.sched_setaffinity(0, {0})
    print("[INFO] Main thread pinned to CPU Core 0.")
except AttributeError:
    # Windows does not support sched_setaffinity — silently skip.
    print("[WARN] sched_setaffinity not supported on this OS — core pinning skipped.")

from camera_manager import MultiCameraManager

# ─── CAMERA SOURCES ──────────────────────────────────────────────────────────
# Every camera MUST have a completely unique "name" so the dictionary
# doesn't overwrite the frames.

CAMERAS = [
    {
        "name":   "cam_entry",
        "source": "/home/keshav/rajan/reid_testing/store.mp4",
    },
    {
        "name":   "cam_exit_1",
        "source": "/home/keshav/rajan/reid_testing/cam_test/shopping.mp4",
    },
    {
        "name":   "cam_exit_2",
        "source": "/home/keshav/rajan/reid_testing/cam_test/shopping.mp4",
    },
    {
        "name":   "cam_exit_3",
        "source": "/home/keshav/rajan/reid_testing/cam_test/shopping.mp4",
    },
    {
        "name":   "cam_exit_4",
        "source": "/home/keshav/rajan/reid_testing/cam_test/shopping.mp4",
    },
    {
        "name":   "cam_exit_5",
        "source": "/home/keshav/rajan/reid_testing/cam_test/shopping.mp4",
    },
]


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

def main():
    if not CAMERAS:
        print("[ERROR] No cameras defined in CAMERAS list")
        return

    manager = MultiCameraManager(
        cameras        = CAMERAS,
        cams_per_core  = 2,
        display_scale  = 1.0,
        start_core_id  = 1,   # ← capture groups get cores 1, 2, 3 …
                               #   core 0 is reserved exclusively for main thread
    )

    # Start all capture sub-processes
    manager.start()

    # Blocks main thread and runs the display loop (stays on core 0)
    manager.display_streams()


if __name__ == "__main__":
    main()