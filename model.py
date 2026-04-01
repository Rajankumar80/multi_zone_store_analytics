# # import cv2
# # import numpy as np
# # import json
# # import time
# # import threading
# # import queue
# # from ultralytics import YOLO
# # from gender_classifier import GenderClassifier
# # from zone import ZoneManager


# # # ─── CONFIGURATION ─────────────────────────────────────────────────────────────

# # ZONE_FILE    = "/home/keshav/rajan/new_pipeline/zones_runtime.json"
# # YOLO_MODEL   = "/home/keshav/rajan/new_pipeline/models/best_openvino_model"
# # GENDER_MODEL = "/home/keshav/rajan/new_pipeline/models/mobilenetv3_gender_best.pth"
# # METRICS_FILE = "zone_metrics.json"
# # EVENTS_FILE  = "zone_events.json"

# # ENTRY_FRAMES = 4
# # EXIT_FRAMES  = 6

# # # Gender cache: re-run inference when age >= TTL or confidence < threshold
# # GENDER_CACHE_TTL    = 30     # frames
# # GENDER_CONF_THRESH  = 0.80

# # # Flush intervals
# # EVENTS_FLUSH_INTERVAL  = 5.0    # seconds
# # METRICS_FLUSH_INTERVAL = 60.0   # seconds

# # # Memory bounds
# # _MAX_EVENT_LOG_FLUSHED  = 500   # trim event_log after this many flushed entries
# # _MAX_METRICS_LOG        = 120   # ~2 hours at 60 s interval
# # _IO_QUEUE_MAXSIZE       = 50    # ~4 min backlog at normal write rate


# # # ─── PALETTE ───────────────────────────────────────────────────────────────────

# # C_WHITE      = (255, 255, 255)
# # C_BLACK      = (0,   0,   0)
# # C_DARK       = (18,  18,  26)
# # C_ACCENT     = (255, 200,  60)
# # C_GREEN      = ( 60, 220, 120)
# # C_RED        = ( 60,  60, 230)
# # C_BBOX       = (  0, 100,   0)   # dark green bounding box
# # C_LABEL_TEXT = (  0, 255,   0)   # bright green label text

# # _ZONE_COLOR_BANK = [
# #     (255, 190,  60),
# #     (100, 220, 100),
# #     ( 60, 160, 255),
# #     (255, 100, 100),
# #     (180,  80, 220),
# #     (  0, 210, 210),
# #     (255, 220,   0),
# #     (255, 140,  40),
# #     (160, 255, 160),
# #     (255, 130, 220),
# # ]


# # # ─── DRAWING HELPERS ───────────────────────────────────────────────────────────

# # def draw_filled_rect_alpha(img, x1, y1, x2, y2, color, alpha=0.55):
# #     """Blit a solid colour rectangle at the given opacity."""
# #     x1, y1 = max(0, x1), max(0, y1)
# #     x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
# #     if x2 <= x1 or y2 <= y1:
# #         return
# #     sub  = img[y1:y2, x1:x2]
# #     rect = np.full(sub.shape, color, dtype=np.uint8)
# #     cv2.addWeighted(rect, alpha, sub, 1 - alpha, 0, sub)
# #     img[y1:y2, x1:x2] = sub


# # def draw_rounded_rect(img, x1, y1, x2, y2, r, color, thickness=2):
# #     """Stroke a rectangle with rounded corners."""
# #     cv2.line(img, (x1+r, y1),   (x2-r, y1),   color, thickness)
# #     cv2.line(img, (x1+r, y2),   (x2-r, y2),   color, thickness)
# #     cv2.line(img, (x1,   y1+r), (x1,   y2-r), color, thickness)
# #     cv2.line(img, (x2,   y1+r), (x2,   y2-r), color, thickness)
# #     cv2.ellipse(img, (x1+r, y1+r), (r, r), 180, 0, 90, color, thickness)
# #     cv2.ellipse(img, (x2-r, y1+r), (r, r), 270, 0, 90, color, thickness)
# #     cv2.ellipse(img, (x1+r, y2-r), (r, r),  90, 0, 90, color, thickness)
# #     cv2.ellipse(img, (x2-r, y2-r), (r, r),   0, 0, 90, color, thickness)


# # def draw_label_with_bg(img, text, x, y, text_color=C_WHITE,
# #                        bg_color=C_DARK, font_scale=0.5, thickness=1, pad=6):
# #     """Draw text with a semi-transparent dark backing rectangle."""
# #     font = cv2.FONT_HERSHEY_DUPLEX
# #     (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
# #     draw_filled_rect_alpha(img,
# #                            x - pad, y - th - pad,
# #                            x + tw + pad, y + pad,
# #                            bg_color, alpha=0.75)
# #     cv2.putText(img, text, (x, y), font, font_scale,
# #                 text_color, thickness, cv2.LINE_AA)


# # # ─── DETECTOR ──────────────────────────────────────────────────────────────────

# # class Detector:
# #     """
# #     Full tracking pipeline with two background threads.

# #     Threading model
# #     ───────────────
# #     Main thread   — YOLO track → zone hysteresis → read gender cache
# #                     → draw frame → return result every frame, no waiting.

# #     Gender thread — receives (frame, boxes, ids) via _gender_queue,
# #                     runs batched inference for stale/new tracks only,
# #                     writes results into _gender_cache under _cache_lock.
# #                     Never touches zone logic or frame drawing.

# #     I/O thread    — drains _io_queue, writes JSON files to disk.
# #                     Never blocks the main thread.

# #     Key invariants
# #     ──────────────
# #     - YOLO tracker state is single-threaded (main thread only).
# #     - Zone entry/exit counts and confirmed_inside are single-threaded.
# #     - Gender labels are display-only — a 1-frame lag is invisible.
# #     - All background threads survive exceptions (try/except/finally).
# #     - No background thread can crash or freeze the main video loop.
# #     """

# #     def __init__(self, camera_name="cam_entry"):
# #         # ── Models ────────────────────────────────────────────────────────────
# #         self.model        = YOLO(YOLO_MODEL)
# #         self.gender_model = GenderClassifier(GENDER_MODEL)

# #         # ── Zone manager ──────────────────────────────────────────────────────
# #         with open(ZONE_FILE) as f:
# #             camera_data = json.load(f)[camera_name]

# #         self.zm = ZoneManager(
# #             camera_data,
# #             entry_frames = ENTRY_FRAMES,
# #             exit_frames  = EXIT_FRAMES,
# #         )

# #         # One display colour per zone
# #         self.zone_color = {
# #             name: _ZONE_COLOR_BANK[idx % len(_ZONE_COLOR_BANK)]
# #             for idx, name in enumerate(self.zm.zones_pixel)
# #         }

# #         # ── Gender cache ──────────────────────────────────────────────────────
# #         # Written by gender thread (under _cache_lock).
# #         # Read by main thread without a lock — CPython dict .get() is atomic.
# #         self._gender_cache = {}    # tid → {"label": str, "confidence": float, "age": int}
# #         self._cache_lock   = threading.Lock()

# #         # ── Queues ────────────────────────────────────────────────────────────
# #         # maxsize=1: if gender thread is busy, drop the job — cached label is fine.
# #         self._gender_queue = queue.Queue(maxsize=1)
# #         # maxsize=_IO_QUEUE_MAXSIZE: bounded so a slow disk can't OOM the process.
# #         self._io_queue     = queue.Queue(maxsize=_IO_QUEUE_MAXSIZE)

# #         # ── Event / metrics logs ──────────────────────────────────────────────
# #         self.event_log          = []
# #         self._flushed_count     = 0
# #         self.metrics_log        = []
# #         self._last_metrics      = 0.0
# #         self._last_events_flush = 0.0

# #         # ── Pre-allocated static floor map canvas ─────────────────────────────
# #         # Grid, zone outlines, title bar and legend are drawn once at startup.
# #         # Every frame only adds the per-frame dynamic elements on a copy.
# #         self.MAP_SCALE     = 150
# #         self.MAP_W         = 900
# #         self.MAP_H         = 750
# #         self._floor_canvas = np.zeros((self.MAP_H, self.MAP_W, 3), dtype=np.uint8)
# #         self._build_floor_base()

# #         # ── Start background threads ──────────────────────────────────────────
# #         threading.Thread(target=self._gender_worker, daemon=True).start()
# #         threading.Thread(target=self._io_worker,     daemon=True).start()

# #     # =========================================================================
# #     # Gender thread
# #     # =========================================================================

# #     def _gender_worker(self):
# #         """
# #         Waits for a (frame, boxes, ids) job.
# #         Runs batched GPU inference only for stale/new/uncertain tracks.
# #         Writes results into _gender_cache under _cache_lock.
# #         task_done() is guaranteed even on exception so the queue never jams.
# #         """
# #         while True:
# #             job = self._gender_queue.get()
# #             if job is None:                    # shutdown sentinel
# #                 self._gender_queue.task_done()
# #                 break

# #             try:
# #                 frame, boxes, ids = job

# #                 # Snapshot the cache under the lock (very fast — dict copy)
# #                 with self._cache_lock:
# #                     cache_snapshot = dict(self._gender_cache)

# #                 # Classify each track: fresh (use cache) or stale (need inference)
# #                 stale_idx, stale_boxes = [], []
# #                 for i, tid in enumerate(ids):
# #                     cached = cache_snapshot.get(tid)
# #                     if (cached is not None
# #                             and cached["age"] < GENDER_CACHE_TTL
# #                             and cached["confidence"] >= GENDER_CONF_THRESH):
# #                         # Fresh — increment age in live cache; no GPU work needed
# #                         with self._cache_lock:
# #                             if tid in self._gender_cache:
# #                                 self._gender_cache[tid]["age"] += 1
# #                     else:
# #                         stale_idx.append(i)
# #                         stale_boxes.append(boxes[i])

# #                 # One batched forward pass for all stale/new tracks
# #                 if stale_boxes:
# #                     preds = self.gender_model.predict(frame, stale_boxes)
# #                     with self._cache_lock:
# #                         for list_pos, orig_i in enumerate(stale_idx):
# #                             tid = ids[orig_i]
# #                             self._gender_cache[tid] = {
# #                                 "label":      preds[list_pos]["label"],
# #                                 "confidence": preds[list_pos]["confidence"],
# #                                 "age":        0,
# #                             }

# #                 # Evict tracks that are no longer in this job's frame
# #                 active = set(ids)
# #                 with self._cache_lock:
# #                     for tid in list(self._gender_cache.keys()):
# #                         if tid not in active:
# #                             del self._gender_cache[tid]

# #             except Exception as e:
# #                 # Log but never let the thread die
# #                 print(f"[WARN] gender worker error: {e}")
# #             finally:
# #                 self._gender_queue.task_done()

# #     # =========================================================================
# #     # I/O thread
# #     # =========================================================================

# #     def _io_worker(self):
# #         """
# #         Drains _io_queue and writes JSON to disk.
# #         Catches all exceptions so the thread never dies silently.
# #         task_done() fires in finally so the queue never jams.
# #         """
# #         while True:
# #             filepath, data = self._io_queue.get()
# #             try:
# #                 with open(filepath, "w") as f:
# #                     # default=str handles any non-serialisable types gracefully
# #                     json.dump(data, f, indent=2, default=str)
# #             except Exception as e:
# #                 print(f"[WARN] I/O write failed ({filepath}): {e}")
# #             finally:
# #                 self._io_queue.task_done()

