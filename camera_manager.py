# # # import os
# # # os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
# # # import gi
# # # gi.require_version("Gst", "1.0")
# # # from gi.repository import Gst
# # # import numpy as np
# # # import multiprocessing as mp
# # # import signal
# # # import sys
# # # import time
# # # import cv2
# # # from mode import Detector


# # # def make_no_signal_frame(width, height):
# # #     try:
# # #         frame = np.zeros((height, width, 3), dtype=np.uint8)
# # #         frame[:] = (30, 30, 30)
# # #         text = "NO SIGNAL"
# # #         font = cv2.FONT_HERSHEY_SIMPLEX
# # #         font_scale = width / 400.0
# # #         thickness = max(2, int(font_scale * 2))
# # #         (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
# # #         tx = (width - tw) // 2
# # #         ty = (height + th) // 2
# # #         cv2.putText(frame, text, (tx + 2, ty + 2), font, font_scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
# # #         cv2.putText(frame, text, (tx, ty), font, font_scale, (60, 60, 60), thickness, cv2.LINE_AA)
# # #         line_color = (50, 50, 50)
# # #         spacing = max(20, width // 32)
# # #         for i in range(0, height, spacing):
# # #             cv2.line(frame, (0, i), (width, i), line_color, 1)
# # #         for j in range(0, width, spacing):
# # #             cv2.line(frame, (j, 0), (j, height), line_color, 1)
# # #         return frame
# # #     except Exception:
# # #         return np.zeros((height, width, 3), dtype=np.uint8)


# # # class StreamProcessor(mp.Process):
# # #     def __init__(self, cam_id, url, frame_queue, img_size, buffer_size, fps):
# # #         super().__init__()
# # #         self.cam_id = cam_id
# # #         self.url = url
# # #         self.frame_queue = frame_queue
# # #         self.width, self.height = img_size
# # #         self.buffer_size = buffer_size
# # #         self.fps = fps
# # #         self.running = mp.Value('b', True)
# # #         self.pipeline = None

# # #     def _build_pipeline(self):
# # #         try:
# # #             return Gst.parse_launch(
# # #                 f'rtspsrc location="{self.url}" protocols=tcp latency=300 retry=3 timeout=5000000 ! '
# # #                 f'rtph265depay ! h265parse ! avdec_h265 ! '
# # #                 f'videorate ! video/x-raw,framerate={self.fps}/1 ! '
# # #                 f'videoconvert ! videoscale method=3 ! '
# # #                 f'video/x-raw,width={self.width},height={self.height},format=BGR ! '
# # #                 f'appsink name=sink emit-signals=true sync=false max-buffers={self.buffer_size} drop=true'
# # #             )
# # #         except Exception:
# # #             return None

# # #     def on_sample(self, sink):
# # #         try:
# # #             sample = sink.emit("pull-sample")
# # #             if not sample:
# # #                 return Gst.FlowReturn.OK
# # #             buf = sample.get_buffer()
# # #             res, map_info = buf.map(Gst.MapFlags.READ)
# # #             if not res:
# # #                 return Gst.FlowReturn.OK
# # #             try:
# # #                 frame = np.ndarray(
# # #                     (self.height, self.width, 3),
# # #                     buffer=map_info.data,
# # #                     dtype=np.uint8
# # #                 ).copy()
# # #                 try:
# # #                     if self.frame_queue.full():
# # #                         self.frame_queue.get_nowait()
# # #                     self.frame_queue.put_nowait(frame)
# # #                 except Exception:
# # #                     pass
# # #             finally:
# # #                 buf.unmap(map_info)
# # #         except Exception:
# # #             pass
# # #         return Gst.FlowReturn.OK

# # #     def _cleanup(self):
# # #         try:
# # #             if self.pipeline:
# # #                 self.pipeline.set_state(Gst.State.NULL)
# # #                 self.pipeline.get_state(timeout=2 * Gst.SECOND)
# # #         except Exception:
# # #             pass
# # #         finally:
# # #             self.pipeline = None

# # #     def run(self):
# # #         try:
# # #             signal.signal(signal.SIGINT, signal.SIG_IGN)
# # #             signal.signal(signal.SIGTERM, lambda s, f: setattr(self.running, 'value', False))
# # #         except Exception:
# # #             pass
# # #         try:
# # #             Gst.init(None)
# # #         except Exception:
# # #             return
# # #         while self.running.value:
# # #             try:
# # #                 self.pipeline = self._build_pipeline()
# # #                 if self.pipeline is None:
# # #                     raise RuntimeError()
# # #                 try:
# # #                     sink = self.pipeline.get_by_name("sink")
# # #                     sink.connect("new-sample", self.on_sample)
# # #                 except Exception:
# # #                     raise RuntimeError()
# # #                 ret = self.pipeline.set_state(Gst.State.PLAYING)
# # #                 if ret == Gst.StateChangeReturn.FAILURE:
# # #                     raise RuntimeError()
# # #                 try:
# # #                     bus = self.pipeline.get_bus()
# # #                     while self.running.value:
# # #                         try:
# # #                             msg = bus.timed_pop(100 * Gst.MSECOND)
# # #                             if msg:
# # #                                 if msg.type == Gst.MessageType.ERROR:
# # #                                     break
# # #                                 elif msg.type == Gst.MessageType.EOS:
# # #                                     break
# # #                         except Exception:
# # #                             break
# # #                 except Exception:
# # #                     pass
# # #             except Exception:
# # #                 pass
# # #             finally:
# # #                 self._cleanup()
# # #             if self.running.value:
# # #                 try:
# # #                     time.sleep(3)
# # #                 except Exception:
# # #                     pass


# # # class MultiCameraManager:
# # #     def __init__(self, cameras, buffer_size=2, fps=15, img_size=(640, 640)):
# # #         self.urls = cameras
# # #         self.img_size = img_size
# # #         self.buffer_size = buffer_size
# # #         self.fps = fps
# # #         self.queues = []
# # #         self.processes = []
# # #         self._stopped = False
# # #         self._no_signal_frames = {}
# # #         self._last_frame_time = {}
# # #         self._current_frames = {}

# # #         self.detectors = [Detector(img_size=img_size) for _ in cameras]

# # #         try:
# # #             self.queues = [mp.Queue(maxsize=buffer_size) for _ in cameras]
# # #         except Exception:
# # #             sys.exit(1)

# # #         try:
# # #             no_signal = make_no_signal_frame(img_size[0], img_size[1])
# # #             for i in range(len(cameras)):
# # #                 self._no_signal_frames[i] = no_signal
# # #                 self._last_frame_time[i] = time.time()
# # #                 self._current_frames[i] = no_signal
# # #         except Exception:
# # #             pass

# # #         try:
# # #             signal.signal(signal.SIGINT, self._shutdown)
# # #             signal.signal(signal.SIGTERM, self._shutdown)
# # #         except Exception:
# # #             pass

# # #         for i, url in enumerate(self.urls):
# # #             try:
# # #                 p = StreamProcessor(i, url, self.queues[i], self.img_size, self.buffer_size, self.fps)
# # #                 p.daemon = True
# # #                 p.start()
# # #                 self.processes.append(p)
# # #             except Exception:
# # #                 pass

# # #     def _run_inference(self, frame, cam_id):
# # #         h, w = self.img_size[1], self.img_size[0]
# # #         if frame.shape[:2] != (h, w):
# # #             frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
# # #         annotated = self.detectors[cam_id].process_frame(frame)
# # #         label = f"CAM {cam_id}"
# # #         font_scale = max(0.5, self.img_size[0] / 900)
# # #         thickness = max(1, int(font_scale * 2))
# # #         cv2.putText(annotated, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0), thickness, cv2.LINE_AA)
# # #         return annotated

# # #     def _update_frames(self):
# # #         for cam_id, q in enumerate(self.queues):
# # #             latest = None
# # #             try:
# # #                 while not q.empty():
# # #                     try:
# # #                         latest = q.get_nowait()
# # #                     except Exception:
# # #                         break
# # #             except Exception:
# # #                 pass

# # #             if latest is not None:
# # #                 self._last_frame_time[cam_id] = time.time()
# # #                 processed_frame = self._run_inference(latest, cam_id)
# # #                 self._current_frames[cam_id] = processed_frame
# # #             else:
# # #                 elapsed = time.time() - self._last_frame_time.get(cam_id, 0)
# # #                 if elapsed > 2.0:
# # #                     self._current_frames[cam_id] = self._no_signal_frames.get(cam_id)

# # #     def display_streams(self):
# # #         win_w = self.img_size[0] * len(self.urls)
# # #         win_h = self.img_size[1]
# # #         cv2.namedWindow("Multi Camera View", cv2.WINDOW_NORMAL)
# # #         cv2.resizeWindow("Multi Camera View", win_w, win_h)
# # #         delay = max(1, int(1000 / self.fps))

# # #         try:
# # #             while not self._stopped:
# # #                 self._update_frames()
# # #                 frames = []
# # #                 for i in range(len(self.urls)):
# # #                     f = self._current_frames[i]
# # #                     if f is None or f.shape[:2] != (self.img_size[1], self.img_size[0]):
# # #                         f = self._no_signal_frames[i]
# # #                     frames.append(f)
# # #                 combined = np.hstack(frames)
# # #                 cv2.imshow("Multi Camera View", combined)
# # #                 if cv2.waitKey(delay) & 0xFF == ord('q'):
# # #                     break
# # #         except Exception:
# # #             pass
# # #         finally:
# # #             self.stop()
# # #             cv2.destroyAllWindows()