# #     def _enqueue_write(self, filepath, data):
# #         """
# #         Post a write job — returns immediately, never blocks, never crashes.
# #         If the I/O queue is full (disk saturated) the write is silently dropped
# #         with a warning. A skipped write is always better than a crashed process.
# #         """
# #         try:
# #             self._io_queue.put_nowait((filepath, data))
# #         except queue.Full:
# #             print(f"[WARN] I/O queue full — dropping write to {filepath}")

# #     # =========================================================================
# #     # Floor map — static base built once at startup
# #     # =========================================================================

# #     def _build_floor_base(self):
# #         """
# #         Draw the parts of the floor map that never change:
# #         metric grid, zone outlines, title bar, legend.
# #         Called once in __init__. Every frame copies this and draws dots on top.
# #         """
# #         self._floor_canvas[:] = (22, 22, 30)

# #         # Metric grid
# #         for x in range(0, self.MAP_W, self.MAP_SCALE):
# #             cv2.line(self._floor_canvas, (x, 0), (x, self.MAP_H), (45, 45, 55), 1)
# #             cv2.putText(self._floor_canvas, f"{x // self.MAP_SCALE}m",
# #                         (x + 3, 13), cv2.FONT_HERSHEY_DUPLEX, 0.3, (80, 80, 100), 1)
# #         for y in range(0, self.MAP_H, self.MAP_SCALE):
# #             cv2.line(self._floor_canvas, (0, y), (self.MAP_W, y), (45, 45, 55), 1)
# #             cv2.putText(self._floor_canvas, f"{y // self.MAP_SCALE}m",
# #                         (3, y + 13), cv2.FONT_HERSHEY_DUPLEX, 0.3, (80, 80, 100), 1)

# #         # Zone outlines (positions never change)
# #         for name, poly_world in self.zm.zones_world.items():
# #             if len(poly_world) < 3:
# #                 continue
# #             color = self.zone_color[name]
# #             pts   = np.array(
# #                 [[int(p[0] * self.MAP_SCALE), int(p[1] * self.MAP_SCALE)]
# #                  for p in poly_world], dtype=np.int32)
# #             cv2.polylines(self._floor_canvas, [pts], True, color, 2, cv2.LINE_AA)

# #         # Title bar
# #         cv2.rectangle(self._floor_canvas, (0, 0), (self.MAP_W, 24), (30, 30, 40), -1)
# #         cv2.line(self._floor_canvas, (0, 24), (self.MAP_W, 24), C_ACCENT, 1)
# #         cv2.putText(self._floor_canvas, "STORE FLOOR MAP  —  bird's-eye view",
# #                     (self.MAP_W // 2 - 155, 17),
# #                     cv2.FONT_HERSHEY_DUPLEX, 0.46, C_ACCENT, 1)

# #         # Legend
# #         lx, ly = self.MAP_W - 140, self.MAP_H - 52
# #         draw_filled_rect_alpha(self._floor_canvas,
# #                                lx - 8, ly - 14, self.MAP_W - 6, self.MAP_H - 6,
# #                                C_DARK, alpha=0.70)
# #         cv2.circle(self._floor_canvas, (lx + 6, ly),     5, (180, 180, 180), -1)
# #         cv2.putText(self._floor_canvas, "open area", (lx + 16, ly + 4),
# #                     cv2.FONT_HERSHEY_DUPLEX, 0.36, (180, 180, 180), 1)
# #         cv2.circle(self._floor_canvas, (lx + 6, ly + 22), 5, C_GREEN, -1)
# #         cv2.putText(self._floor_canvas, "in zone",   (lx + 16, ly + 26),
# #                     cv2.FONT_HERSHEY_DUPLEX, 0.36, C_GREEN, 1)

# #     # =========================================================================
# #     # Drawing helpers — called from main thread every frame
# #     # =========================================================================

# #     def _draw_hud(self, output):
# #         """Top-left stats panel: ZONE | NOW | ENTRY | EXIT per zone."""
# #         font    = cv2.FONT_HERSHEY_DUPLEX
# #         pad     = 14
# #         row_h   = 36
# #         col_w   = 110
# #         label_w = 115
# #         n_zones = len(self.zm.zones_pixel)
# #         panel_w = label_w + 3 * col_w + 2 * pad
# #         panel_h = pad + 28 + n_zones * row_h + pad

# #         draw_filled_rect_alpha(output, 10, 10,
# #                                10 + panel_w, 10 + panel_h, C_DARK, alpha=0.72)
# #         cv2.rectangle(output, (10, 10),
# #                       (10 + panel_w, 10 + panel_h), C_ACCENT, 1)

# #         hx, hy = 10 + pad, 10 + pad + 16
# #         for title, offset in zip(
# #             ["ZONE", "NOW", "ENTRY", "EXIT"],
# #             [0, label_w, label_w + col_w, label_w + 2 * col_w],
# #         ):
# #             cv2.putText(output, title, (hx + offset, hy),
# #                         font, 0.42, C_ACCENT, 1, cv2.LINE_AA)

# #         div_y = 10 + pad + 22
# #         cv2.line(output, (10 + pad, div_y),
# #                  (10 + panel_w - pad, div_y), C_ACCENT, 1)

# #         for i, zone in enumerate(self.zm.zones_pixel):
# #             ry      = div_y + 8 + (i + 1) * row_h - 6
# #             inside  = len(self.zm.confirmed_inside[zone])
# #             entries = self.zm.zone_entry_count[zone]
# #             exits   = self.zm.zone_exit_count[zone]
# #             z_color = self.zone_color[zone]

# #             cv2.circle(output, (hx + 6, ry - 5), 5, z_color, -1)
# #             cv2.putText(output, zone.upper(),
# #                         (hx + 18, ry), font, 0.44, z_color, 1, cv2.LINE_AA)
# #             cv2.putText(output, str(inside),
# #                         (hx + label_w + 30, ry), font, 0.55,
# #                         C_GREEN if inside > 0 else C_WHITE, 1, cv2.LINE_AA)
# #             cv2.putText(output, str(entries),
# #                         (hx + label_w + col_w + 20, ry),
# #                         font, 0.55, C_GREEN, 1, cv2.LINE_AA)
# #             cv2.putText(output, str(exits),
# #                         (hx + label_w + 2 * col_w + 20, ry),
# #                         font, 0.55, C_RED, 1, cv2.LINE_AA)

# #     def _draw_zones(self, output):
# #         """Zone boundary polylines with name labels. No transparent fill."""
# #         for name, poly in self.zm.zones_pixel.items():
# #             if len(poly) < 3:
# #                 continue
# #             pts   = np.array(poly, dtype=np.int32)
# #             color = self.zone_color[name]
# #             cv2.polylines(output, [pts], True, color, 2, cv2.LINE_AA)
# #             cx = int(np.mean([p[0] for p in poly]))
# #             cy = int(np.mean([p[1] for p in poly]))
# #             draw_label_with_bg(output, name.upper(), cx - 30, cy,
# #                                text_color=color, bg_color=C_DARK)

# #     def _draw_track(self, output, track):
# #         """
# #         Dark-green thin bounding box + foot dot.
# #         Label above the box (falls back to below if too close to top edge).
# #         Both left and right label edges are clamped to frame bounds.
# #         """
# #         x1, y1, x2, y2 = track["bbox"]
# #         gender_label    = track.get("gender", "?")

# #         # Bounding box and foot dot
# #         cv2.rectangle(output, (x1, y1), (x2, y2), C_BBOX, 1)
# #         cv2.circle(output, track["foot"], 4, C_BBOX, -1)

# #         # Label positioning
# #         label = f"ID {track['id']} | {gender_label}"
# #         font  = cv2.FONT_HERSHEY_SIMPLEX
# #         (tw, th), _ = cv2.getTextSize(label, font, 0.5, 1)

# #         # Place above bbox; if too close to top edge place below instead
# #         if y1 - th - 8 >= 0:
# #             lx, ly = x1, y1
# #         else:
# #             lx, ly = x1, y2 + th + 8

# #         # Clamp both horizontal edges to frame bounds
# #         lx = max(0, lx)
# #         rx = min(output.shape[1], lx + tw + 6)

# #         cv2.rectangle(output, (lx, ly - th - 8), (rx, ly), C_BLACK, -1)
# #         cv2.putText(output, label, (lx + 3, ly - 4),
# #                     font, 0.5, C_LABEL_TEXT, 1, cv2.LINE_AA)

# #     def _draw_floor_map(self, tracks):
# #         """
# #         Copy the static base canvas and draw per-frame dynamic elements:
# #         live zone stats (NOW/E/X) and person dots.
# #         """
# #         floor_map = self._floor_canvas.copy()

# #         # Live zone stats
# #         for name, poly_world in self.zm.zones_world.items():
# #             if len(poly_world) < 3:
# #                 continue
# #             color = self.zone_color[name]
# #             pts   = np.array(
# #                 [[int(p[0] * self.MAP_SCALE), int(p[1] * self.MAP_SCALE)]
# #                  for p in poly_world], dtype=np.int32)
# #             cx = int(np.mean(pts[:, 0]))
# #             cy = int(np.mean(pts[:, 1]))
# #             cv2.putText(floor_map, name.upper(),
# #                         (cx - 34, cy - 24),
# #                         cv2.FONT_HERSHEY_DUPLEX, 0.45, color, 1)
# #             cv2.putText(floor_map, f"NOW {len(self.zm.confirmed_inside[name])}",
# #                         (cx - 38, cy),
# #                         cv2.FONT_HERSHEY_DUPLEX, 0.40, C_GREEN, 1)
# #             cv2.putText(floor_map, f"E:{self.zm.zone_entry_count[name]}",
# #                         (cx - 38, cy + 20),
# #                         cv2.FONT_HERSHEY_DUPLEX, 0.38, (120, 255, 120), 1)
# #             cv2.putText(floor_map, f"X:{self.zm.zone_exit_count[name]}",
# #                         (cx + 14, cy + 20),
# #                         cv2.FONT_HERSHEY_DUPLEX, 0.38, (80, 80, 230), 1)

# #         # Person dots
# #         for track in tracks:
# #             wp = self.zm.pixel_to_world(track["foot"][0], track["foot"][1])
# #             if wp is None:
# #                 continue
# #             mx = int(wp[0] * self.MAP_SCALE)
# #             my = int(wp[1] * self.MAP_SCALE)
# #             if not (0 <= mx < self.MAP_W and 0 <= my < self.MAP_H):
# #                 continue
# #             dot_col = C_GREEN if track["zones"] else (180, 180, 180)
# #             cv2.circle(floor_map, (mx, my), 8, dot_col, -1)
# #             cv2.circle(floor_map, (mx, my), 9, C_WHITE,  1)
# #             cv2.putText(floor_map, str(track["id"]),
# #                         (mx + 11, my + 4),
# #                         cv2.FONT_HERSHEY_DUPLEX, 0.38, dot_col, 1)

# #         return floor_map

# #     # =========================================================================
# #     # Main per-frame entry point
# #     # =========================================================================

# #     def process_frame(self, frame):
# #         """
# #         Called from the video loop on every captured frame.
# #         Runs entirely on the main thread. Returns immediately without waiting
# #         for any background thread.