# # #     def stop(self):
# # #         if self._stopped:
# # #             return
# # #         self._stopped = True
# # #         for p in self.processes:
# # #             try:
# # #                 p.running.value = False
# # #             except Exception:
# # #                 pass
# # #         for p in self.processes:
# # #             try:
# # #                 if p.is_alive():
# # #                     os.kill(p.pid, signal.SIGTERM)
# # #             except Exception:
# # #                 pass
# # #         for p in self.processes:
# # #             try:
# # #                 if p.is_alive():
# # #                     p.join(timeout=5)
# # #                     if p.is_alive():
# # #                         p.kill()
# # #                         p.join(timeout=2)
# # #             except Exception:
# # #                 pass
# # #         for q in self.queues:
# # #             try:
# # #                 while not q.empty():
# # #                     try:
# # #                         q.get_nowait()
# # #                     except Exception:
# # #                         break
# # #                 q.close()
# # #                 q.join_thread()
# # #             except Exception:
# # #                 pass
# # #         self.processes.clear()

# # #     def _shutdown(self, sig=None, frame=None):
# # #         try:
# # #             signal.signal(signal.SIGINT, signal.SIG_DFL)
# # #             signal.signal(signal.SIGTERM, signal.SIG_DFL)
# # #         except Exception:
# # #             pass
# # #         self.stop()
# # #         try:
# # #             cv2.destroyAllWindows()
# # #         except Exception:
# # #             pass
# # #         sys.exit(0)
# # # ---------------------------------------------------------------
# # """
# # camera_manager.py

# # All cameras push frames into ONE shared queue.
# # A single linear pipeline processes them in order:

# #   GStreamerCapture(cam_entry) ──┐
# #                                 ├──► [shared_raw_queue]
# #   GStreamerCapture(cam_exit)  ──┘          │
# #                                            ▼
# #                                    DetectorThread
# #                                    (one Detector per cam_name,
# #                                     dispatches by frame tag)
# #                                            │
# #                                     [detect_queue]
# #                                            │
# #                                            ▼
# #                                     GenderThread
# #                                            │
# #                                     [gender_queue]
# #                                            │
# #                                            ▼
# #                                       IOThread
# #                                   (video write + JSON log)
# #                                            │
# #                                     latest_results{}
# #                                            │
# #                                            ▼
# #                                    Main thread Display
# #                                    [cam | floor_map] grid

# # Zone loading
# # ────────────
# # Each cam_name gets its own Detector instance, loaded lazily on first frame:
# #   "cam_entry"  →  Detector("cam_entry")  →  zones_runtime.json["cam_entry"]
# #   "cam_exit"   →  Detector("cam_exit")   →  zones_runtime.json["cam_exit"]

# # Frames are tagged  {"cam": cam_name, "frame": np.ndarray}  so the single
# # DetectorThread dispatches each frame to the correct Detector — no zone
# # cross-talk is possible.
# # """

# # import os
# # os.environ["CUDA_VISIBLE_DEVICES"] = ""
# # os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

# # import json
# # import queue
# # import signal
# # import sys
# # import threading
# # import time

# # import cv2
# # cv2.setNumThreads(2)

# # import gi
# # gi.require_version("Gst", "1.0")
# # from gi.repository import Gst

# # import multiprocessing as mp
# # import numpy as np

# # try:
# #     import torch
# #     torch.set_num_threads(2)
# #     torch.set_num_interop_threads(1)
# # except ImportError:
# #     pass

# # from model import Detector

# # # ─── TUNING ───────────────────────────────────────────────────────────────────

# # RAW_QUEUE_SIZE    = 8     # shared raw queue (all cameras combined)
# # DETECT_QUEUE_SIZE = 4
# # GENDER_QUEUE_SIZE = 4

# # CAPTURE_FPS   = 8         # max FPS per camera pushed into raw queue
# # INFER_FPS     = 20         # max detector calls/sec across ALL cameras combined
# # DISPLAY_FPS   = 15        # display refresh rate
# # DISPLAY_SCALE = 0.55
# # RECORD_FPS    = 8

# # # Sentinel value pushed by each capture process when its stream ends
# # _DONE = "__DONE__"


# # # ═══════════════════════════════════════════════════════════════════════════════
# # #  STAGE 0 — GStreamer capture  (one mp.Process per camera)
# # #  Every process tags its frames with cam_name before pushing to shared queue.
# # # ═══════════════════════════════════════════════════════════════════════════════
# # def resize_keep_aspect(img, target_w, target_h):
# #     h, w = img.shape[:2]
# #     scale = min(target_w / w, target_h / h)

# #     new_w = int(w * scale)
# #     new_h = int(h * scale)

# #     resized = cv2.resize(img, (new_w, new_h))

# #     canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
# #     y_offset = (target_h - new_h) // 2
# #     x_offset = (target_w - new_w) // 2

# #     canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
# #     return canvas
# # class GStreamerCapture(mp.Process):
# #     """
# #     Reads a FILE or RTSP source and pushes dicts:
# #         {"cam": cam_name, "frame": np.ndarray}
# #     into the SHARED raw_queue.

# #     FILE  → cv2.VideoCapture, throttled to CAPTURE_FPS, loops on EOS.
# #     RTSP  → GStreamer rtspsrc, reconnects on error/EOS.
# #     """

# #     def __init__(self, cam_name: str, source: str,
# #                  raw_queue: mp.Queue, img_size: tuple):
# #         super().__init__(name=f"cap-{cam_name}", daemon=True)
# #         self.cam_name  = cam_name
# #         self.source    = source
# #         self.raw_queue = raw_queue
# #         self.width, self.height = img_size
# #         self.running   = mp.Value("b", True)
# #         self.fullscreen = False
# #         self.fullscreen_cam = None   # camera name
# #         self.fullscreen_type = None  # "video" or "map"
# #         self._last_click_time = 0

# #     def stop(self):
# #         self.running.value = False

# #     def _push(self, frame: np.ndarray):
# #         """Tag frame and push to shared queue; drop oldest if full."""
# #         item = {"cam": self.cam_name, "frame": frame}
# #         if self.raw_queue.full():
# #             try:
# #                 self.raw_queue.get_nowait()
# #             except Exception:
# #                 pass
# #         try:
# #             self.raw_queue.put_nowait(item)
# #         except Exception:
# #             pass

# #     def _resize(self, frame):
# #         return frame
       

# #     # ── FILE source via cv2.VideoCapture ─────────────────────────────────────

# #     def _run_file(self):
# #         cap = cv2.VideoCapture(self.source)
# #         if not cap.isOpened():
# #             print(f"[ERROR] [{self.cam_name}] Cannot open: {self.source}")
# #             return

# #         src_fps  = cap.get(cv2.CAP_PROP_FPS) or 25.0
# #         interval = 1.0 / min(CAPTURE_FPS, src_fps)
# #         print(f"[INFO] [{self.cam_name}] File capture started "
# #               f"({src_fps:.1f} src fps → throttled to {CAPTURE_FPS} fps)")

# #         while self.running.value:
# #             t0 = time.monotonic()
# #             ret, frame = cap.read()
# #             if not ret:
# #                 cap.set(cv2.CAP_PROP_POS_FRAMES, 0)   # loop
# #                 continue
# #             self._push(self._resize(frame))
# #             wait = interval - (time.monotonic() - t0)
# #             if wait > 0:
# #                 time.sleep(wait)

# #         cap.release()
# #         print(f"[INFO] [{self.cam_name}] File capture stopped")

# #     # ── RTSP source via GStreamer ─────────────────────────────────────────────

# #     def _gst_str(self) -> str:
# #         appsink = (
# #             f"videoconvert ! videoscale method=3 ! "
# #             f"video/x-raw,width={self.width},height={self.height},format=BGR ! "
# #             f"appsink name=sink emit-signals=true sync=false max-buffers=2 drop=true"
# #         )
# #         return (
# #             f'rtspsrc location="{self.source}" protocols=tcp '
# #             f'latency=300 retry=3 timeout=5000000 ! '
# #             f'rtph264depay ! h264parse ! avdec_h264 max-threads=2 ! '
# #             f'videorate ! video/x-raw,framerate={CAPTURE_FPS}/1 ! '
# #             f'{appsink}'
# #         )

# #     def _on_sample(self, sink):
# #         try:
# #             sample = sink.emit("pull-sample")
# #             if not sample:
# #                 return Gst.FlowReturn.OK
# #             buf = sample.get_buffer()
# #             ok, mi = buf.map(Gst.MapFlags.READ)
# #             if not ok:
# #                 return Gst.FlowReturn.OK
# #             try:
# #                 frame = np.ndarray(
# #                     (self.height, self.width, 3),
# #                     buffer=mi.data, dtype=np.uint8).copy()
# #                 self._push(frame)
# #             finally:
# #                 buf.unmap(mi)
# #         except Exception:
# #             pass
# #         return Gst.FlowReturn.OK

# #     def _run_rtsp(self):
# #         Gst.init(None)
# #         print(f"[INFO] [{self.cam_name}] RTSP capture started <- {self.source}")
# #         pipeline = None
# #         while self.running.value:
# #             try:
# #                 pipeline = Gst.parse_launch(self._gst_str())
# #                 sink = pipeline.get_by_name("sink")
# #                 sink.connect("new-sample", self._on_sample)
# #                 if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
# #                     raise RuntimeError("PLAYING failed")
# #                 bus = pipeline.get_bus()
# #                 while self.running.value:
# #                     msg = bus.timed_pop(100 * Gst.MSECOND)
# #                     if msg and msg.type in (Gst.MessageType.ERROR,
# #                                             Gst.MessageType.EOS):
# #                         break
# #             except Exception as e:
# #                 print(f"[WARN] [{self.cam_name}] RTSP error: {e}")
# #             finally:
# #                 if pipeline:
# #                     pipeline.set_state(Gst.State.NULL)
# #                     pipeline = None
# #             if self.running.value:
# #                 time.sleep(3)
# #         print(f"[INFO] [{self.cam_name}] RTSP capture stopped")

# #     # ── Process entry ─────────────────────────────────────────────────────────

# #     def run(self):
# #         signal.signal(signal.SIGINT,  signal.SIG_IGN)
# #         signal.signal(signal.SIGTERM,
# #                       lambda s, f: setattr(self.running, "value", False))
# #         if self.source.lower().startswith("rtsp://"):
# #             self._run_rtsp()
# #         else:
# #             self._run_file()
# #         # Push per-camera sentinel so DetectorThread knows this cam is done
# #         try:
# #             self.raw_queue.put({"cam": self.cam_name, "frame": _DONE}, timeout=3)
# #         except Exception:
# #             pass


# # # ═══════════════════════════════════════════════════════════════════════════════
# # #  STAGE 1 — Detector thread  (single thread, handles ALL cameras)
# # # ═══════════════════════════════════════════════════════════════════════════════

# # class DetectorThread(threading.Thread):
# #     """
# #     Pulls tagged frames from the shared raw_queue one at a time.

# #     Maintains a dict of  cam_name → Detector — loaded lazily on the first
# #     frame from each camera.  This ensures every camera gets its own isolated
# #     Detector with the correct zones from zones_runtime.json[cam_name].

# #     Pushes result dicts into detect_queue.
# #     """

# #     def __init__(self, cam_names: list,
# #                  raw_queue: mp.Queue,
# #                  detect_queue: queue.Queue):
# #         super().__init__(name="detector", daemon=True)
# #         self.cam_names    = cam_names
# #         self.raw_queue    = raw_queue
# #         self.detect_queue = detect_queue
# #         self._stop_evt    = threading.Event()
# #         self._detectors: dict = {}        # cam_name → Detector (lazy loaded)
# #         self._done_cams: set  = set()
# #         self._interval = 1.0 / INFER_FPS
# #         cv2.setMouseCallback("Surveillance Grid", self._mouse_callback)

# #     def stop(self):
# #         self._stop_evt.set()

# #     def _get_detector(self, cam_name: str) -> Detector:
# #         """Load Detector for cam_name on first use — zones fully isolated."""
# #         if cam_name not in self._detectors:
# #             print(f"[INFO] [detector] Loading detector for '{cam_name}' ...")
# #             det = Detector(camera_name=cam_name)
# #             zone_names = list(det.zm.zones_pixel.keys())
# #             non_empty  = [z for z in zone_names if len(det.zm.zones_pixel[z]) >= 3]
# #             skipped    = set(zone_names) - set(non_empty)
# #             print(f"[INFO] [detector] '{cam_name}' ready "
# #                   f"| zones: {non_empty}"
# #                   + (f" | skipped empty: {skipped}" if skipped else ""))
# #             self._detectors[cam_name] = det
# #         return self._detectors[cam_name]

# #     def _push(self, item):
# #         try:
# #             self.detect_queue.put_nowait(item)
# #         except queue.Full:
# #             try:
# #                 self.detect_queue.get_nowait()
# #             except queue.Empty:
# #                 pass
# #             try:
# #                 self.detect_queue.put_nowait(item)
# #             except queue.Full:
# #                 pass
# #     def _mouse_callback(self, event, x, y, flags, param):
# #         if event != cv2.EVENT_LBUTTONDOWN:
# #             return

# #         now = time.time()

# #         # detect double click (within 300ms)
# #         if now - self._last_click_time < 0.3:
# #             self._handle_double_click(x, y)

# #         self._last_click_time = now   
# #     def _handle_double_click(self, x, y):
# #         TARGET_H = int(self.img_size[1] * self.display_scale)
# #         TARGET_W = int(self.img_size[0] * self.display_scale)

# #         row_height = TARGET_H + 4  # including separator

# #         row_idx = y // row_height
# #         if row_idx >= len(self.cam_names):
# #             return

# #         cam_name = self.cam_names[row_idx]

# #         # check left or right side
# #         if x < TARGET_W:
# #             clicked_type = "video"
# #         elif x > TARGET_W:
# #             clicked_type = "map"
# #         else:
# #             return

# #         # toggle fullscreen
# #         if self.fullscreen:
# #             self.fullscreen = False
# #             self.fullscreen_cam = None
# #             self.fullscreen_type = None
# #         else:
# #             self.fullscreen = True
# #             self.fullscreen_cam = cam_name
# #             self.fullscreen_type = clicked_type         

# #     def run(self):
# #         print("[INFO] [detector] Detector thread started")

# #         while not self._stop_evt.is_set():
# #             try:
# #                 item = self.raw_queue.get(timeout=1.0)
# #             except Exception:
# #                 continue

# #             cam_name = item.get("cam")
# #             frame    = item.get("frame")

# #             # Per-camera sentinel
# #             if frame is _DONE:
# #                 print(f"[INFO] [detector] '{cam_name}' stream finished")
# #                 self._done_cams.add(cam_name)
# #                 # Propagate sentinel downstream
# #                 self._push({"cam": cam_name, "annotated": _DONE,
# #                             "floor_map": None, "tracks": []})
# #                 if self._done_cams >= set(self.cam_names):
# #                     print("[INFO] [detector] All cameras done — stopping")
# #                     break
# #                 continue

# #             t0 = time.monotonic()
# #             try:
# #                 det = self._get_detector(cam_name)
# #                 annotated, tracks, floor_map = det.process_frame(frame)
# #             except Exception as e:
# #                 print(f"[WARN] [detector] '{cam_name}': {e}")
# #                 time.sleep(0.05)
# #                 continue

# #             self._push({
# #                 "cam":       cam_name,
# #                 "annotated": annotated,
# #                 "floor_map": floor_map,
# #                 "tracks":    tracks,
# #             })

# #             # Rate-limit — never exceed INFER_FPS calls/sec total
# #             time.sleep(max(0.0, self._interval - (time.monotonic() - t0)))

# #         print("[INFO] [detector] Detector thread stopped")


# # # ═══════════════════════════════════════════════════════════════════════════════
# # #  STAGE 2 — Gender thread
# # # ═══════════════════════════════════════════════════════════════════════════════

# # class GenderThread(threading.Thread):
# #     """
# #     Pulls detect_queue items, assigns gender to each track.
# #     Uses a separate cache per camera so track IDs from different cameras
# #     never collide.

# #     Replace _infer_gender() with your actual model call.
# #     """

# #     def __init__(self, cam_names: list,
# #                  detect_queue: queue.Queue,
# #                  gender_queue: queue.Queue):
# #         super().__init__(name="gender", daemon=True)
# #         self.cam_names    = cam_names
# #         self.detect_queue = detect_queue
# #         self.gender_queue = gender_queue
# #         self._stop_evt    = threading.Event()
# #         self._cache: dict = {n: {} for n in cam_names}   # cam → {id → gender}
# #         self._done_cams: set = set()

# #     def stop(self):
# #         self._stop_evt.set()

# #     def _infer_gender(self, crop: np.ndarray) -> str:
# #         """Stub — replace with your actual gender model."""
# #         return "unknown"

# #     def _push(self, item):
# #         try:
# #             self.gender_queue.put_nowait(item)
# #         except queue.Full:
# #             try:
# #                 self.gender_queue.get_nowait()
# #             except queue.Empty:
# #                 pass
# #             try:
# #                 self.gender_queue.put_nowait(item)
# #             except queue.Full:
# #                 pass

# #     def run(self):
# #         print("[INFO] [gender] Gender thread started")

# #         while not self._stop_evt.is_set():
# #             try:
# #                 item = self.detect_queue.get(timeout=1.0)
# #             except queue.Empty:
# #                 continue

# #             cam_name = item["cam"]

# #             if item["annotated"] is _DONE:
# #                 self._done_cams.add(cam_name)
# #                 self._push(item)
# #                 if self._done_cams >= set(self.cam_names):
# #                     break
# #                 continue

# #             cam_cache = self._cache.setdefault(cam_name, {})
# #             for track in item["tracks"]:
# #                 tid = track.get("id")
# #                 if tid is None:
# #                     continue
# #                 if tid not in cam_cache:
# #                     crop = track.get("crop")
# #                     cam_cache[tid] = (
# #                         self._infer_gender(crop)
# #                         if crop is not None and crop.size > 0
# #                         else "unknown"
# #                     )
# #                 track["gender"] = cam_cache[tid]

# #             self._push(item)

# #         print("[INFO] [gender] Gender thread stopped")


# # # ═══════════════════════════════════════════════════════════════════════════════
# # #  STAGE 3 — I/O thread
# # # ═══════════════════════════════════════════════════════════════════════════════

# # class IOThread(threading.Thread):
# #     """
# #     Pulls gender_queue items.
# #     • Writes per-camera .avi files.
# #     • Writes a shared .jsonl log tagged with camera name.
# #     • Exposes get_latest(cam_name) for the display thread.
# #     """

# #     def __init__(self, cam_names: list,
# #                  gender_queue: queue.Queue,
# #                  output_videos: dict,          # {cam_name: path_or_None}
# #                  output_json:   str = None):
# #         super().__init__(name="io", daemon=True)
# #         self.cam_names    = cam_names
# #         self.gender_queue = gender_queue
# #         self.output_videos = output_videos
# #         self.output_json  = output_json
# #         self._stop_evt    = threading.Event()
# #         self._writers: dict = {n: None for n in cam_names}
# #         self._json_fh     = None
# #         self._done_cams: set = set()

# #         # Latest (annotated, floor_map) per camera — read by display thread
# #         self._lock   = threading.Lock()
# #         self._latest: dict = {n: (None, None) for n in cam_names}

# #     def stop(self):
# #         self._stop_evt.set()

# #     def get_latest(self, cam_name: str):
# #         with self._lock:
# #             return self._latest.get(cam_name, (None, None))

# #     def _init_writer(self, cam_name: str, frame: np.ndarray):
# #         path = self.output_videos.get(cam_name)
# #         if not path:
# #             return
# #         h, w   = frame.shape[:2]
# #         fourcc = cv2.VideoWriter_fourcc(*"XVID")
# #         self._writers[cam_name] = cv2.VideoWriter(path, fourcc, RECORD_FPS, (w, h))
# #         print(f"[INFO] [io] Recording '{cam_name}' -> {path}")