# #         Steps
# #         -----
# #         1. YOLO tracking  — produces bounding boxes + tracker IDs
# #         2. Zone hysteresis — updates entry/exit state and event log
# #         3. Gender cache read — reads last known label (may be 1 frame stale)
# #         4. Gender job post — drops job into queue non-blocking (skip if busy)
# #         5. Gender cache eviction — remove entries for vanished tracks immediately
# #         6. Draw — zones, tracks, HUD, floor map
# #         7. Periodic I/O — flush events and metrics to background thread
# #         8. Return (annotated_frame, tracks, floor_map)
# #         """
# #         now = time.time()

# #         # ── 1. YOLO ───────────────────────────────────────────────────────────
# #         results = self.model.track(
# #             frame,
# #             persist = True,
# #             classes = 0,
# #             conf    = 0.1,
# #             iou     = 0.7,
# #             tracker = "botsort.yaml",
# #             verbose = False,
# #         )

# #         result     = results[0]
# #         output     = frame.copy()
# #         active_ids = set()
# #         tracks     = []

# #         if result.boxes is not None and result.boxes.id is not None:
# #             boxes = result.boxes.xyxy.cpu().numpy()
# #             ids   = result.boxes.id.cpu().numpy().astype(int)

# #             for box, tid in zip(boxes, ids):
# #                 x1, y1, x2, y2 = box.astype(int)
# #                 cx, cy          = int((x1 + x2) / 2), int(y2)
# #                 foot_pixel      = (cx, cy)
# #                 active_ids.add(tid)
# #                 world_pt        = self.zm.pixel_to_world(cx, cy)

# #                 # ── 2. Zone hysteresis ────────────────────────────────────────
# #                 person_zones = []
# #                 # AFTER
# #                 for zone_name in self.zm.zones_pixel:
# #                     if len(self.zm.zones_pixel[zone_name]) < 3:   # ← add this line
# #                         raw_inside = False
# #                     elif world_pt is not None and len(self.zm.zones_world[zone_name]) >= 3:
# #                         raw_inside = (
# #                             cv2.pointPolygonTest(
# #                                 np.array(self.zm.zones_world[zone_name], np.float32),
# #                                 tuple(world_pt), False,
# #                             ) >= 0
# #                         )
# #                     else:
# #                         raw_inside = (
# #                             cv2.pointPolygonTest(
# #                                 np.array(self.zm.zones_pixel[zone_name], np.float32),
# #                                 foot_pixel, False,
# #                             ) >= 0
# #                         )               
# #                     self.zm.apply_hysteresis(tid, zone_name, raw_inside,
# #                                              now, self.event_log)
# #                     if tid in self.zm.confirmed_inside[zone_name]:
# #                         person_zones.append(zone_name)

# #                 # ── 3. Gender cache read (CPython dict.get is atomic) ─────────
# #                 cached = self._gender_cache.get(tid)
# #                 gender = cached["label"] if cached else "?"

# #                 tracks.append({
# #                     "id":     tid,
# #                     "bbox":   (x1, y1, x2, y2),
# #                     "foot":   foot_pixel,
# #                     "zones":  person_zones,
# #                     "gender": gender,
# #                 })

# #             # ── 4. Post gender job — non-blocking, drop if thread is busy ─────
# #             if not self._gender_queue.full():
# #                 try:
# #                     self._gender_queue.put_nowait((frame.copy(), boxes, ids))
# #                 except queue.Full:
# #                     pass   # race between full() check and put_nowait — harmless

# #         # ── Cleanup lost tracks ───────────────────────────────────────────────
# #         self.zm.cleanup_lost_tracks(active_ids, now, self.event_log)

# #         # ── 5. Evict gender cache for vanished tracks (main thread, immediate) ─
# #         # The gender worker evicts based on the most recent job's ids, which is
# #         # 1 frame old. This eviction runs on the current frame's active_ids,
# #         # preventing a reused tracker ID from inheriting a stale cached label.
# #         with self._cache_lock:
# #             for tid in list(self._gender_cache.keys()):
# #                 if tid not in active_ids:
# #                     del self._gender_cache[tid]

# #         # ── 6. Draw ───────────────────────────────────────────────────────────
# #         self._draw_zones(output)
# #         for track in tracks:
# #             self._draw_track(output, track)
# #         self._draw_hud(output)
# #         floor_map = self._draw_floor_map(tracks)

# #         # ── 7. Periodic I/O ───────────────────────────────────────────────────
# #         if now - self._last_events_flush >= EVENTS_FLUSH_INTERVAL:
# #             new_events = self.event_log[self._flushed_count:]
# #             if new_events:
# #                 self._enqueue_write(EVENTS_FILE, {"events": new_events})
# #                 self._flushed_count = len(self.event_log)
# #             # Trim the already-flushed prefix to keep memory bounded
# #             if self._flushed_count > _MAX_EVENT_LOG_FLUSHED:
# #                 del self.event_log[:self._flushed_count]
# #                 self._flushed_count = 0
# #             self._last_events_flush = now

# #         if now - self._last_metrics >= METRICS_FLUSH_INTERVAL:
# #             log = {"time": self.zm.fmt_ts(now)}
# #             for zone in self.zm.zones_pixel:
# #                 log[zone] = {
# #                     "current": len(self.zm.confirmed_inside[zone]),
# #                     "entries": self.zm.zone_entry_count[zone],
# #                     "exits":   self.zm.zone_exit_count[zone],
# #                 }
# #             self.metrics_log.append(log)
# #             if len(self.metrics_log) > _MAX_METRICS_LOG:
# #                 self.metrics_log = self.metrics_log[-_MAX_METRICS_LOG:]
# #             self._enqueue_write(METRICS_FILE, self.metrics_log)
# #             self._last_metrics = now

# #         # ── 8. Return ─────────────────────────────────────────────────────────
# #         return output, tracks, floor_map
# # ---------------------------------------------------------

# import cv2
# import numpy as np
# import json
# import time
# import threading
# import queue
# from ultralytics import YOLO
# from gender_classifier import GenderClassifier
# from zone import ZoneManager
# import supervision as sv


# # ─── CONFIGURATION ─────────────────────────────────────────────────────────────

# ZONE_FILE    = "/home/keshav/rajan/new_pipeline/zones_runtime.json"
# YOLO_MODEL   = "yolov8n_openvino_model"   # exported OpenVINO dir
# GENDER_MODEL = "/home/keshav/rajan/new_pipeline/models/mobilenetv3_gender_best.pth"
# METRICS_FILE = "zone_metrics.json"
# EVENTS_FILE  = "zone_events.json"

# ENTRY_FRAMES = 4
# EXIT_FRAMES  = 6

# # Gender cache: re-run inference when age >= TTL or confidence < threshold
# GENDER_CACHE_TTL   = 30    # frames
# GENDER_CONF_THRESH = 0.80

# # Flush intervals
# EVENTS_FLUSH_INTERVAL  = 5.0   # seconds
# METRICS_FLUSH_INTERVAL = 60.0  # seconds

# # Memory bounds
# _MAX_EVENT_LOG_FLUSHED = 500
# _MAX_METRICS_LOG       = 120
# _IO_QUEUE_MAXSIZE      = 50


# # ─── PALETTE ───────────────────────────────────────────────────────────────────

# C_WHITE      = (255, 255, 255)
# C_BLACK      = (0,   0,   0)
# C_DARK       = (18,  18,  26)
# C_ACCENT     = (255, 200,  60)
# C_GREEN      = ( 60, 220, 120)
# C_RED        = ( 60,  60, 230)
# C_BBOX       = (  0, 100,   0)
# C_LABEL_TEXT = (  0, 255,   0)

# _ZONE_COLOR_BANK = [
#     (255, 190,  60),
#     (100, 220, 100),
#     ( 60, 160, 255),
#     (255, 100, 100),
#     (180,  80, 220),
#     (  0, 210, 210),
#     (255, 220,   0),
#     (255, 140,  40),
#     (160, 255, 160),
#     (255, 130, 220),
# ]


# # ─── DRAWING HELPERS ───────────────────────────────────────────────────────────

# def draw_filled_rect_alpha(img, x1, y1, x2, y2, color, alpha=0.55):
#     x1, y1 = max(0, x1), max(0, y1)
#     x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
#     if x2 <= x1 or y2 <= y1:
#         return
#     sub  = img[y1:y2, x1:x2]
#     rect = np.full(sub.shape, color, dtype=np.uint8)
#     cv2.addWeighted(rect, alpha, sub, 1 - alpha, 0, sub)
#     img[y1:y2, x1:x2] = sub


# def draw_rounded_rect(img, x1, y1, x2, y2, r, color, thickness=2):
#     cv2.line(img, (x1+r, y1),   (x2-r, y1),   color, thickness)
#     cv2.line(img, (x1+r, y2),   (x2-r, y2),   color, thickness)
#     cv2.line(img, (x1,   y1+r), (x1,   y2-r), color, thickness)
#     cv2.line(img, (x2,   y1+r), (x2,   y2-r), color, thickness)
#     cv2.ellipse(img, (x1+r, y1+r), (r, r), 180, 0, 90, color, thickness)
#     cv2.ellipse(img, (x2-r, y1+r), (r, r), 270, 0, 90, color, thickness)
#     cv2.ellipse(img, (x1+r, y2-r), (r, r),  90, 0, 90, color, thickness)
#     cv2.ellipse(img, (x2-r, y2-r), (r, r),   0, 0, 90, color, thickness)


# def draw_label_with_bg(img, text, x, y, text_color=C_WHITE,
#                        bg_color=C_DARK, font_scale=0.5, thickness=1, pad=6):
#     font = cv2.FONT_HERSHEY_DUPLEX
#     (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
#     draw_filled_rect_alpha(img,
#                            x - pad, y - th - pad,
#                            x + tw + pad, y + pad,
#                            bg_color, alpha=0.75)
#     cv2.putText(img, text, (x, y), font, font_scale,
#                 text_color, thickness, cv2.LINE_AA)


# # ─── DETECTOR ──────────────────────────────────────────────────────────────────

# class Detector:
#     """
#     Full tracking pipeline using yolov8n OpenVINO model + sv.ByteTrack.

#     Threading model
#     ───────────────
#     Main thread   — OpenVINO YOLO detect → sv.ByteTrack → zone hysteresis
#                     → gender cache read → draw → return.  No waiting.

#     Gender thread — batched gender inference for stale/new tracks only.
#                     Writes into _gender_cache under _cache_lock.

#     I/O thread    — drains _io_queue, writes JSON to disk.

#     Key invariants
#     ──────────────
#     - model() is called with task="detect" — never .track() (incompatible
#       with OpenVINO IR and causes segfaults).
#     - sv.ByteTrack owns all tracking state on the main thread only.
#     - Zone state is single-threaded (main thread).
#     - Gender labels are display-only; 1-frame lag is invisible.
#     - Background threads never crash or freeze the video loop.
#     """

#     def __init__(self, camera_name="cam_entry"):

#         # ── OpenVINO model ────────────────────────────────────────────────────
#         # Pass the exported directory path.  Ultralytics auto-detects the
#         # OpenVINO IR inside and uses the CPU provider.
#         # task="detect" is mandatory; omitting it can trigger a segfault on
#         # some OpenVINO + Ultralytics version combinations.
#         self.model = YOLO(YOLO_MODEL, task="detect")