# #     def _write_json(self, cam_name: str, tracks: list):
# #         if not self.output_json:
# #             return
# #         if self._json_fh is None:
# #             self._json_fh = open(self.output_json, "a")
# #         record = {"ts": time.time(), "camera": cam_name, "tracks": tracks}
# #         self._json_fh.write(json.dumps(record) + "\n")
# #         self._json_fh.flush()

# #     def run(self):
# #         print("[INFO] [io] I/O thread started")

# #         while not self._stop_evt.is_set():
# #             try:
# #                 item = self.gender_queue.get(timeout=1.0)
# #             except queue.Empty:
# #                 continue

# #             cam_name = item["cam"]

# #             if item["annotated"] is _DONE:
# #                 self._done_cams.add(cam_name)
# #                 if self._done_cams >= set(self.cam_names):
# #                     break
# #                 continue

# #             annotated = item["annotated"]
# #             floor_map = item["floor_map"]
# #             tracks    = item["tracks"]

# #             # Video write
# #             if self.output_videos.get(cam_name):
# #                 if self._writers[cam_name] is None:
# #                     self._init_writer(cam_name, annotated)
# #                 if self._writers[cam_name]:
# #                     self._writers[cam_name].write(annotated)

# #             # JSON log
# #             if self.output_json:
# #                 safe = [{k: v for k, v in t.items() if k != "crop"} for t in tracks]
# #                 self._write_json(cam_name, safe)

# #             # Update display snapshot
# #             with self._lock:
# #                 self._latest[cam_name] = (annotated, floor_map)

# #         # Cleanup
# #         for w in self._writers.values():
# #             if w:
# #                 w.release()
# #         if self._json_fh:
# #             self._json_fh.close()

# #         print("[INFO] [io] I/O thread stopped")


# # # ═══════════════════════════════════════════════════════════════════════════════
# # #  MULTI-CAMERA MANAGER
# # # ═══════════════════════════════════════════════════════════════════════════════

# # def _make_no_signal(width: int, height: int) -> np.ndarray:
# #     frame = np.full((height, width, 3), 30, dtype=np.uint8)
# #     text  = "NO SIGNAL"
# #     font  = cv2.FONT_HERSHEY_SIMPLEX
# #     fs    = width / 400.0
# #     th    = max(2, int(fs * 2))
# #     (tw, fh), _ = cv2.getTextSize(text, font, fs, th)
# #     cv2.putText(frame, text, ((width - tw) // 2, (height + fh) // 2),
# #                 font, fs, (60, 60, 60), th, cv2.LINE_AA)
# #     sp = max(20, width // 32)
# #     for i in range(0, height, sp):
# #         cv2.line(frame, (0, i), (width, i), (50, 50, 50), 1)
# #     for j in range(0, width, sp):
# #         cv2.line(frame, (j, 0), (j, height), (50, 50, 50), 1)
# #     return frame


# # class MultiCameraManager:
# #     """
# #     Wires everything together:
# #       N × GStreamerCapture (each a separate process) → ONE shared raw_queue
# #       ONE DetectorThread → ONE GenderThread → ONE IOThread
# #       Main thread: display loop reading latest results from IOThread
# #     """

# #     def __init__(self, cameras: list,
# #                  img_size:      tuple = (640, 640),
# #                  display_scale: float = DISPLAY_SCALE,
# #                  **_ignored):
# #         self.cameras       = cameras
# #         self.cam_names     = [c["name"] for c in cameras]
# #         self.img_size      = img_size
# #         self.display_scale = display_scale
# #         self._stopped      = False
# #         self._streams_done = False
# #         self._no_signal    = _make_no_signal(*img_size)

# #         # ── ONE shared raw queue (all cameras push here) ──────────────────────
# #         self._raw_queue    = mp.Queue(maxsize=RAW_QUEUE_SIZE)
# #         self._detect_queue = queue.Queue(maxsize=DETECT_QUEUE_SIZE)
# #         self._gender_queue = queue.Queue(maxsize=GENDER_QUEUE_SIZE)

# #         # ── Capture processes ─────────────────────────────────────────────────
# #         self._captures: list = [
# #             GStreamerCapture(c["name"], c["source"], self._raw_queue, img_size)
# #             for c in cameras
# #         ]

# #         # ── Single pipeline threads ───────────────────────────────────────────
# #         self._detector = DetectorThread(
# #             self.cam_names, self._raw_queue, self._detect_queue)

# #         self._gender = GenderThread(
# #             self.cam_names, self._detect_queue, self._gender_queue)

# #         self._io = IOThread(
# #             cam_names     = self.cam_names,
# #             gender_queue  = self._gender_queue,
# #             output_videos = {c["name"]: c.get("output") for c in cameras},
# #             output_json   = None,   # set to a file path to enable JSON logging
# #         )

# #         # Start pipeline threads before capture so they're ready for first frame
# #         self._io.start()
# #         self._gender.start()
# #         self._detector.start()
# #         for cap in self._captures:
# #             cap.start()

# #         try:
# #             signal.signal(signal.SIGINT,  self._shutdown)
# #             signal.signal(signal.SIGTERM, self._shutdown)
# #         except Exception:
# #             pass

# #         cv2.namedWindow("Surveillance Grid", cv2.WINDOW_NORMAL)
# #         print(f"[INFO] {len(cameras)} capture processes → 1 shared queue "
# #               f"→ detector → gender → io")

# #     # ── Display ───────────────────────────────────────────────────────────────

# #     def _scale(self, img: np.ndarray) -> np.ndarray:
# #         return cv2.resize(img, (0, 0),
# #                           fx=self.display_scale, fy=self.display_scale,
# #                           interpolation=cv2.INTER_LINEAR)

# #     def _compose_grid(self) -> np.ndarray:
# #         SEP = (50, 50, 50)
# #         rows = []

# #         BASE_H = int(480 * self.display_scale)   # choose base height
# #         ASPECT_RATIO = 16 / 9                    # standard video

# #         TARGET_H = BASE_H
# #         TARGET_W = int(BASE_H * ASPECT_RATIO)
# #         for name in self.cam_names:
# #             annotated, floor_map = self._io.get_latest(name)

# #             # fallback if no frame
# #             annotated = annotated if annotated is not None else self._no_signal
# #             floor_map = floor_map if floor_map is not None else self._no_signal

# #             # resize both to SAME size (important fix)
# #             cell_cam = resize_keep_aspect(annotated, TARGET_W, TARGET_H)
# #             cell_map = resize_keep_aspect(floor_map, TARGET_W, TARGET_H)

# #             # combine → 50% video | 50% map
# #             row = np.hstack([
# #                 cell_cam,
# #                 np.full((TARGET_H, 4, 3), SEP, dtype=np.uint8),  # FIXED (was 'h')
# #                 cell_map,
# #             ])

# #             rows.append(row)

# #         if not rows:
# #             return self._no_signal

# #         # make all rows equal width
# #         max_w = max(r.shape[1] for r in rows)
# #         padded = []

# #         for r in rows:
# #             if r.shape[1] < max_w:
# #                 r = np.hstack([
# #                     r,
# #                     np.zeros((r.shape[0], max_w - r.shape[1], 3), dtype=np.uint8)
# #                 ])
# #             padded.append(r)

# #             # separator between rows
# #             padded.append(np.full((4, max_w, 3), SEP, dtype=np.uint8))

# #         return np.vstack(padded[:-1])
# #     def display_streams(self):
# #         delay = max(1, int(1000 / DISPLAY_FPS))
# #         print("[INFO] Pipeline running  --  press  q  to quit")

# #         try:
# #             while not self._stopped:
# #                 if not self._streams_done and all(
# #                         not c.is_alive() for c in self._captures):
# #                     self._streams_done = True
# #                     print("[INFO] All streams finished  --  press  q  to quit")

# #                 # grid = self._compose_grid()
# #                 if self.fullscreen:
# #                     annotated, floor_map = self._io.get_latest(self.fullscreen_cam)

# #                     frame = annotated if self.fullscreen_type == "video" else floor_map
# #                     if frame is None:
# #                         frame = self._no_signal

# #                     grid = cv2.resize(frame, (1280, 720))  # full screen
# #                 else:
# #                     grid = self._compose_grid()

# #                 if self._streams_done:
# #                     h, w = grid.shape[:2]
# #                     msg  = "All streams finished  --  press  q  to quit"
# #                     font = cv2.FONT_HERSHEY_DUPLEX
# #                     (tw, th), _ = cv2.getTextSize(msg, font, 0.65, 1)
# #                     bx, by = max(0, (w - tw) // 2), h - 20
# #                     cv2.rectangle(grid, (bx - 12, by - th - 10),
# #                                   (bx + tw + 12, by + 8), (15, 15, 15), -1)
# #                     cv2.putText(grid, msg, (bx, by), font, 0.65,
# #                                 (60, 220, 120), 1, cv2.LINE_AA)

# #                 cv2.imshow("Surveillance Grid", grid)
# #                 if cv2.waitKey(delay) & 0xFF in (ord("q"), 27):
# #                     print("[INFO] Quit by user")
# #                     break

# #         except KeyboardInterrupt:
# #             print("[INFO] Interrupted")
# #         finally:
# #             self.stop()
# #             cv2.destroyAllWindows()

# #     # ── Shutdown ──────────────────────────────────────────────────────────────

# #     def stop(self):
# #         if self._stopped:
# #             return
# #         self._stopped = True
# #         print("[INFO] Shutting down ...")

# #         # Stop capture first (cut the source)
# #         for cap in self._captures:
# #             try:
# #                 cap.stop()
# #             except Exception:
# #                 pass
# #         for cap in self._captures:
# #             cap.join(timeout=4)
# #             if cap.is_alive():
# #                 cap.kill()
# #                 cap.join(timeout=2)

# #         # Stop pipeline threads in order
# #         self._detector.stop()
# #         self._detector.join(timeout=8)

# #         self._gender.stop()
# #         self._gender.join(timeout=4)

# #         self._io.stop()
# #         self._io.join(timeout=4)

# #         # Drain and close shared queue
# #         try:
# #             while not self._raw_queue.empty():
# #                 self._raw_queue.get_nowait()
# #             self._raw_queue.close()
# #             self._raw_queue.join_thread()
# #         except Exception:
# #             pass

# #         print("[INFO] Finished")

# #     def _shutdown(self, sig=None, frame=None):
# #         try:
# #             signal.signal(signal.SIGINT,  signal.SIG_DFL)
# #             signal.signal(signal.SIGTERM, signal.SIG_DFL)
# #         except Exception:
# #             pass
# #         self.stop()
# #         cv2.destroyAllWindows()
# #         sys.exit(0)
# # ---------------------------------------------------------------
# import os
# os.environ["CUDA_VISIBLE_DEVICES"] = ""
# os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

# import json
# import queue
# import signal
# import sys
# import threading
# import time

# import cv2
# cv2.setNumThreads(2)

# import gi
# gi.require_version("Gst", "1.0")
# from gi.repository import Gst

# import multiprocessing as mp
# import numpy as np

# try:
#     import torch
#     torch.set_num_threads(2)
#     torch.set_num_interop_threads(1)
# except ImportError:
#     pass

# from model import Detector

# # ─── TUNING ─────────────────────────────────────────────
# RAW_QUEUE_SIZE    = 8
# DETECT_QUEUE_SIZE = 4
# GENDER_QUEUE_SIZE = 4

# CAPTURE_FPS = 8
# INFER_FPS   = 20
# DISPLAY_FPS = 15
# DISPLAY_SCALE = 0.55
# RECORD_FPS = 8

# _DONE = "__DONE__"


# # ─── HELPER ─────────────────────────────────────────────
# def resize_keep_aspect(img, target_w, target_h):
#     h, w = img.shape[:2]
#     scale = min(target_w / w, target_h / h)

#     new_w = int(w * scale)
#     new_h = int(h * scale)

#     resized = cv2.resize(img, (new_w, new_h))

#     canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
#     y_offset = (target_h - new_h) // 2
#     x_offset = (target_w - new_w) // 2

#     canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
#     return canvas


# # ─── CAPTURE ────────────────────────────────────────────
# class GStreamerCapture(mp.Process):
#     def __init__(self, cam_name, source, raw_queue, img_size):
#         super().__init__(daemon=True)
#         self.cam_name = cam_name
#         self.source = source
#         self.raw_queue = raw_queue
#         self.running = mp.Value("b", True)

#     def stop(self):
#         self.running.value = False

#     def _push(self, frame):
#         item = {"cam": self.cam_name, "frame": frame}
#         if self.raw_queue.full():
#             try:
#                 self.raw_queue.get_nowait()
#             except:
#                 pass
#         try:
#             self.raw_queue.put_nowait(item)
#         except:
#             pass

#     def run(self):
#         cap = cv2.VideoCapture(self.source)
#         while self.running.value:
#             ret, frame = cap.read()
#             if not ret:
#                 cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
#                 continue
#             self._push(frame)
#         cap.release()


# # ─── DETECTOR THREAD ────────────────────────────────────
# class DetectorThread(threading.Thread):
#     def __init__(self, cam_names, raw_queue, detect_queue):
#         super().__init__(daemon=True)
#         self.cam_names = cam_names
#         self.raw_queue = raw_queue
#         self.detect_queue = detect_queue
#         self._detectors = {}
#         self._interval = 1.0 / INFER_FPS
#         self._stop_evt = threading.Event()

#     def stop(self):
#         self._stop_evt.set()

#     def _get_detector(self, cam_name):
#         if cam_name not in self._detectors:
#             self._detectors[cam_name] = Detector(camera_name=cam_name)
#         return self._detectors[cam_name]

#     def run(self):
#         while not self._stop_evt.is_set():
#             try:
#                 item = self.raw_queue.get(timeout=1)
#             except:
#                 continue

#             cam = item["cam"]
#             frame = item["frame"]

#             t0 = time.monotonic()

#             det = self._get_detector(cam)
#             annotated, tracks, floor_map = det.process_frame(frame)

#             try:
#                 self.detect_queue.put_nowait({
#                     "cam": cam,
#                     "annotated": annotated,
#                     "floor_map": floor_map,
#                     "tracks": tracks
#                 })
#             except:
#                 pass

#             time.sleep(max(0, self._interval - (time.monotonic() - t0)))


# # ─── IO THREAD ──────────────────────────────────────────
# class IOThread(threading.Thread):
#     def __init__(self, cam_names, gender_queue):
#         super().__init__(daemon=True)
#         self.gender_queue = gender_queue
#         self._latest = {n: (None, None) for n in cam_names}
#         self._lock = threading.Lock()

#     def get_latest(self, cam):
#         with self._lock:
#             return self._latest.get(cam, (None, None))

#     def run(self):
#         while True:
#             try:
#                 item = self.gender_queue.get(timeout=1)
#             except:
#                 continue

#             with self._lock:
#                 self._latest[item["cam"]] = (
#                     item["annotated"],
#                     item["floor_map"]
#                 )


# # ─── MANAGER ────────────────────────────────────────────
# class MultiCameraManager:
#     def __init__(self, cameras, img_size=(640,640), display_scale=DISPLAY_SCALE,**kwargs):
#         self.cameras = cameras
#         self.cam_names = [c["name"] for c in cameras]
#         self.display_scale = display_scale
#         self.img_size = img_size

#         self.fullscreen = False
#         self.fullscreen_cam = None
#         self.fullscreen_type = None
#         self._last_click_time = 0

#         self._raw_queue = mp.Queue(RAW_QUEUE_SIZE)
#         self._detect_queue = queue.Queue(DETECT_QUEUE_SIZE)

#         self._captures = [
#             GStreamerCapture(c["name"], c["source"], self._raw_queue, img_size)
#             for c in cameras
#         ]

#         self._detector = DetectorThread(
#             self.cam_names, self._raw_queue, self._detect_queue)

#         self._io = IOThread(self.cam_names, self._detect_queue)

#         self._io.start()
#         self._detector.start()
#         for c in self._captures:
#             c.start()

#         cv2.namedWindow("Surveillance Grid", cv2.WINDOW_NORMAL)
#         cv2.setMouseCallback("Surveillance Grid", self._mouse_callback)

#     # ─── MOUSE ─────────────────────────────
#     def _mouse_callback(self, event, x, y, flags, param):
#         if event != cv2.EVENT_LBUTTONDOWN:
#             return

#         now = time.time()
#         if now - self._last_click_time < 0.3:
#             self._handle_double_click(x, y)

#         self._last_click_time = now

#     def _handle_double_click(self, x, y):
#         BASE_H = int(480 * self.display_scale)
#         TARGET_H = BASE_H
#         TARGET_W = int(BASE_H * (16/9))

#         row = y // (TARGET_H + 4)
#         if row >= len(self.cam_names):
#             return

#         cam = self.cam_names[row]

#         if x < TARGET_W:
#             typ = "video"
#         else:
#             typ = "map"

#         if self.fullscreen:
#             self.fullscreen = False
#         else:
#             self.fullscreen = True
#             self.fullscreen_cam = cam
#             self.fullscreen_type = typ

#     # ─── GRID ─────────────────────────────
#     def _compose_grid(self):
#         rows = []
#         SEP = (50,50,50)

#         BASE_H = int(480 * self.display_scale)
#         TARGET_H = BASE_H
#         TARGET_W = int(BASE_H * (16/9))

#         for cam in self.cam_names:
#             annotated, floor_map = self._io.get_latest(cam)

#             if annotated is None:
#                 annotated = np.zeros((480,640,3), dtype=np.uint8)
#             if floor_map is None:
#                 floor_map = annotated

#             cam_img = resize_keep_aspect(annotated, TARGET_W, TARGET_H)
#             map_img = resize_keep_aspect(floor_map, TARGET_W, TARGET_H)

#             row = np.hstack([
#                 cam_img,
#                 np.full((TARGET_H, 4, 3), SEP, dtype=np.uint8),
#                 map_img
#             ])

#             rows.append(row)

#         return np.vstack(rows)

#     # ─── DISPLAY ──────────────────────────
#     def display_streams(self):
#         delay = int(1000 / DISPLAY_FPS)

#         while True:
#             if self.fullscreen:
#                 annotated, floor_map = self._io.get_latest(self.fullscreen_cam)

#                 frame = annotated if self.fullscreen_type=="video" else floor_map
#                 if frame is None:
#                     frame = np.zeros((480,640,3), dtype=np.uint8)

#                 h, w = frame.shape[:2]
#                 new_w = 1280
#                 new_h = int(new_w * h / w)

#                 grid = cv2.resize(frame, (new_w, new_h))
#             else:
#                 grid = self._compose_grid()

#             cv2.imshow("Surveillance Grid", grid)

#             if cv2.waitKey(delay) & 0xFF in (27, ord('q')):
#                 break

#         cv2.destroyAllWindows()
# ------------------------------------new25--------------------
"""
camera_manager.py

Pipeline
────────
  GStreamerCapture × N  (mp.Process, cv2.VideoCapture, file or RTSP)
       │  raw frames tagged {"cam": name, "frame": ndarray}
       ▼
  shared mp.Queue
       │
  DetectorThread  (threading.Thread)
       │  {"cam", "annotated", "floor_map", "tracks"}
       ▼
  detect_queue (queue.Queue)
       │
  IOThread  (threading.Thread)
       │  latest (annotated, floor_map) per camera
       ▼
  Main thread — display loop
"""