#         # Warm-up: compile the IR graph now so the first real frame is fast.
#         dummy = np.zeros((640, 640, 3), dtype=np.uint8)
#         self.model(dummy, verbose=False)

#         # ── ByteTrack ─────────────────────────────────────────────────────────
#         self.tracker = sv.ByteTrack()

#         # ── Gender classifier ─────────────────────────────────────────────────
#         self.gender_model = GenderClassifier(GENDER_MODEL)

#         # ── Zone manager ──────────────────────────────────────────────────────
#         with open(ZONE_FILE) as f:
#             camera_data = json.load(f)[camera_name]

#         self.zm = ZoneManager(
#             camera_data,
#             entry_frames=ENTRY_FRAMES,
#             exit_frames=EXIT_FRAMES,
#         )

#         self.zone_color = {
#             name: _ZONE_COLOR_BANK[idx % len(_ZONE_COLOR_BANK)]
#             for idx, name in enumerate(self.zm.zones_pixel)
#         }

#         # ── Gender cache ──────────────────────────────────────────────────────
#         self._gender_cache = {}   # tid → {"label": str, "confidence": float, "age": int}
#         self._cache_lock   = threading.Lock()

#         # ── Queues ────────────────────────────────────────────────────────────
#         self._gender_queue = queue.Queue(maxsize=1)
#         self._io_queue     = queue.Queue(maxsize=_IO_QUEUE_MAXSIZE)

#         # ── Logs ──────────────────────────────────────────────────────────────
#         self.event_log          = []
#         self._flushed_count     = 0
#         self.metrics_log        = []
#         self._last_metrics      = 0.0
#         self._last_events_flush = 0.0

#         # ── Floor map static canvas ───────────────────────────────────────────
#         self.MAP_SCALE     = 150
#         self.MAP_W         = 900
#         self.MAP_H         = 750
#         self._floor_canvas = np.zeros((self.MAP_H, self.MAP_W, 3), dtype=np.uint8)
#         self._build_floor_base()

#         # ── Background threads ────────────────────────────────────────────────
#         threading.Thread(target=self._gender_worker, daemon=True).start()
#         threading.Thread(target=self._io_worker,     daemon=True).start()

#     # =========================================================================
#     # Gender thread
#     # =========================================================================

#     def _gender_worker(self):
#         """
#         Job payload: (frame, boxes, ids)
#             boxes — np.ndarray (N, 4) float32  xyxy pixel coords
#             ids   — np.ndarray (N,)   int       ByteTrack IDs
#         """
#         while True:
#             job = self._gender_queue.get()
#             if job is None:
#                 self._gender_queue.task_done()
#                 break
#             try:
#                 frame, boxes, ids = job

#                 with self._cache_lock:
#                     cache_snapshot = dict(self._gender_cache)

#                 stale_idx, stale_boxes = [], []
#                 for i, tid in enumerate(ids):
#                     cached = cache_snapshot.get(tid)
#                     if (cached is not None
#                             and cached["age"] < GENDER_CACHE_TTL
#                             and cached["confidence"] >= GENDER_CONF_THRESH):
#                         with self._cache_lock:
#                             if tid in self._gender_cache:
#                                 self._gender_cache[tid]["age"] += 1
#                     else:
#                         stale_idx.append(i)
#                         stale_boxes.append(boxes[i])

#                 if stale_boxes:
#                     preds = self.gender_model.predict(frame, stale_boxes)
#                     with self._cache_lock:
#                         for list_pos, orig_i in enumerate(stale_idx):
#                             tid = ids[orig_i]
#                             self._gender_cache[tid] = {
#                                 "label":      preds[list_pos]["label"],
#                                 "confidence": preds[list_pos]["confidence"],
#                                 "age":        0,
#                             }

#                 active = set(ids)
#                 with self._cache_lock:
#                     for tid in list(self._gender_cache.keys()):
#                         if tid not in active:
#                             del self._gender_cache[tid]

#             except Exception as e:
#                 print(f"[WARN] gender worker error: {e}")
#             finally:
#                 self._gender_queue.task_done()

#     # =========================================================================
#     # I/O thread
#     # =========================================================================

#     def _io_worker(self):
#         while True:
#             filepath, data = self._io_queue.get()
#             try:
#                 with open(filepath, "w") as f:
#                     json.dump(data, f, indent=2, default=str)
#             except Exception as e:
#                 print(f"[WARN] I/O write failed ({filepath}): {e}")
#             finally:
#                 self._io_queue.task_done()

#     def _enqueue_write(self, filepath, data):
#         try:
#             self._io_queue.put_nowait((filepath, data))
#         except queue.Full:
#             print(f"[WARN] I/O queue full — dropping write to {filepath}")

#     # =========================================================================
#     # Floor map static base
#     # =========================================================================

#     def _build_floor_base(self):
#         self._floor_canvas[:] = (22, 22, 30)

#         for x in range(0, self.MAP_W, self.MAP_SCALE):
#             cv2.line(self._floor_canvas, (x, 0), (x, self.MAP_H), (45, 45, 55), 1)
#             cv2.putText(self._floor_canvas, f"{x // self.MAP_SCALE}m",
#                         (x + 3, 13), cv2.FONT_HERSHEY_DUPLEX, 0.3, (80, 80, 100), 1)
#         for y in range(0, self.MAP_H, self.MAP_SCALE):
#             cv2.line(self._floor_canvas, (0, y), (self.MAP_W, y), (45, 45, 55), 1)
#             cv2.putText(self._floor_canvas, f"{y // self.MAP_SCALE}m",
#                         (3, y + 13), cv2.FONT_HERSHEY_DUPLEX, 0.3, (80, 80, 100), 1)

#         for name, poly_world in self.zm.zones_world.items():
#             if len(poly_world) < 3:
#                 continue
#             color = self.zone_color[name]
#             pts = np.array(
#                 [[int(p[0] * self.MAP_SCALE), int(p[1] * self.MAP_SCALE)]
#                  for p in poly_world], dtype=np.int32)
#             cv2.polylines(self._floor_canvas, [pts], True, color, 2, cv2.LINE_AA)

#         cv2.rectangle(self._floor_canvas, (0, 0), (self.MAP_W, 24), (30, 30, 40), -1)
#         cv2.line(self._floor_canvas, (0, 24), (self.MAP_W, 24), C_ACCENT, 1)
#         cv2.putText(self._floor_canvas, "STORE FLOOR MAP  —  bird's-eye view",
#                     (self.MAP_W // 2 - 155, 17),
#                     cv2.FONT_HERSHEY_DUPLEX, 0.46, C_ACCENT, 1)

#         lx, ly = self.MAP_W - 140, self.MAP_H - 52
#         draw_filled_rect_alpha(self._floor_canvas,
#                                lx - 8, ly - 14, self.MAP_W - 6, self.MAP_H - 6,
#                                C_DARK, alpha=0.70)
#         cv2.circle(self._floor_canvas, (lx + 6, ly),      5, (180, 180, 180), -1)
#         cv2.putText(self._floor_canvas, "open area", (lx + 16, ly + 4),
#                     cv2.FONT_HERSHEY_DUPLEX, 0.36, (180, 180, 180), 1)
#         cv2.circle(self._floor_canvas, (lx + 6, ly + 22), 5, C_GREEN, -1)
#         cv2.putText(self._floor_canvas, "in zone",   (lx + 16, ly + 26),
#                     cv2.FONT_HERSHEY_DUPLEX, 0.36, C_GREEN, 1)

#     # =========================================================================
#     # Per-frame drawing helpers
#     # =========================================================================

#     def _draw_hud(self, output):
#         font    = cv2.FONT_HERSHEY_DUPLEX
#         pad     = 14
#         row_h   = 36
#         col_w   = 110
#         label_w = 115
#         n_zones = len(self.zm.zones_pixel)
#         panel_w = label_w + 3 * col_w + 2 * pad
#         panel_h = pad + 28 + n_zones * row_h + pad

#         draw_filled_rect_alpha(output, 10, 10,
#                                10 + panel_w, 10 + panel_h, C_DARK, alpha=0.72)
#         cv2.rectangle(output, (10, 10),
#                       (10 + panel_w, 10 + panel_h), C_ACCENT, 1)

#         hx, hy = 10 + pad, 10 + pad + 16
#         for title, offset in zip(
#             ["ZONE", "NOW", "ENTRY", "EXIT"],
#             [0, label_w, label_w + col_w, label_w + 2 * col_w],
#         ):
#             cv2.putText(output, title, (hx + offset, hy),
#                         font, 0.42, C_ACCENT, 1, cv2.LINE_AA)

#         div_y = 10 + pad + 22
#         cv2.line(output, (10 + pad, div_y),
#                  (10 + panel_w - pad, div_y), C_ACCENT, 1)

#         for i, zone in enumerate(self.zm.zones_pixel):
#             ry      = div_y + 8 + (i + 1) * row_h - 6
#             inside  = len(self.zm.confirmed_inside[zone])
#             entries = self.zm.zone_entry_count[zone]
#             exits   = self.zm.zone_exit_count[zone]
#             z_color = self.zone_color[zone]

#             cv2.circle(output, (hx + 6, ry - 5), 5, z_color, -1)
#             cv2.putText(output, zone.upper(),
#                         (hx + 18, ry), font, 0.44, z_color, 1, cv2.LINE_AA)
#             cv2.putText(output, str(inside),
#                         (hx + label_w + 30, ry), font, 0.55,
#                         C_GREEN if inside > 0 else C_WHITE, 1, cv2.LINE_AA)
#             cv2.putText(output, str(entries),
#                         (hx + label_w + col_w + 20, ry),
#                         font, 0.55, C_GREEN, 1, cv2.LINE_AA)
#             cv2.putText(output, str(exits),
#                         (hx + label_w + 2 * col_w + 20, ry),
#                         font, 0.55, C_RED, 1, cv2.LINE_AA)

#     def _draw_zones(self, output):
#         for name, poly in self.zm.zones_pixel.items():
#             if len(poly) < 3:
#                 continue
#             pts   = np.array(poly, dtype=np.int32)
#             color = self.zone_color[name]
#             cv2.polylines(output, [pts], True, color, 2, cv2.LINE_AA)
#             cx = int(np.mean([p[0] for p in poly]))
#             cy = int(np.mean([p[1] for p in poly]))
#             draw_label_with_bg(output, name.upper(), cx - 30, cy,
#                                text_color=color, bg_color=C_DARK)

#     def _draw_track(self, output, track):
#         x1, y1, x2, y2 = track["bbox"]
#         gender_label    = track.get("gender", "?")

#         cv2.rectangle(output, (x1, y1), (x2, y2), C_BBOX, 1)
#         cv2.circle(output, track["foot"], 4, C_BBOX, -1)

#         label = f"ID {track['id']} | {gender_label}"
#         font  = cv2.FONT_HERSHEY_SIMPLEX
#         (tw, th), _ = cv2.getTextSize(label, font, 0.5, 1)

#         if y1 - th - 8 >= 0:
#             lx, ly = x1, y1
#         else:
#             lx, ly = x1, y2 + th + 8

#         lx = max(0, lx)
#         rx = min(output.shape[1], lx + tw + 6)

#         cv2.rectangle(output, (lx, ly - th - 8), (rx, ly), C_BLACK, -1)
#         cv2.putText(output, label, (lx + 3, ly - 4),
#                     font, 0.5, C_LABEL_TEXT, 1, cv2.LINE_AA)

#     def _draw_floor_map(self, tracks):
#         floor_map = self._floor_canvas.copy()

#         for name, poly_world in self.zm.zones_world.items():
#             if len(poly_world) < 3:
#                 continue
#             color = self.zone_color[name]
#             pts = np.array(
#                 [[int(p[0] * self.MAP_SCALE), int(p[1] * self.MAP_SCALE)]
#                  for p in poly_world], dtype=np.int32)
#             cx = int(np.mean(pts[:, 0]))
#             cy = int(np.mean(pts[:, 1]))
#             cv2.putText(floor_map, name.upper(),
#                         (cx - 34, cy - 24),
#                         cv2.FONT_HERSHEY_DUPLEX, 0.45, color, 1)
#             cv2.putText(floor_map, f"NOW {len(self.zm.confirmed_inside[name])}",
#                         (cx - 38, cy),
#                         cv2.FONT_HERSHEY_DUPLEX, 0.40, C_GREEN, 1)
#             cv2.putText(floor_map, f"E:{self.zm.zone_entry_count[name]}",
#                         (cx - 38, cy + 20),
#                         cv2.FONT_HERSHEY_DUPLEX, 0.38, (120, 255, 120), 1)
#             cv2.putText(floor_map, f"X:{self.zm.zone_exit_count[name]}",
#                         (cx + 14, cy + 20),
#                         cv2.FONT_HERSHEY_DUPLEX, 0.38, (80, 80, 230), 1)

#         for track in tracks:
#             wp = self.zm.pixel_to_world(track["foot"][0], track["foot"][1])
#             if wp is None:
#                 continue
#             mx = int(wp[0] * self.MAP_SCALE)
#             my = int(wp[1] * self.MAP_SCALE)
#             if not (0 <= mx < self.MAP_W and 0 <= my < self.MAP_H):
#                 continue
#             dot_col = C_GREEN if track["zones"] else (180, 180, 180)
#             cv2.circle(floor_map, (mx, my), 8, dot_col, -1)
#             cv2.circle(floor_map, (mx, my), 9, C_WHITE,  1)
#             cv2.putText(floor_map, str(track["id"]),
#                         (mx + 11, my + 4),
#                         cv2.FONT_HERSHEY_DUPLEX, 0.38, dot_col, 1)

#         return floor_map

#     # =========================================================================
#     # Main per-frame entry point
#     # =========================================================================

#     def process_frame(self, frame):
#         """
#         Steps
#         -----
#         1. OpenVINO detect  — model() on CPU, no .track(), no persist
#         2. sv.ByteTrack     — assigns stable IDs from raw detections
#         3. Zone hysteresis  — updates entry/exit state and event log
#         4. Gender cache read
#         5. Gender job post  — non-blocking, skip if thread busy
#         6. Gender cache eviction for vanished tracks
#         7. Draw
#         8. Periodic I/O flush
#         9. Return (annotated_frame, tracks, floor_map)
#         """
#         now    = time.time()
#         output = frame.copy()

#         # ── 1. OpenVINO inference ─────────────────────────────────────────────
#         # NEVER call .track() with an OpenVINO model — it triggers a segfault
#         # because Ultralytics' built-in tracker attempts CUDA ops on a CPU IR.
#         results = self.model(
#             frame,
#             conf=0.1,
#             iou=0.7,
#             classes=0,      # person only
#             verbose=False,
#         )
#         result = results[0]

#         active_ids = set()
#         tracks     = []

#         if result.boxes is not None and len(result.boxes) > 0:

#             # ── 2. ByteTrack ──────────────────────────────────────────────────
#             detections = sv.Detections.from_ultralytics(result)
#             tracked    = self.tracker.update_with_detections(detections)

#             if tracked.tracker_id is not None and len(tracked) > 0:
#                 boxes = tracked.xyxy                        # (N,4) float32
#                 ids   = tracked.tracker_id.astype(int)      # (N,)  int

#                 for i in range(len(tracked)):
#                     x1, y1, x2, y2 = boxes[i].astype(int)
#                     tid             = ids[i]
#                     cx, cy          = int((x1 + x2) / 2), int(y2)
#                     foot_pixel      = (cx, cy)

#                     active_ids.add(tid)
#                     world_pt = self.zm.pixel_to_world(cx, cy)

#                     # ── 3. Zone hysteresis ────────────────────────────────────
#                     person_zones = []
#                     for zone_name in self.zm.zones_pixel:
#                         zone_poly_px = self.zm.zones_pixel[zone_name]
#                         if len(zone_poly_px) < 3:
#                             raw_inside = False
#                         elif world_pt is not None and len(self.zm.zones_world[zone_name]) >= 3:
#                             raw_inside = (
#                                 cv2.pointPolygonTest(
#                                     np.array(self.zm.zones_world[zone_name], np.float32),
#                                     tuple(world_pt), False,
#                                 ) >= 0
#                             )
#                         else:
#                             raw_inside = (
#                                 cv2.pointPolygonTest(
#                                     np.array(zone_poly_px, np.float32),
#                                     foot_pixel, False,
#                                 ) >= 0
#                             )

#                         self.zm.apply_hysteresis(tid, zone_name, raw_inside,
#                                                  now, self.event_log)
#                         if tid in self.zm.confirmed_inside[zone_name]:
#                             person_zones.append(zone_name)

#                     # ── 4. Gender cache read ──────────────────────────────────
#                     cached = self._gender_cache.get(tid)
#                     gender = cached["label"] if cached else "?"

#                     tracks.append({
#                         "id":     tid,
#                         "bbox":   (x1, y1, x2, y2),
#                         "foot":   foot_pixel,
#                         "zones":  person_zones,
#                         "gender": gender,
#                     })

#                 # ── 5. Post gender job ────────────────────────────────────────
#                 if not self._gender_queue.full():
#                     try:
#                         self._gender_queue.put_nowait((frame.copy(), boxes, ids))
#                     except queue.Full:
#                         pass

#         # ── Cleanup lost tracks ───────────────────────────────────────────────
#         self.zm.cleanup_lost_tracks(active_ids, now, self.event_log)

#         # ── 6. Evict stale gender cache entries ───────────────────────────────
#         with self._cache_lock:
#             for tid in list(self._gender_cache.keys()):
#                 if tid not in active_ids:
#                     del self._gender_cache[tid]

#         # ── 7. Draw ───────────────────────────────────────────────────────────
#         self._draw_zones(output)
#         for track in tracks:
#             self._draw_track(output, track)
#         self._draw_hud(output)
#         floor_map = self._draw_floor_map(tracks)

#         # ── 8. Periodic I/O ───────────────────────────────────────────────────
#         if now - self._last_events_flush >= EVENTS_FLUSH_INTERVAL:
#             new_events = self.event_log[self._flushed_count:]
#             if new_events:
#                 self._enqueue_write(EVENTS_FILE, {"events": new_events})
#                 self._flushed_count = len(self.event_log)
#             if self._flushed_count > _MAX_EVENT_LOG_FLUSHED:
#                 del self.event_log[:self._flushed_count]
#                 self._flushed_count = 0
#             self._last_events_flush = now

#         if now - self._last_metrics >= METRICS_FLUSH_INTERVAL:
#             log = {"time": self.zm.fmt_ts(now)}
#             for zone in self.zm.zones_pixel:
#                 log[zone] = {
#                     "current": len(self.zm.confirmed_inside[zone]),
#                     "entries": self.zm.zone_entry_count[zone],
#                     "exits":   self.zm.zone_exit_count[zone],
#                 }
#             self.metrics_log.append(log)
#             if len(self.metrics_log) > _MAX_METRICS_LOG:
#                 self.metrics_log = self.metrics_log[-_MAX_METRICS_LOG:]
#             self._enqueue_write(METRICS_FILE, self.metrics_log)
#             self._last_metrics = now

#         # ── 9. Return ─────────────────────────────────────────────────────────
#         return output, tracks, floor_map
# ---------------------------------------------------------------------------------
"""
model.py  —  Strict per-core multiprocessing inference pipeline
================================================================

CPU core layout
───────────────
  Core 0      Main process — display loop  (pinned in main.py)
  Cores 1-2   DetectionProcess — YOLOv8n OpenVINO + ByteTrack
                OpenVINO can use both cores for parallel IR execution.
  Core 3      GenderProcess — MobileNetV3 gender classifier
  Core 4      ZoneProcess   — ZoneManager hysteresis + annotation drawing
  Core 5      IOProcess     — asyncio event loop for all JSON file writes

Inter-process queues  (all mp.Queue — truly cross-process, no shared memory)
─────────────────────────────────────────────────────────────────────────────
  frame_queue      mp.Queue  ← written by CaptureGroupProcesses (camera_manager)
  detection_queue  mp.Queue  ← written by DetectionProcess
  gender_queue     mp.Queue  ← written by GenderProcess
  zone_queue       mp.Queue  ← written by ZoneProcess  (read by display loop)
  io_queue         mp.Queue  ← written by ZoneProcess  (read by IOProcess)

Queue item schemas
──────────────────
  frame_queue      {"cam": str, "frame": bytes}                JPEG 640×360
  detection_queue  {"cam": str, "frame": bytes,                JPEG pass-through
                    "tracks": list[TrackD], "timestamp": float}
  gender_queue     {"cam": str, "frame": bytes,
                    "tracks": list[TrackDG], "timestamp": float}
  zone_queue       {"cam": str, "annotated_frame": bytes,      JPEG annotated
                    "floor_map": bytes, "timestamp": float}    JPEG floor map
  io_queue         {"filepath": str, "data": object}           JSON payload

  TrackD  = {"id": int, "bbox": (x1,y1,x2,y2), "foot": (cx,cy)}
  TrackDG = TrackD  + {"gender": "M"|"F"|"?"}
  TrackDGZ= TrackDG + {"zones": list[str]}

Non-blocking guarantee
──────────────────────
  _mp_put() drops the OLDEST item when a queue is full.
  No process ever blocks waiting for a downstream consumer.
  The pipeline always carries the freshest available frame.

Key invariants
──────────────
  • YOLO: task="detect" — NEVER .track(). .track() triggers a segfault on
    OpenVINO CPU IR because it calls CUDA ops internally.
  • All models are loaded inside process.run() — NEVER in __init__().
    With "spawn" start method, __init__ executes in the parent process;
    run() executes in the freshly spawned child.
  • ByteTrack: one instance per camera per DetectionProcess.
  • Gender cache key: (cam, tid) — track IDs isolated across cameras.
  • ZoneManager state: mutated only by ZoneProcess (zero-lock zone logic).
  • ZoneManager's own dwell-writer daemon thread runs inside ZoneProcess
    and writes zone_dwell_{cam}.json directly (not through io_queue).
"""

from __future__ import annotations

import asyncio
import cv2
import json
import multiprocessing as mp
import numpy as np
import os
import queue as _queue        # stdlib queue — used for Full/Empty exceptions only
import signal
import threading
import time


# ─── CONFIGURATION ─────────────────────────────────────────────────────────────