# import os
# os.environ["CUDA_VISIBLE_DEVICES"] = ""
# os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

# # ── NOTE: GStreamer (gi / Gst) is intentionally NOT imported here. ────────────
# # The gi.repository import triggers a native segfault in this OpenVINO +
# # PyTorch environment.  cv2.VideoCapture handles both file and RTSP sources
# # reliably without GStreamer bindings.

# import queue
# import signal
# import sys
# import threading
# import time

# import cv2
# cv2.setNumThreads(2)

# import multiprocessing as mp
# import numpy as np

# try:
#     import torch
#     torch.set_num_threads(2)
#     torch.set_num_interop_threads(1)
# except ImportError:
#     pass

# from model import Detector


# # ─── TUNING ───────────────────────────────────────────────────────────────────

# RAW_QUEUE_SIZE    = 8
# DETECT_QUEUE_SIZE = 4

# CAPTURE_FPS   = 8
# INFER_FPS     = 20
# DISPLAY_FPS   = 15
# DISPLAY_SCALE = 0.55
# RECORD_FPS    = 8


# # ─── HELPERS ──────────────────────────────────────────────────────────────────

# def resize_keep_aspect(img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
#     h, w   = img.shape[:2]
#     scale  = min(target_w / w, target_h / h)
#     new_w  = int(w * scale)
#     new_h  = int(h * scale)
#     canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
#     resized = cv2.resize(img, (new_w, new_h))
#     y0 = (target_h - new_h) // 2
#     x0 = (target_w - new_w) // 2
#     canvas[y0:y0 + new_h, x0:x0 + new_w] = resized
#     return canvas


# def _make_no_signal(width: int, height: int) -> np.ndarray:
#     frame = np.full((height, width, 3), 30, dtype=np.uint8)
#     text  = "NO SIGNAL"
#     font  = cv2.FONT_HERSHEY_SIMPLEX
#     fs    = width / 400.0
#     th    = max(2, int(fs * 2))
#     (tw, fh), _ = cv2.getTextSize(text, font, fs, th)
#     cv2.putText(frame, text,
#                 ((width - tw) // 2, (height + fh) // 2),
#                 font, fs, (60, 60, 60), th, cv2.LINE_AA)
#     sp = max(20, width // 32)
#     for i in range(0, height, sp):
#         cv2.line(frame, (0, i), (width, i), (50, 50, 50), 1)
#     for j in range(0, width, sp):
#         cv2.line(frame, (j, 0), (j, height), (50, 50, 50), 1)
#     return frame


# # ─── STAGE 0 — Capture process ────────────────────────────────────────────────

# class CaptureProcess(mp.Process):
#     """
#     One process per camera.  Uses cv2.VideoCapture for both file and RTSP.
#     Pushes {"cam": cam_name, "frame": ndarray} into the shared raw_queue.
#     Loops on file EOS.  Reconnects on RTSP drop.
#     """

#     def __init__(self, cam_name: str, source: str,
#                  raw_queue: mp.Queue, fps: int = CAPTURE_FPS):
#         super().__init__(daemon=True, name=f"cap-{cam_name}")
#         self.cam_name  = cam_name
#         self.source    = source
#         self.raw_queue = raw_queue
#         self.fps       = fps
#         self.running   = mp.Value("b", True)

#     def stop(self):
#         self.running.value = False

#     def _push(self, frame: np.ndarray):
#         item = {"cam": self.cam_name, "frame": frame}
#         if self.raw_queue.full():
#             try:
#                 self.raw_queue.get_nowait()
#             except Exception:
#                 pass
#         try:
#             self.raw_queue.put_nowait(item)
#         except Exception:
#             pass

#     def run(self):
#         # Ignore Ctrl-C in child — parent handles shutdown
#         signal.signal(signal.SIGINT, signal.SIG_IGN)
#         signal.signal(signal.SIGTERM,
#                       lambda s, f: setattr(self.running, "value", False))

#         interval = 1.0 / self.fps
#         is_rtsp  = self.source.lower().startswith("rtsp://")

#         print(f"[INFO] [{self.cam_name}] Capture started  <- {self.source}")

#         while self.running.value:
#             cap = cv2.VideoCapture(self.source)
#             if not cap.isOpened():
#                 print(f"[WARN] [{self.cam_name}] Cannot open source — retrying in 3 s")
#                 time.sleep(3)
#                 continue

#             src_fps  = cap.get(cv2.CAP_PROP_FPS) or 25.0
#             throttle = 1.0 / min(self.fps, src_fps)

#             while self.running.value:
#                 t0 = time.monotonic()
#                 ret, frame = cap.read()
#                 if not ret:
#                     if is_rtsp:
#                         print(f"[WARN] [{self.cam_name}] RTSP dropped — reconnecting")
#                         break          # outer loop reconnects
#                     else:
#                         cap.set(cv2.CAP_PROP_POS_FRAMES, 0)   # loop file
#                         continue
#                 self._push(frame)
#                 wait = throttle - (time.monotonic() - t0)
#                 if wait > 0:
#                     time.sleep(wait)

#             cap.release()

#             if not is_rtsp:
#                 break   # file finished — don't loop the outer while

#             if self.running.value:
#                 time.sleep(3)   # brief back-off before RTSP reconnect

#         print(f"[INFO] [{self.cam_name}] Capture stopped")


# # ─── STAGE 1 — Detector thread ────────────────────────────────────────────────

# class DetectorThread(threading.Thread):
#     """
#     Pulls tagged frames from raw_queue.
#     Maintains one Detector per camera (lazy-loaded on first frame).
#     Pushes result dicts into detect_queue.
#     """

#     def __init__(self, cam_names: list,
#                  raw_queue:    mp.Queue,
#                  detect_queue: queue.Queue):
#         super().__init__(daemon=True, name="detector")
#         self.cam_names    = cam_names
#         self.raw_queue    = raw_queue
#         self.detect_queue = detect_queue
#         self._detectors: dict = {}
#         self._interval = 1.0 / INFER_FPS
#         self._stop_evt = threading.Event()

#     def stop(self):
#         self._stop_evt.set()

#     def _get_detector(self, cam_name: str) -> Detector:
#         if cam_name not in self._detectors:
#             print(f"[INFO] [detector] Loading Detector for '{cam_name}' ...")
#             self._detectors[cam_name] = Detector(camera_name=cam_name)
#             print(f"[INFO] [detector] '{cam_name}' ready")
#         return self._detectors[cam_name]

#     def _push(self, item: dict):
#         try:
#             self.detect_queue.put_nowait(item)
#         except queue.Full:
#             try:
#                 self.detect_queue.get_nowait()
#             except queue.Empty:
#                 pass
#             try:
#                 self.detect_queue.put_nowait(item)
#             except queue.Full:
#                 pass

#     def run(self):
#         print("[INFO] [detector] Detector thread started")
#         while not self._stop_evt.is_set():
#             try:
#                 item = self.raw_queue.get(timeout=1.0)
#             except Exception:
#                 continue

#             cam_name = item.get("cam")
#             frame    = item.get("frame")
#             if frame is None or cam_name is None:
#                 continue

#             t0 = time.monotonic()
#             try:
#                 det = self._get_detector(cam_name)
#                 annotated, tracks, floor_map = det.process_frame(frame)
#             except Exception as e:
#                 print(f"[WARN] [detector] '{cam_name}': {e}")
#                 time.sleep(0.05)
#                 continue

#             self._push({
#                 "cam":       cam_name,
#                 "annotated": annotated,
#                 "floor_map": floor_map,
#                 "tracks":    tracks,
#             })

#             wait = self._interval - (time.monotonic() - t0)
#             if wait > 0:
#                 time.sleep(wait)

#         print("[INFO] [detector] Detector thread stopped")


# # ─── STAGE 2 — I/O thread ─────────────────────────────────────────────────────

# class IOThread(threading.Thread):
#     """
#     Drains detect_queue and stores the latest (annotated, floor_map) per camera.
#     Optionally writes per-camera .avi files.
#     Display thread reads via get_latest().
#     """

#     def __init__(self, cam_names: list,
#                  detect_queue:  queue.Queue,
#                  output_videos: dict = None,   # {cam_name: path} or None
#                  record_fps:    int  = RECORD_FPS):
#         super().__init__(daemon=True, name="io")
#         self.cam_names     = cam_names
#         self.detect_queue  = detect_queue
#         self.output_videos = output_videos or {}
#         self.record_fps    = record_fps
#         self._stop_evt     = threading.Event()
#         self._lock         = threading.Lock()
#         self._latest: dict = {n: (None, None) for n in cam_names}
#         self._writers: dict = {}

#     def stop(self):
#         self._stop_evt.set()

#     def get_latest(self, cam_name: str):
#         with self._lock:
#             return self._latest.get(cam_name, (None, None))

#     def _get_writer(self, cam_name: str, frame: np.ndarray):
#         if cam_name in self._writers:
#             return self._writers[cam_name]
#         path = self.output_videos.get(cam_name)
#         if not path:
#             self._writers[cam_name] = None
#             return None
#         h, w   = frame.shape[:2]
#         fourcc = cv2.VideoWriter_fourcc(*"XVID")
#         writer = cv2.VideoWriter(path, fourcc, self.record_fps, (w, h))
#         self._writers[cam_name] = writer
#         print(f"[INFO] [io] Recording '{cam_name}' → {path}")
#         return writer

#     def run(self):
#         print("[INFO] [io] I/O thread started")
#         while not self._stop_evt.is_set():
#             try:
#                 item = self.detect_queue.get(timeout=1.0)
#             except queue.Empty:
#                 continue

#             cam_name  = item.get("cam")
#             annotated = item.get("annotated")
#             floor_map = item.get("floor_map")

#             if cam_name is None or annotated is None:
#                 continue

#             # Video write
#             writer = self._get_writer(cam_name, annotated)
#             if writer:
#                 writer.write(annotated)

#             # Update display snapshot
#             with self._lock:
#                 self._latest[cam_name] = (annotated, floor_map)

#         # Release writers on exit
#         for w in self._writers.values():
#             if w:
#                 w.release()
#         print("[INFO] [io] I/O thread stopped")


# # ─── MULTI-CAMERA MANAGER ─────────────────────────────────────────────────────

# class MultiCameraManager:
#     """
#     Wires everything together and owns the display loop.
#     """

#     def __init__(self, cameras: list,
#                  buffer_size:   int   = RAW_QUEUE_SIZE,
#                  fps:           int   = CAPTURE_FPS,
#                  img_size:      tuple = (640, 640),
#                  display_scale: float = DISPLAY_SCALE,
#                  record_fps:    int   = RECORD_FPS,
#                  **_ignored):
#         self.cameras       = cameras
#         self.cam_names     = [c["name"] for c in cameras]
#         self.img_size      = img_size
#         self.display_scale = display_scale
#         self._stopped      = False
#         self._no_signal    = _make_no_signal(*img_size)

#         # Fullscreen state
#         self.fullscreen       = False
#         self.fullscreen_cam   = None
#         self.fullscreen_type  = None   # "video" or "map"
#         self._last_click_time = 0.0

#         # ── Queues ────────────────────────────────────────────────────────────
#         self._raw_queue    = mp.Queue(maxsize=buffer_size)
#         self._detect_queue = queue.Queue(maxsize=DETECT_QUEUE_SIZE)

#         # ── Capture processes ─────────────────────────────────────────────────
#         self._captures = [
#             CaptureProcess(c["name"], c["source"], self._raw_queue, fps)
#             for c in cameras
#         ]

#         # ── Pipeline threads ──────────────────────────────────────────────────
#         self._detector = DetectorThread(
#             self.cam_names, self._raw_queue, self._detect_queue)

#         self._io = IOThread(
#             cam_names     = self.cam_names,
#             detect_queue  = self._detect_queue,
#             output_videos = {c["name"]: c.get("output") for c in cameras},
#             record_fps    = record_fps,
#         )

#         # Start threads before processes so they're ready for first frame
#         self._io.start()
#         self._detector.start()
#         for cap in self._captures:
#             cap.start()

#         # Signal handlers
#         try:
#             signal.signal(signal.SIGINT,  self._shutdown)
#             signal.signal(signal.SIGTERM, self._shutdown)
#         except Exception:
#             pass

#         cv2.namedWindow("Surveillance Grid", cv2.WINDOW_NORMAL)
#         cv2.setMouseCallback("Surveillance Grid", self._mouse_callback)
#         print(f"[INFO] {len(cameras)} camera(s) started  —  press  q  to quit")

#     # ── Mouse callbacks ───────────────────────────────────────────────────────

#     def _mouse_callback(self, event, x, y, flags, param):
#         if event != cv2.EVENT_LBUTTONDOWN:
#             return
#         now = time.time()
#         if now - self._last_click_time < 0.35:
#             self._handle_double_click(x, y)
#         self._last_click_time = now

#     def _handle_double_click(self, x, y):
#         BASE_H   = int(480 * self.display_scale)
#         TARGET_W = int(BASE_H * 16 / 9)
#         row      = y // (BASE_H + 4)
#         if row >= len(self.cam_names):
#             return
#         if self.fullscreen:
#             self.fullscreen = False
#         else:
#             self.fullscreen      = True
#             self.fullscreen_cam  = self.cam_names[row]
#             self.fullscreen_type = "video" if x < TARGET_W else "map"

#     # ── Grid composition ──────────────────────────────────────────────────────

#     def _compose_grid(self) -> np.ndarray:
#         SEP      = (50, 50, 50)
#         BASE_H   = int(480 * self.display_scale)
#         TARGET_H = BASE_H
#         TARGET_W = int(BASE_H * 16 / 9)
#         rows     = []

#         for cam in self.cam_names:
#             annotated, floor_map = self._io.get_latest(cam)

#             annotated = annotated if annotated is not None else self._no_signal
#             floor_map = floor_map if floor_map is not None else self._no_signal

#             cam_cell = resize_keep_aspect(annotated, TARGET_W, TARGET_H)
#             map_cell = resize_keep_aspect(floor_map, TARGET_W, TARGET_H)

#             row = np.hstack([
#                 cam_cell,
#                 np.full((TARGET_H, 4, 3), SEP, dtype=np.uint8),
#                 map_cell,
#             ])
#             rows.append(row)
#             rows.append(np.full((4, row.shape[1], 3), SEP, dtype=np.uint8))

#         if not rows:
#             return self._no_signal

#         # Remove trailing separator
#         return np.vstack(rows[:-1])

#     # ── Display loop ──────────────────────────────────────────────────────────

#     def display_streams(self):
#         delay = max(1, int(1000 / DISPLAY_FPS))

#         try:
#             while not self._stopped:
#                 if self.fullscreen and self.fullscreen_cam:
#                     annotated, floor_map = self._io.get_latest(self.fullscreen_cam)
#                     frame = (annotated if self.fullscreen_type == "video"
#                              else floor_map)
#                     if frame is None:
#                         frame = self._no_signal
#                     h, w  = frame.shape[:2]
#                     grid  = cv2.resize(frame, (1280, int(1280 * h / w)))
#                 else:
#                     grid = self._compose_grid()

#                 cv2.imshow("Surveillance Grid", grid)

#                 key = cv2.waitKey(delay) & 0xFF
#                 if key in (ord("q"), 27):
#                     print("[INFO] Quit by user")
#                     break

#         except KeyboardInterrupt:
#             print("[INFO] Interrupted")
#         finally:
#             self.stop()
#             cv2.destroyAllWindows()

#     # ── Shutdown ──────────────────────────────────────────────────────────────

#     def stop(self):
#         if self._stopped:
#             return
#         self._stopped = True
#         print("[INFO] Shutting down ...")

#         for cap in self._captures:
#             try:
#                 cap.stop()
#             except Exception:
#                 pass
#         for cap in self._captures:
#             cap.join(timeout=4)
#             if cap.is_alive():
#                 cap.kill()
#                 cap.join(timeout=2)

#         self._detector.stop()
#         self._detector.join(timeout=8)

#         self._io.stop()
#         self._io.join(timeout=4)

#         try:
#             while not self._raw_queue.empty():
#                 self._raw_queue.get_nowait()
#             self._raw_queue.close()
#             self._raw_queue.join_thread()
#         except Exception:
#             pass

#         print("[INFO] Shutdown complete")

#     def _shutdown(self, sig=None, frame=None):
#         try:
#             signal.signal(signal.SIGINT,  signal.SIG_DFL)
#             signal.signal(signal.SIGTERM, signal.SIG_DFL)
#         except Exception:
#             pass
#         self.stop()
#         cv2.destroyAllWindows()
#         sys.exit(0)
# -------------------------------------------------------------------
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

import queue
import signal
import sys
import threading
import time
import multiprocessing as mp

import cv2
import numpy as np

# ─── TUNING ───────────────────────────────────────────────────────────────────

FRAME_QUEUE_SIZE = 180  
CAPTURE_FPS      = 10
DISPLAY_FPS      = 10    
DISPLAY_SCALE    = 1.0     