ZONE_FILE    = "/home/keshav/rajan/new_pipeline/zones_runtime.json"
YOLO_MODEL   = "yolov8n_openvino_model"   # exported OpenVINO directory
GENDER_MODEL = "/home/keshav/rajan/new_pipeline/models/mobilenetv3_gender_best.pth"

ENTRY_FRAMES = 4
EXIT_FRAMES  = 6

GENDER_CACHE_TTL   = 30     # frames before forced re-inference
GENDER_CONF_THRESH = 0.80   # re-infer when confidence drops below this

EVENTS_FLUSH_INTERVAL  = 5.0    # seconds between event JSON writes
METRICS_FLUSH_INTERVAL = 60.0   # seconds between metrics JSON writes

_MAX_EVENT_LOG_FLUSHED = 500
_MAX_METRICS_LOG       = 120

# Queue depths — drop-oldest keeps producers non-blocking
_DET_Q_SIZE    = 24
_GENDER_Q_SIZE = 24
_ZONE_Q_SIZE   = 24
_IO_Q_SIZE     = 200   # larger — writes burst but are rare

# JPEG quality for IPC frames (640×360 @ q80 ≈ 25-40 KB vs ~675 KB raw)
_IPC_JPEG_QUALITY = 80
_IPC_JPEG_PARAMS  = [cv2.IMWRITE_JPEG_QUALITY, _IPC_JPEG_QUALITY]

# Annotated output frames shown to user — slightly higher quality
_ANN_JPEG_QUALITY = 85
_ANN_JPEG_PARAMS  = [cv2.IMWRITE_JPEG_QUALITY, _ANN_JPEG_QUALITY]


# ─── COLOUR PALETTE ────────────────────────────────────────────────────────────

C_WHITE      = (255, 255, 255)
C_BLACK      = (  0,   0,   0)
C_DARK       = ( 18,  18,  26)
C_ACCENT     = (255, 200,  60)
C_GREEN      = ( 60, 220, 120)
C_RED        = ( 60,  60, 230)
C_BBOX       = (  0, 100,   0)
C_LABEL_TEXT = (  0, 255,   0)

_ZONE_COLOR_BANK = [
    (255, 190,  60), (100, 220, 100), ( 60, 160, 255), (255, 100, 100),
    (180,  80, 220), (  0, 210, 210), (255, 220,   0), (255, 140,  40),
    (160, 255, 160), (255, 130, 220),
]


# ─── SHARED HELPERS ────────────────────────────────────────────────────────────

def _jpeg_enc(frame: np.ndarray,
              params: list = _IPC_JPEG_PARAMS) -> bytes:
    """Encode a BGR numpy frame to JPEG bytes for IPC transport."""
    ok, buf = cv2.imencode(".jpg", frame, params)
    return buf.tobytes() if ok else b""


def _jpeg_dec(data: bytes) -> "np.ndarray | None":
    """Decode JPEG bytes to BGR numpy. Returns None on failure."""
    if not data:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _mp_put(q: mp.Queue, item: dict) -> None:
    """
    Non-blocking mp.Queue put.
    If full: evict oldest item first, then retry.
    Always prefers the freshest data over blocking the producer.
    """
    try:
        q.put_nowait(item)
        return
    except _queue.Full:
        pass
    try:
        q.get_nowait()   # drop oldest
    except _queue.Empty:
        pass
    try:
        q.put_nowait(item)
    except _queue.Full:
        pass             # genuine saturation — discard silently


def _pin_cores(core_ids: set, proc_name: str) -> None:
    """Restrict the calling process to given CPU cores."""
    try:
        os.sched_setaffinity(0, core_ids)
        print(f"[INFO] [{proc_name}] Pinned to CPU core(s) {sorted(core_ids)}")
    except (AttributeError, OSError) as exc:
        print(f"[WARN] [{proc_name}] Core pinning unavailable: {exc}")


def _start_parent_watchdog(parent_pid: int) -> None:
    """
    Daemon thread: self-terminate this process if the parent dies.
    Prevents orphan inference processes when the main app crashes.
    """
    def _watch() -> None:
        while True:
            try:
                ppid = os.getppid()
                if ppid != parent_pid or ppid == 1:
                    os._exit(1)
            except Exception:
                os._exit(1)
            time.sleep(1.0)

    threading.Thread(target=_watch, daemon=True, name="parent-watchdog").start()


# ─── DRAWING PRIMITIVES (used inside ZoneProcess) ──────────────────────────────

def _fill_rect_alpha(img, x1, y1, x2, y2, color, alpha=0.55):
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return
    sub  = img[y1:y2, x1:x2]
    rect = np.full(sub.shape, color, dtype=np.uint8)
    cv2.addWeighted(rect, alpha, sub, 1 - alpha, 0, sub)
    img[y1:y2, x1:x2] = sub