# ─── JPEG ENCODE / DECODE QUALITY ─────────────────────────────────────────────
# BOTTLENECK FIX: Raw 1920x1080 numpy frames (~6 MB each) were being pickled
# and sent through mp.Queue, causing ~hundreds of MB/s of IPC traffic.
# JPEG at quality=75 compresses each frame to ~150-200 KB (a 30x reduction),
# eliminating the queue lock contention and memory pressure that caused
# freezes and crashes under multi-camera load.
JPEG_ENCODE_QUALITY = 75   # 0–100. 75 is visually near-lossless for preview.
JPEG_ENCODE_PARAMS  = [cv2.IMWRITE_JPEG_QUALITY, JPEG_ENCODE_QUALITY]


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def resize_for_preview(img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """
    UI OPTIMIZATION: We use INTER_LINEAR here instead of INTER_AREA. 
    It is slightly softer visually, but takes 1/4th the CPU power, 
    preventing the main UI thread from freezing.
    """
    h, w   = img.shape[:2]
    scale  = min(target_w / w, target_h / h)
    new_w  = int(w * scale)
    new_h  = int(h * scale)
    canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    
    y0 = (target_h - new_h) // 2
    x0 = (target_w - new_w) // 2
    canvas[y0:y0 + new_h, x0:x0 + new_w] = resized
    return canvas

def _make_no_signal(width: int, height: int) -> np.ndarray:
    frame = np.full((height, width, 3), 30, dtype=np.uint8)
    text  = "NO SIGNAL"
    font  = cv2.FONT_HERSHEY_SIMPLEX
    fs    = width / 400.0
    th    = max(2, int(fs * 2))
    (tw, fh), _ = cv2.getTextSize(text, font, fs, th)
    cv2.putText(frame, text,
                ((width - tw) // 2, (height + fh) // 2),
                font, fs, (60, 60, 60), th, cv2.LINE_AA)
    return frame


# ─── STAGE 0 — Capture Workers (Threads inside a Process) ─────────────────────

class SingleCameraReader(threading.Thread):
    def __init__(self, cam_name: str, source: str, frame_queue: mp.Queue, fps: int):
        super().__init__(daemon=True, name=f"thread-{cam_name}")
        self.cam_name    = cam_name
        self.source      = source
        self.frame_queue = frame_queue
        self.fps         = fps

    def _push(self, frame: np.ndarray):
        # ── BOTTLENECK FIX ────────────────────────────────────────────────────
        # Previously: raw numpy array (~6 MB) was pickled into mp.Queue.
        # Now: JPEG-encode to bytes (~150-200 KB) before queuing.
        # This reduces IPC payload by ~30x, eliminating the lock contention
        # and serialization overhead that caused queue stalls and UI freezes.
        ok, buf = cv2.imencode(".jpg", frame, JPEG_ENCODE_PARAMS)
        if not ok:
            return
        # Store compressed bytes; cam name is a small string — no overhead.
        item = {"cam": self.cam_name, "frame": buf.tobytes()}
        # ──────────────────────────────────────────────────────────────────────

        if self.frame_queue.full():
            try:
                self.frame_queue.get_nowait()
            except Exception:
                pass
        try:
            self.frame_queue.put_nowait(item)
        except Exception:
            pass

    def run(self):
        interval = 1.0 / self.fps
        is_rtsp  = self.source.lower().startswith("rtsp://")
        print(f"[INFO] [{self.cam_name}] Capture thread started <- {self.source}")

        while True:
            cap = cv2.VideoCapture(self.source)
            
            if not cap.isOpened():
                print(f"[WARN] [{self.cam_name}] Cannot open source — retrying in 3 s")
                time.sleep(3)
                continue

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            
            # Minimize internal buffer to prevent stale frames on RTSP
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            src_fps  = cap.get(cv2.CAP_PROP_FPS) or 25.0
            throttle = 1.0 / min(self.fps, src_fps)

            while True:
                t0 = time.monotonic()
                
                # ASYNC OPTIMIZATION: grab() is fast and non-blocking. 
                # It tells the hardware to point to the next frame.
                grabbed = cap.grab()
                
                if not grabbed:
                    if is_rtsp:
                        print(f"[WARN] [{self.cam_name}] RTSP dropped — reconnecting")
                        break
                    else:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                
                # retrieve() is the heavy CPU decode. We only do it if grab succeeded.
                ret, frame = cap.retrieve()
                if ret:
                    # ✅ resize BEFORE sending to queue
                    frame = cv2.resize(frame, (640, 360))

                    self._push(frame)
                wait = throttle - (time.monotonic() - t0)
                if wait > 0:
                    time.sleep(max(0, wait))

            cap.release()

            if not is_rtsp:
                break

            time.sleep(3)


class CaptureGroupProcess(mp.Process):
    def __init__(self, group_id: int, cameras: list, frame_queue: mp.Queue, 
                 fps: int, core_id: int, parent_pid: int):
        super().__init__(daemon=True, name=f"cap-group-{group_id}")
        self.group_id    = group_id
        self.cameras     = cameras
        self.frame_queue = frame_queue
        self.fps         = fps
        self.core_id     = core_id
        self.parent_pid  = parent_pid

    def run(self):
        cv2.setNumThreads(1) 
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        
        def parent_monitor():
            while True:
                current_ppid = os.getppid()
                if current_ppid != self.parent_pid or current_ppid == 1:
                    os._exit(1)
                time.sleep(1)

        monitor_thread = threading.Thread(target=parent_monitor, daemon=True)
        monitor_thread.start()

        if self.core_id is not None:
            try:
                os.sched_setaffinity(0, {self.core_id})
                print(f"[INFO] [cap-group-{self.group_id}] Pinned to CPU Core {self.core_id}.")
            except AttributeError:
                pass

        threads = []
        for cam in self.cameras:
            t = SingleCameraReader(cam["name"], cam["source"], self.frame_queue, self.fps)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()


# ─── MULTI-CAMERA MANAGER ─────────────────────────────────────────────────────

class MultiCameraManager:
    def __init__(self, cameras: list,
                 buffer_size:   int   = FRAME_QUEUE_SIZE,
                 fps:           int   = CAPTURE_FPS,
                 img_size:      tuple = (640, 640),
                 display_scale: float = DISPLAY_SCALE,
                 cams_per_core: int   = 6,       
                 start_core_id: int   = 1,
                 **_ignored):
                 
        self.cameras       = cameras
        self.cam_names     = [c["name"] for c in cameras]
        self.img_size      = img_size
        self.display_scale = display_scale
        self._no_signal    = _make_no_signal(*img_size)

        self.frame_queue = mp.Queue(maxsize=buffer_size)
        self._capture_groups = []
        
        # --- NEW: State variables for double-click feature ---
        self.focused_cam = None
        self._cam_bboxes = {}
        self._last_grid_shape = None
        # -----------------------------------------------------
        
        chunks = [cameras[i:i + cams_per_core] for i in range(0, len(cameras), cams_per_core)]
        parent_pid = os.getpid()
        
        for i, chunk in enumerate(chunks):
            target_core = start_core_id + i 
            
            group_proc = CaptureGroupProcess(
                group_id    = i,
                cameras     = chunk,
                frame_queue = self.frame_queue,
                fps         = fps,
                core_id     = target_core,
                parent_pid  = parent_pid        
            )
            self._capture_groups.append(group_proc)

    def start(self):
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        print(f"[INFO] Starting {len(self.cameras)} camera(s) grouped into {len(self._capture_groups)} process(es).")
        for cg in self._capture_groups:
            cg.start()

    def _signal_handler(self, sig, frame):
        self.stop()

    def stop(self):
        print("\n[CRITICAL] Force quitting all capture processes instantly...")
        for cg in self._capture_groups:
            if cg.is_alive():
                cg.kill()

        cv2.destroyAllWindows()
        print("[INFO] Terminated.")
        os._exit(0)

    # --- NEW: Mouse Callback to handle double clicks ---
    def _mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDBLCLK:
            if self.focused_cam is not None:
                # If already focused, double-click returns to grid
                self.focused_cam = None
            else:
                # If in grid mode, find which camera was clicked
                for cam, (x1, y1, x2, y2) in self._cam_bboxes.items():
                    if x1 <= x <= x2 and y1 <= y <= y2:
                        self.focused_cam = cam
                        break

    def _compose_grid(self, latest_frames: dict) -> np.ndarray:
        COLS_PER_ROW = 3
        SEP_COLOR    = (50, 50, 50)
        SEP_THICK     = 4

        BASE_H   = int(480 * self.display_scale)
        TARGET_H = BASE_H
        TARGET_W = int(BASE_H * 16 / 9)
        
        v_sep = np.full((TARGET_H, SEP_THICK, 3), SEP_COLOR, dtype=np.uint8)
        grid_rows = []

        self._cam_bboxes.clear() # Reset bounding boxes for the new frame
        current_y = 0

        for i in range(0, len(self.cam_names), COLS_PER_ROW):
            chunk_names = self.cam_names[i:i + COLS_PER_ROW]
            row_cells = []
            current_x = 0
            
            for j in range(COLS_PER_ROW):
                if j < len(chunk_names):
                    cam = chunk_names[j]
                    frame = latest_frames.get(cam)
                    if frame is None:
                        frame = self._no_signal
                    
                    # Record the bounding box of this camera's grid cell
                    self._cam_bboxes[cam] = (current_x, current_y, current_x + TARGET_W, current_y + TARGET_H)
                else:
                    frame = self._no_signal
                    
                cell = resize_for_preview(frame, TARGET_W, TARGET_H)
                row_cells.append(cell)
                current_x += TARGET_W
                
                if j < COLS_PER_ROW - 1:
                    row_cells.append(v_sep)
                    current_x += SEP_THICK
            
            row_img = np.hstack(row_cells)
            grid_rows.append(row_img)
            current_y += TARGET_H
            
            h_sep = np.full((SEP_THICK, row_img.shape[1], 3), SEP_COLOR, dtype=np.uint8)
            grid_rows.append(h_sep)
            current_y += SEP_THICK

        if not grid_rows:
            return self._no_signal

        return np.vstack(grid_rows[:-1])

    def display_streams(self):
        cv2.namedWindow("Raw Camera Feeds", cv2.WINDOW_NORMAL)
        
        # --- NEW: Bind the mouse callback to the window ---
        cv2.setMouseCallback("Raw Camera Feeds", self._mouse_callback)
        
        delay = max(1, int(1000 / DISPLAY_FPS))
        latest_frames = {name: None for name in self.cam_names}

        try:
            while True:
                drain_count = 0
                MAX_DRAIN = len(self.cam_names)
                latest_raw = {}

                for _ in range(MAX_DRAIN):
                    try:
                        item = self.frame_queue.get_nowait()

                        frame_bytes = np.frombuffer(item["frame"], dtype=np.uint8)
                        decoded     = cv2.imdecode(frame_bytes, cv2.IMREAD_COLOR)

                        if decoded is not None:
                            latest_frames[item["cam"]] = decoded

                    except queue.Empty:
                        break
                # Step 2: Decode only once per camera
                for cam, frame_bytes in latest_raw.items():
                    frame_bytes = np.frombuffer(frame_bytes, dtype=np.uint8)
                    decoded = cv2.imdecode(frame_bytes, cv2.IMREAD_COLOR)

                    if decoded is not None:
                        latest_frames[cam] = decoded    
                # --- NEW: Display logic to toggle full screen ---
                if self.focused_cam is not None:
                    # Show only the focused camera
                    focus_frame = latest_frames.get(self.focused_cam)
                    if focus_frame is None:
                        focus_frame = self._no_signal
                        
                    # Resize it to match the overall grid dimensions so the window 
                    # doesn't drastically snap back and forth in size.
                    if self._last_grid_shape is not None:
                        h, w = self._last_grid_shape[:2]
                        display_img = resize_for_preview(focus_frame, w, h)
                    else:
                        display_img = focus_frame
                else:
                    # Show the normal grid
                    display_img = self._compose_grid(latest_frames)
                    self._last_grid_shape = display_img.shape # Cache shape for stability
                
                cv2.imshow("Raw Camera Feeds", display_img)
                
                if cv2.waitKey(delay) & 0xFF in (ord("q"), 27):
                    print("[INFO] Quit by user")
                    self.stop()
                    
        except KeyboardInterrupt:
            self.stop()