def _label_bg(img, text, x, y,
              text_color=C_WHITE, bg_color=C_DARK,
              font_scale=0.5, thickness=1, pad=6):
    font = cv2.FONT_HERSHEY_DUPLEX
    (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
    _fill_rect_alpha(img, x - pad, y - th - pad,
                     x + tw + pad, y + pad, bg_color, alpha=0.75)
    cv2.putText(img, text, (x, y), font, font_scale,
                text_color, thickness, cv2.LINE_AA)


# ══════════════════════════════════════════════════════════════════════════════
# PROCESS 1 — Detection + Tracking  (cores 1 & 2)
# ══════════════════════════════════════════════════════════════════════════════

class DetectionProcess(mp.Process):
    """
    YOLOv8n OpenVINO inference + per-camera ByteTrack.

    Core affinity : {1, 2}
    OpenVINO IR runs its own internal thread pool; giving it 2 cores
    enables parallel layer execution and approximately doubles throughput.

    Design
    ------
    • model() called with task="detect" — .track() segfaults on OpenVINO.
    • Warm-up in run(): compiles the OpenVINO IR graph before the first
      real frame so latency is stable from frame #1.
    • One sv.ByteTrack instance per camera; created lazily.
    • JPEG bytes from frame_queue are decoded here, then the ORIGINAL
      bytes are passed through to detection_queue unchanged to avoid
      a second lossy compression round-trip into GenderProcess.
    • Loop has no sleep — detection is the bottleneck and must run as
      fast as the hardware allows.
    """

    def __init__(self,
                 frame_queue:     mp.Queue,
                 detection_queue: mp.Queue,
                 yolo_model:      str,
                 parent_pid:      int,
                 core_ids:        tuple = (1, 2)) -> None:
        super().__init__(daemon=True, name="proc-detect")
        self.frame_queue     = frame_queue
        self.detection_queue = detection_queue
        self.yolo_model      = yolo_model
        self.parent_pid      = parent_pid
        self.core_ids        = set(core_ids)

    def run(self) -> None:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        _pin_cores(self.core_ids, self.name)
        _start_parent_watchdog(self.parent_pid)
        cv2.setNumThreads(2)   # allow OpenCV to use both assigned cores

        # ── Load model inside child process (never before spawn) ──────────
        from ultralytics import YOLO       # noqa
        import supervision as sv           # noqa

        model = YOLO(self.yolo_model, task="detect")

        # Warm-up: compile OpenVINO IR so the first real frame is fast
        _dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        model(_dummy, verbose=False)
        del _dummy
        print(f"[INFO] {self.name}: YOLO OpenVINO ready")

        # Per-camera ByteTrack instances (lazy initialisation)
        trackers: dict[str, object] = {}

        def _tracker(cam: str):
            if cam not in trackers:
                trackers[cam] = sv.ByteTrack()
            return trackers[cam]

        # ── Detection + tracking loop ─────────────────────────────────────
        while True:
            try:
                item = self.frame_queue.get(timeout=1.0)
            except _queue.Empty:
                continue
            except Exception as exc:
                print(f"[WARN] {self.name}: queue read: {exc}")
                continue

            try:
                cam   = item["cam"]
                frame = _jpeg_dec(item["frame"])
                if frame is None:
                    continue

                # ── YOLO — task="detect", never .track() ──────────────────
                results = model(frame, conf=0.1, iou=0.7,
                                classes=0, verbose=False)
                result  = results[0]

                tracks: list[dict] = []

                if result.boxes is not None and len(result.boxes) > 0:
                    dets    = sv.Detections.from_ultralytics(result)
                    tracked = _tracker(cam).update_with_detections(dets)

                    if tracked.tracker_id is not None and len(tracked) > 0:
                        for i in range(len(tracked)):
                            x1, y1, x2, y2 = tracked.xyxy[i].astype(int).tolist()
                            tid = int(tracked.tracker_id[i])
                            tracks.append({
                                "id":   tid,
                                "bbox": (x1, y1, x2, y2),
                                "foot": ((x1 + x2) // 2, y2),
                            })

                # Pass original JPEG bytes through — no re-encode
                _mp_put(self.detection_queue, {
                    "cam":       cam,
                    "frame":     item["frame"],
                    "tracks":    tracks,
                    "timestamp": time.time(),
                })

            except Exception as exc:
                print(f"[WARN] {self.name}: frame error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# PROCESS 2 — Gender Classification  (core 3)
# ══════════════════════════════════════════════════════════════════════════════

class GenderProcess(mp.Process):
    """
    Batched MobileNetV3 gender inference with TTL + confidence cache.

    Core affinity : {3}
    PyTorch's OpenMP thread pool is constrained to this core via
    sched_setaffinity — the OS will not schedule those threads elsewhere.

    Cache
    -----
    Key  : (cam, tid)  — prevents cross-camera ID collisions
    Fresh: age < TTL  AND  confidence >= GENDER_CONF_THRESH
    Stale: all else   → included in next batch inference pass

    Async
    -----
    A secondary daemon thread sweeps the cache every 10 s for entries
    whose age exceeds 3×TTL (belt-and-suspenders eviction on top of the
    per-frame active-key eviction in the main loop).
    """

    def __init__(self,
                 detection_queue: mp.Queue,
                 gender_queue:    mp.Queue,
                 gender_model:    str,
                 parent_pid:      int,
                 core_id:         int = 3) -> None:
        super().__init__(daemon=True, name="proc-gender")
        self.detection_queue = detection_queue
        self.gender_queue    = gender_queue
        self.gender_model    = gender_model
        self.parent_pid      = parent_pid
        self.core_id         = core_id

    def run(self) -> None:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        _pin_cores({self.core_id}, self.name)
        _start_parent_watchdog(self.parent_pid)
        cv2.setNumThreads(1)

        # ── Load model inside child process ───────────────────────────────
        from gender_classifier import GenderClassifier   # noqa
        model = GenderClassifier(self.gender_model)
        print(f"[INFO] {self.name}: GenderClassifier on {model.device}")

        # (cam, tid) → {"label": str, "confidence": float, "age": int}
        cache: dict[tuple, dict] = {}
        lock  = threading.Lock()

        # ── Background cache sweep (removes very old entries) ─────────────
        def _sweep() -> None:
            while True:
                time.sleep(10.0)
                cutoff = GENDER_CACHE_TTL * 3
                with lock:
                    dead = [k for k, v in cache.items() if v.get("age", 0) > cutoff]
                    for k in dead:
                        del cache[k]

        threading.Thread(target=_sweep, daemon=True, name="gender-sweep").start()

        # ── Inference loop ────────────────────────────────────────────────
        while True:
            try:
                item = self.detection_queue.get(timeout=1.0)
            except _queue.Empty:
                continue
            except Exception as exc:
                print(f"[WARN] {self.name}: queue read: {exc}")
                continue

            try:
                cam    = item["cam"]
                tracks = item["tracks"]

                # Fast path — no people detected
                if not tracks:
                    _mp_put(self.gender_queue, item)
                    continue

                frame = _jpeg_dec(item["frame"])
                if frame is None:
                    for t in tracks:
                        t["gender"] = "?"
                    _mp_put(self.gender_queue, item)
                    continue

                ids         = [t["id"] for t in tracks]
                boxes       = np.array([t["bbox"] for t in tracks], dtype=np.float32)
                active_keys = {(cam, tid) for tid in ids}

                # ── Classify stale/new tracks ─────────────────────────────
                stale_idx:   list[int] = []
                stale_boxes: list      = []

                with lock:
                    for i, tid in enumerate(ids):
                        key    = (cam, tid)
                        cached = cache.get(key)
                        fresh  = (
                            cached is not None
                            and cached["age"] < GENDER_CACHE_TTL
                            and cached["confidence"] >= GENDER_CONF_THRESH
                        )
                        if fresh:
                            cache[key]["age"] += 1
                        else:
                            stale_idx.append(i)
                            stale_boxes.append(boxes[i])

                # Single batched forward pass
                if stale_boxes:
                    preds = model.predict(frame, stale_boxes)
                    with lock:
                        for lpos, orig_i in enumerate(stale_idx):
                            key = (cam, ids[orig_i])
                            cache[key] = {
                                "label":      preds[lpos]["label"],
                                "confidence": preds[lpos]["confidence"],
                                "age":        0,
                            }

                # Evict tracks no longer visible in this camera
                with lock:
                    gone = [k for k in list(cache)
                            if k[0] == cam and k not in active_keys]
                    for k in gone:
                        del cache[k]

                # Attach labels from cache snapshot
                with lock:
                    for t in tracks:
                        cached    = cache.get((cam, t["id"]))
                        t["gender"] = cached["label"] if cached else "?"

                _mp_put(self.gender_queue, item)

            except Exception as exc:
                print(f"[WARN] {self.name}: frame error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# PROCESS 3 — Zone Processing + Drawing  (core 4)
# ══════════════════════════════════════════════════════════════════════════════

class ZoneProcess(mp.Process):
    """
    Zone hysteresis, annotation drawing, and I/O forwarding.

    Core affinity : {4}

    Zone state
    ----------
    One ZoneManager per camera; state is mutated only by this process
    (no locking needed). ZoneManager's own dwell-writer daemon thread
    runs inside this process.

    I/O forwarding
    --------------
    Events and metrics are put to io_queue via _mp_put — fully async,
    never blocks. This process never writes files directly.

    Output
    ------
    zone_queue items: annotated_frame + floor_map, both JPEG-encoded.
    """

    _MAP_SCALE = 150
    _MAP_W     = 900
    _MAP_H     = 750

    def __init__(self,
                 gender_queue: mp.Queue,
                 zone_queue:   mp.Queue,
                 io_queue:     mp.Queue,
                 camera_names: list,
                 zone_file:    str,
                 parent_pid:   int,
                 core_id:      int = 4) -> None:
        super().__init__(daemon=True, name="proc-zone")
        self.gender_queue = gender_queue
        self.zone_queue   = zone_queue
        self.io_queue     = io_queue
        self.camera_names = camera_names
        self.zone_file    = zone_file
        self.parent_pid   = parent_pid
        self.core_id      = core_id

    # ── Static floor map canvas ───────────────────────────────────────────────

    def _build_floor_base(self, zm, colors: dict) -> np.ndarray:
        MS = self._MAP_SCALE
        c  = np.zeros((self._MAP_H, self._MAP_W, 3), dtype=np.uint8)
        c[:] = (22, 22, 30)
        for x in range(0, self._MAP_W, MS):
            cv2.line(c, (x, 0), (x, self._MAP_H), (45, 45, 55), 1)
            cv2.putText(c, f"{x // MS}m", (x + 3, 13),
                        cv2.FONT_HERSHEY_DUPLEX, 0.3, (80, 80, 100), 1)
        for y in range(0, self._MAP_H, MS):
            cv2.line(c, (0, y), (self._MAP_W, y), (45, 45, 55), 1)
            cv2.putText(c, f"{y // MS}m", (3, y + 13),
                        cv2.FONT_HERSHEY_DUPLEX, 0.3, (80, 80, 100), 1)
        for name, poly in zm.zones_world.items():
            if len(poly) < 3:
                continue
            pts = np.array([[int(p[0]*MS), int(p[1]*MS)] for p in poly], np.int32)
            cv2.polylines(c, [pts], True, colors[name], 2, cv2.LINE_AA)
        cv2.rectangle(c, (0, 0), (self._MAP_W, 24), (30, 30, 40), -1)
        cv2.line(c, (0, 24), (self._MAP_W, 24), C_ACCENT, 1)
        cv2.putText(c, "STORE FLOOR MAP  —  bird's-eye view",
                    (self._MAP_W // 2 - 155, 17),
                    cv2.FONT_HERSHEY_DUPLEX, 0.46, C_ACCENT, 1)
        lx, ly = self._MAP_W - 140, self._MAP_H - 52
        _fill_rect_alpha(c, lx-8, ly-14, self._MAP_W-6, self._MAP_H-6, C_DARK, 0.70)
        cv2.circle(c, (lx+6, ly),    5, (180,180,180), -1)
        cv2.putText(c, "open area", (lx+16, ly+4),
                    cv2.FONT_HERSHEY_DUPLEX, 0.36, (180,180,180), 1)
        cv2.circle(c, (lx+6, ly+22), 5, C_GREEN, -1)
        cv2.putText(c, "in zone", (lx+16, ly+26),
                    cv2.FONT_HERSHEY_DUPLEX, 0.36, C_GREEN, 1)
        return c

    # ── Per-frame drawing ─────────────────────────────────────────────────────

    def _draw_hud(self, out, zm, colors):
        font = cv2.FONT_HERSHEY_DUPLEX
        pad, rh, cw, lw = 14, 36, 110, 115
        n  = len(zm.zones_pixel)
        pw = lw + 3*cw + 2*pad
        ph = pad + 28 + n*rh + pad
        _fill_rect_alpha(out, 10, 10, 10+pw, 10+ph, C_DARK, 0.72)
        cv2.rectangle(out, (10, 10), (10+pw, 10+ph), C_ACCENT, 1)
        hx, hy = 10+pad, 10+pad+16
        for title, off in zip(["ZONE","NOW","ENTRY","EXIT"],
                               [0, lw, lw+cw, lw+2*cw]):
            cv2.putText(out, title, (hx+off, hy), font, 0.42, C_ACCENT, 1, cv2.LINE_AA)
        dy = 10+pad+22
        cv2.line(out, (10+pad, dy), (10+pw-pad, dy), C_ACCENT, 1)
        for i, zone in enumerate(zm.zones_pixel):
            ry  = dy + 8 + (i+1)*rh - 6
            ins = len(zm.confirmed_inside[zone])
            z   = colors[zone]
            cv2.circle(out, (hx+6, ry-5), 5, z, -1)
            cv2.putText(out, zone.upper(), (hx+18, ry), font, 0.44, z, 1, cv2.LINE_AA)
            cv2.putText(out, str(ins), (hx+lw+30, ry), font, 0.55,
                        C_GREEN if ins > 0 else C_WHITE, 1, cv2.LINE_AA)
            cv2.putText(out, str(zm.zone_entry_count[zone]),
                        (hx+lw+cw+20, ry), font, 0.55, C_GREEN, 1, cv2.LINE_AA)
            cv2.putText(out, str(zm.zone_exit_count[zone]),
                        (hx+lw+2*cw+20, ry), font, 0.55, C_RED, 1, cv2.LINE_AA)

    def _draw_zones(self, out, zm, colors):
        for name, poly in zm.zones_pixel.items():
            if len(poly) < 3:
                continue
            cv2.polylines(out, [np.array(poly, np.int32)], True, colors[name], 2, cv2.LINE_AA)
            cx = int(np.mean([p[0] for p in poly]))
            cy = int(np.mean([p[1] for p in poly]))
            _label_bg(out, name.upper(), cx-30, cy,
                      text_color=colors[name], bg_color=C_DARK)

    def _draw_track(self, out, track):
        x1, y1, x2, y2 = track["bbox"]
        label = f"ID {track['id']} | {track.get('gender','?')}"
        cv2.rectangle(out, (x1,y1), (x2,y2), C_BBOX, 1)
        cv2.circle(out, track["foot"], 4, C_BBOX, -1)
        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), _ = cv2.getTextSize(label, font, 0.5, 1)
        lx = max(0, x1)
        ly = y1 if y1-th-8 >= 0 else y2+th+8
        rx = min(out.shape[1], lx+tw+6)
        cv2.rectangle(out, (lx, ly-th-8), (rx, ly), C_BLACK, -1)
        cv2.putText(out, label, (lx+3, ly-4), font, 0.5, C_LABEL_TEXT, 1, cv2.LINE_AA)

    def _draw_floor_map(self, base, tracks, zm, colors):
        MS    = self._MAP_SCALE
        floor = base.copy()
        for name, poly in zm.zones_world.items():
            if len(poly) < 3:
                continue
            pts = np.array([[int(p[0]*MS), int(p[1]*MS)] for p in poly], np.int32)
            cx, cy = int(np.mean(pts[:,0])), int(np.mean(pts[:,1]))
            col = colors[name]
            cv2.putText(floor, name.upper(), (cx-34, cy-24),
                        cv2.FONT_HERSHEY_DUPLEX, 0.45, col, 1)
            cv2.putText(floor, f"NOW {len(zm.confirmed_inside[name])}",
                        (cx-38, cy), cv2.FONT_HERSHEY_DUPLEX, 0.40, C_GREEN, 1)
            cv2.putText(floor, f"E:{zm.zone_entry_count[name]}",
                        (cx-38, cy+20), cv2.FONT_HERSHEY_DUPLEX, 0.38, (120,255,120), 1)
            cv2.putText(floor, f"X:{zm.zone_exit_count[name]}",
                        (cx+14, cy+20), cv2.FONT_HERSHEY_DUPLEX, 0.38, (80,80,230), 1)
        for track in tracks:
            wp = zm.pixel_to_world(track["foot"][0], track["foot"][1])
            if wp is None:
                continue
            mx, my = int(wp[0]*MS), int(wp[1]*MS)
            if not (0 <= mx < self._MAP_W and 0 <= my < self._MAP_H):
                continue
            dot = C_GREEN if track.get("zones") else (180,180,180)
            cv2.circle(floor, (mx,my), 8, dot, -1)
            cv2.circle(floor, (mx,my), 9, C_WHITE, 1)
            cv2.putText(floor, str(track["id"]), (mx+11, my+4),
                        cv2.FONT_HERSHEY_DUPLEX, 0.38, dot, 1)
        return floor

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self) -> None:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        _pin_cores({self.core_id}, self.name)
        _start_parent_watchdog(self.parent_pid)
        cv2.setNumThreads(1)

        # ── Load ZoneManagers inside child process ─────────────────────────
        from zone import ZoneManager   # noqa

        with open(self.zone_file) as f:
            all_zone_data: dict = json.load(f)

        zm_map:    dict = {}   # cam → ZoneManager
        color_map: dict = {}   # cam → {zone_name: color_tuple}
        base_map:  dict = {}   # cam → static floor canvas (np.ndarray)

        # Per-camera I/O accounting
        ev_log:   dict = {}   # cam → list[event_dict]
        ev_flush: dict = {}   # cam → int  (how many events forwarded so far)
        met_log:  dict = {}   # cam → list[snapshot_dict]
        last_ev:  dict = {}   # cam → float timestamp
        last_met: dict = {}   # cam → float timestamp

        for cam in self.camera_names:
            if cam not in all_zone_data:
                print(f"[WARN] {self.name}: no zone config for '{cam}'")
                continue
            zm = ZoneManager(
                all_zone_data[cam],
                entry_frames = ENTRY_FRAMES,
                exit_frames  = EXIT_FRAMES,
                dwell_file   = f"zone_dwell_{cam}.json",
            )
            colors = {
                name: _ZONE_COLOR_BANK[idx % len(_ZONE_COLOR_BANK)]
                for idx, name in enumerate(zm.zones_pixel)
            }
            zm_map[cam]    = zm
            color_map[cam] = colors
            base_map[cam]  = self._build_floor_base(zm, colors)
            ev_log[cam]    = []
            ev_flush[cam]  = 0
            met_log[cam]   = []
            last_ev[cam]   = 0.0
            last_met[cam]  = 0.0

        _blank_map = np.zeros((self._MAP_H, self._MAP_W, 3), dtype=np.uint8)
        print(f"[INFO] {self.name}: ready for cameras {list(zm_map)}")

        # ── Main zone loop ────────────────────────────────────────────────
        while True:
            try:
                item = self.gender_queue.get(timeout=1.0)
            except _queue.Empty:
                continue
            except Exception as exc:
                print(f"[WARN] {self.name}: queue read: {exc}")
                continue

            try:
                cam    = item["cam"]
                tracks = item["tracks"]
                now    = item.get("timestamp", time.time())

                frame  = _jpeg_dec(item["frame"])
                if frame is None:
                    continue
                out = frame.copy()

                # ── No zone config — draw bbox/labels only ────────────────
                if cam not in zm_map:
                    for t in tracks:
                        self._draw_track(out, t)
                    _mp_put(self.zone_queue, {
                        "cam":             cam,
                        "annotated_frame": _jpeg_enc(out, _ANN_JPEG_PARAMS),
                        "floor_map":       _jpeg_enc(_blank_map),
                        "timestamp":       now,
                    })
                    continue

                zm     = zm_map[cam]
                colors = color_map[cam]
                ev     = ev_log[cam]

                # ── Zone hysteresis (entry/exit debounce) ─────────────────
                active_ids: set = set()
                for track in tracks:
                    tid  = track["id"]
                    foot = track["foot"]
                    active_ids.add(tid)

                    world_pt = zm.pixel_to_world(foot[0], foot[1])
                    zones: list = []

                    for zone_name in zm.zones_pixel:
                        poly_px = zm.zones_pixel[zone_name]
                        if len(poly_px) < 3:
                            raw_in = False
                        elif world_pt is not None and len(zm.zones_world[zone_name]) >= 3:
                            raw_in = (cv2.pointPolygonTest(
                                np.array(zm.zones_world[zone_name], np.float32),
                                tuple(world_pt), False) >= 0)
                        else:
                            raw_in = (cv2.pointPolygonTest(
                                np.array(poly_px, np.float32),
                                foot, False) >= 0)

                        zm.apply_hysteresis(tid, zone_name, raw_in, now, ev)
                        if tid in zm.confirmed_inside[zone_name]:
                            zones.append(zone_name)

                    track["zones"] = zones

                # Force-exit tracks no longer reported by ByteTrack
                zm.cleanup_lost_tracks(active_ids, now, ev)

                # ── Draw ──────────────────────────────────────────────────
                self._draw_zones(out, zm, colors)
                for track in tracks:
                    self._draw_track(out, track)
                self._draw_hud(out, zm, colors)
                fmap = self._draw_floor_map(base_map[cam], tracks, zm, colors)

                # ── Encode and forward annotated frames ───────────────────
                _mp_put(self.zone_queue, {
                    "cam":             cam,
                    "annotated_frame": _jpeg_enc(out,  _ANN_JPEG_PARAMS),
                    "floor_map":       _jpeg_enc(fmap, _IPC_JPEG_PARAMS),
                    "timestamp":       now,
                })

                # ── Forward events to IOProcess (non-blocking) ─────────────
                if now - last_ev[cam] >= EVENTS_FLUSH_INTERVAL:
                    fc  = ev_flush[cam]
                    new = ev[fc:]
                    if new:
                        _mp_put(self.io_queue, {
                            "filepath": f"zone_events_{cam}.json",
                            "data":     {"events": new},
                        })
                        ev_flush[cam] = len(ev)
                    if ev_flush[cam] > _MAX_EVENT_LOG_FLUSHED:
                        del ev[:ev_flush[cam]]
                        ev_flush[cam] = 0
                    last_ev[cam] = now

                # ── Forward metrics snapshot to IOProcess ──────────────────
                if now - last_met[cam] >= METRICS_FLUSH_INTERVAL:
                    snap: dict = {"time": zm.fmt_ts(now)}
                    for z in zm.zones_pixel:
                        snap[z] = {
                            "current": len(zm.confirmed_inside[z]),
                            "entries": zm.zone_entry_count[z],
                            "exits":   zm.zone_exit_count[z],
                        }
                    ml = met_log[cam]
                    ml.append(snap)
                    if len(ml) > _MAX_METRICS_LOG:
                        met_log[cam] = ml[-_MAX_METRICS_LOG:]
                    _mp_put(self.io_queue, {
                        "filepath": f"zone_metrics_{cam}.json",
                        "data":     met_log[cam],
                    })
                    last_met[cam] = now

            except Exception as exc:
                print(f"[WARN] {self.name}: frame error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# PROCESS 4 — Async I/O Writer  (core 5)
# ══════════════════════════════════════════════════════════════════════════════

class IOProcess(mp.Process):
    """
    All JSON file writes on a dedicated core using asyncio.

    Core affinity : {5}
    File I/O is kernel-bound, not CPU-bound — this process keeps CPU near
    zero even during write bursts.

    Async design
    ────────────
    A single asyncio event loop runs inside this process.
    The drain loop polls the mp.Queue at 20 Hz and schedules each write as
    an independent asyncio.Task backed by run_in_executor (thread pool).

    Key property
    ────────────
    A slow write on one file NEVER stalls writes to any other file because
    each write is an independent Task with its own exception handler.
    The io_queue is never a backpressure point for ZoneProcess.
    """

    def __init__(self,
                 io_queue:   mp.Queue,
                 parent_pid: int,
                 core_id:    int = 5) -> None:
        super().__init__(daemon=True, name="proc-io")
        self.io_queue   = io_queue
        self.parent_pid = parent_pid
        self.core_id    = core_id

    def run(self) -> None:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        _pin_cores({self.core_id}, self.name)
        _start_parent_watchdog(self.parent_pid)
        print(f"[INFO] {self.name}: async JSON writer started")
        asyncio.run(self._loop())

    async def _loop(self) -> None:
        loop    = asyncio.get_running_loop()
        pending: set = set()

        while True:
            # Drain everything in the queue in one non-blocking pass
            batch: list = []
            while True:
                try:
                    batch.append(self.io_queue.get_nowait())
                except _queue.Empty:
                    break

            # Launch each write as an independent concurrent Task
            for item in batch:
                task = loop.create_task(
                    self._write(loop, item["filepath"], item["data"])
                )
                pending.add(task)
                task.add_done_callback(pending.discard)

            # 50 ms sleep → 20 polls/sec — ample for 5-second flush intervals
            await asyncio.sleep(0.05)

    @staticmethod
    async def _write(loop: asyncio.AbstractEventLoop,
                     filepath: str,
                     data: object) -> None:
        """Write one JSON file via thread-pool executor — never blocks the loop."""
        def _do() -> None:
            with open(filepath, "w") as fh:
                json.dump(data, fh, indent=2, default=str)

        try:
            await loop.run_in_executor(None, _do)
        except Exception as exc:
            # Log but never re-raise — a failed write must not kill the loop
            print(f"[WARN] IOProcess: write failed ({filepath}): {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE — creates all queues, starts all four processes
# ══════════════════════════════════════════════════════════════════════════════

class Pipeline:
    """
    Orchestrates DetectionProcess → GenderProcess → ZoneProcess → IOProcess.

    MUST be instantiated AFTER mp.set_start_method("spawn") in main.py.

    Public attribute
    ────────────────
    pipeline.zone_queue  — pass to MultiCameraManager.display_streams()

    Core layout summary
    ───────────────────
    Core 0     main process + display loop  (pinned by main.py)
    Cores 1-2  DetectionProcess
    Core 3     GenderProcess
    Core 4     ZoneProcess
    Core 5     IOProcess
    """

    def __init__(self,
                 frame_queue:  mp.Queue,
                 camera_names: list,
                 zone_file:    str = ZONE_FILE,
                 gender_model: str = GENDER_MODEL) -> None:

        parent_pid = os.getpid()

        # All queues are mp.Queue — required for cross-process IPC
        self.detection_queue: mp.Queue = mp.Queue(maxsize=_DET_Q_SIZE)
        self.gender_queue:    mp.Queue = mp.Queue(maxsize=_GENDER_Q_SIZE)
        self.zone_queue:      mp.Queue = mp.Queue(maxsize=_ZONE_Q_SIZE)
        self.io_queue:        mp.Queue = mp.Queue(maxsize=_IO_Q_SIZE)

        self._procs = [
            DetectionProcess(
                frame_queue=frame_queue,
                detection_queue=self.detection_queue,
                yolo_model=YOLO_MODEL,
                parent_pid=parent_pid,
                core_ids=(1, 2),
            ),
            GenderProcess(
                detection_queue=self.detection_queue,
                gender_queue=self.gender_queue,
                gender_model=gender_model,
                parent_pid=parent_pid,
                core_id=3,
            ),
            ZoneProcess(
                gender_queue=self.gender_queue,
                zone_queue=self.zone_queue,
                io_queue=self.io_queue,
                camera_names=camera_names,
                zone_file=zone_file,
                parent_pid=parent_pid,
                core_id=4,
            ),
            IOProcess(
                io_queue=self.io_queue,
                parent_pid=parent_pid,
                core_id=5,
            ),
        ]

        for proc in self._procs:
            proc.start()

        print(
            "[INFO] Pipeline active:\n"
            "  frame_queue (JPEG bytes from cameras)\n"
            "    └─[cores 1+2]─► DetectionProcess  (YOLO + ByteTrack)\n"
            "        └─[core  3]─► GenderProcess    (MobileNetV3)\n"
            "            └─[core  4]─► ZoneProcess  (hysteresis + draw)\n"
            "                ├─────────────────────► zone_queue (display)\n"
            "                └─[core  5]─► IOProcess (asyncio JSON writes)\n"
            "  [core 0] reserved for display loop"
        )

    def stop(self) -> None:
        for proc in self._procs:
            if proc.is_alive():
                proc.kill()
        print("[INFO] Pipeline stopped")