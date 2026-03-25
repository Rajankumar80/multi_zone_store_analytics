# import cv2
# import numpy as np
# import json
# import time
# import threading
# import queue
# from ultralytics import YOLO
# from gender_classifier import GenderClassifier
# from zone import ZoneManager


# # ─── CONFIGURATION ─────────────────────────────────────────────────────────────

# ZONE_FILE    = "/home/keshav/rajan/new_pipeline/zones_runtime.json"
# YOLO_MODEL   = "/home/keshav/rajan/new_pipeline/models/best_openvino_model"
# GENDER_MODEL = "/home/keshav/rajan/new_pipeline/models/mobilenetv3_gender_best.pth"
# METRICS_FILE = "zone_metrics.json"
# EVENTS_FILE  = "zone_events.json"

# ENTRY_FRAMES = 4
# EXIT_FRAMES  = 6

# # Gender cache: re-run inference when age >= TTL or confidence < threshold
# GENDER_CACHE_TTL    = 30     # frames
# GENDER_CONF_THRESH  = 0.80

# # Flush intervals
# EVENTS_FLUSH_INTERVAL  = 5.0    # seconds
# METRICS_FLUSH_INTERVAL = 60.0   # seconds

# # Memory bounds
# _MAX_EVENT_LOG_FLUSHED  = 500   # trim event_log after this many flushed entries
# _MAX_METRICS_LOG        = 120   # ~2 hours at 60 s interval
# _IO_QUEUE_MAXSIZE       = 50    # ~4 min backlog at normal write rate


# # ─── PALETTE ───────────────────────────────────────────────────────────────────

# C_WHITE      = (255, 255, 255)
# C_BLACK      = (0,   0,   0)
# C_DARK       = (18,  18,  26)
# C_ACCENT     = (255, 200,  60)
# C_GREEN      = ( 60, 220, 120)
# C_RED        = ( 60,  60, 230)
# C_BBOX       = (  0, 100,   0)   # dark green bounding box
# C_LABEL_TEXT = (  0, 255,   0)   # bright green label text

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
#     """Blit a solid colour rectangle at the given opacity."""
#     x1, y1 = max(0, x1), max(0, y1)
#     x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
#     if x2 <= x1 or y2 <= y1:
#         return
#     sub  = img[y1:y2, x1:x2]
#     rect = np.full(sub.shape, color, dtype=np.uint8)
#     cv2.addWeighted(rect, alpha, sub, 1 - alpha, 0, sub)
#     img[y1:y2, x1:x2] = sub


# def draw_rounded_rect(img, x1, y1, x2, y2, r, color, thickness=2):
#     """Stroke a rectangle with rounded corners."""
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
#     """Draw text with a semi-transparent dark backing rectangle."""
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
#     Full tracking pipeline with two background threads.

#     Threading model
#     ───────────────
#     Main thread   — YOLO track → zone hysteresis → read gender cache
#                     → draw frame → return result every frame, no waiting.

#     Gender thread — receives (frame, boxes, ids) via _gender_queue,
#                     runs batched inference for stale/new tracks only,
#                     writes results into _gender_cache under _cache_lock.
#                     Never touches zone logic or frame drawing.

#     I/O thread    — drains _io_queue, writes JSON files to disk.
#                     Never blocks the main thread.

#     Key invariants
#     ──────────────
#     - YOLO tracker state is single-threaded (main thread only).
#     - Zone entry/exit counts and confirmed_inside are single-threaded.
#     - Gender labels are display-only — a 1-frame lag is invisible.
#     - All background threads survive exceptions (try/except/finally).
#     - No background thread can crash or freeze the main video loop.
#     """

#     def __init__(self, camera_name="cam_entry"):
#         # ── Models ────────────────────────────────────────────────────────────
#         self.model        = YOLO(YOLO_MODEL)
#         self.gender_model = GenderClassifier(GENDER_MODEL)

#         # ── Zone manager ──────────────────────────────────────────────────────
#         with open(ZONE_FILE) as f:
#             camera_data = json.load(f)[camera_name]

#         self.zm = ZoneManager(
#             camera_data,
#             entry_frames = ENTRY_FRAMES,
#             exit_frames  = EXIT_FRAMES,
#         )

#         # One display colour per zone
#         self.zone_color = {
#             name: _ZONE_COLOR_BANK[idx % len(_ZONE_COLOR_BANK)]
#             for idx, name in enumerate(self.zm.zones_pixel)
#         }

#         # ── Gender cache ──────────────────────────────────────────────────────
#         # Written by gender thread (under _cache_lock).
#         # Read by main thread without a lock — CPython dict .get() is atomic.
#         self._gender_cache = {}    # tid → {"label": str, "confidence": float, "age": int}
#         self._cache_lock   = threading.Lock()

#         # ── Queues ────────────────────────────────────────────────────────────
#         # maxsize=1: if gender thread is busy, drop the job — cached label is fine.
#         self._gender_queue = queue.Queue(maxsize=1)
#         # maxsize=_IO_QUEUE_MAXSIZE: bounded so a slow disk can't OOM the process.
#         self._io_queue     = queue.Queue(maxsize=_IO_QUEUE_MAXSIZE)

#         # ── Event / metrics logs ──────────────────────────────────────────────
#         self.event_log          = []
#         self._flushed_count     = 0
#         self.metrics_log        = []
#         self._last_metrics      = 0.0
#         self._last_events_flush = 0.0

#         # ── Pre-allocated static floor map canvas ─────────────────────────────
#         # Grid, zone outlines, title bar and legend are drawn once at startup.
#         # Every frame only adds the per-frame dynamic elements on a copy.
#         self.MAP_SCALE     = 150
#         self.MAP_W         = 900
#         self.MAP_H         = 750
#         self._floor_canvas = np.zeros((self.MAP_H, self.MAP_W, 3), dtype=np.uint8)
#         self._build_floor_base()

#         # ── Start background threads ──────────────────────────────────────────
#         threading.Thread(target=self._gender_worker, daemon=True).start()
#         threading.Thread(target=self._io_worker,     daemon=True).start()

#     # =========================================================================
#     # Gender thread
#     # =========================================================================

#     def _gender_worker(self):
#         """
#         Waits for a (frame, boxes, ids) job.
#         Runs batched GPU inference only for stale/new/uncertain tracks.
#         Writes results into _gender_cache under _cache_lock.
#         task_done() is guaranteed even on exception so the queue never jams.
#         """
#         while True:
#             job = self._gender_queue.get()
#             if job is None:                    # shutdown sentinel
#                 self._gender_queue.task_done()
#                 break

#             try:
#                 frame, boxes, ids = job

#                 # Snapshot the cache under the lock (very fast — dict copy)
#                 with self._cache_lock:
#                     cache_snapshot = dict(self._gender_cache)

#                 # Classify each track: fresh (use cache) or stale (need inference)
#                 stale_idx, stale_boxes = [], []
#                 for i, tid in enumerate(ids):
#                     cached = cache_snapshot.get(tid)
#                     if (cached is not None
#                             and cached["age"] < GENDER_CACHE_TTL
#                             and cached["confidence"] >= GENDER_CONF_THRESH):
#                         # Fresh — increment age in live cache; no GPU work needed
#                         with self._cache_lock:
#                             if tid in self._gender_cache:
#                                 self._gender_cache[tid]["age"] += 1
#                     else:
#                         stale_idx.append(i)
#                         stale_boxes.append(boxes[i])

#                 # One batched forward pass for all stale/new tracks
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

#                 # Evict tracks that are no longer in this job's frame
#                 active = set(ids)
#                 with self._cache_lock:
#                     for tid in list(self._gender_cache.keys()):
#                         if tid not in active:
#                             del self._gender_cache[tid]

#             except Exception as e:
#                 # Log but never let the thread die
#                 print(f"[WARN] gender worker error: {e}")
#             finally:
#                 self._gender_queue.task_done()

#     # =========================================================================
#     # I/O thread
#     # =========================================================================

#     def _io_worker(self):
#         """
#         Drains _io_queue and writes JSON to disk.
#         Catches all exceptions so the thread never dies silently.
#         task_done() fires in finally so the queue never jams.
#         """
#         while True:
#             filepath, data = self._io_queue.get()
#             try:
#                 with open(filepath, "w") as f:
#                     # default=str handles any non-serialisable types gracefully
#                     json.dump(data, f, indent=2, default=str)
#             except Exception as e:
#                 print(f"[WARN] I/O write failed ({filepath}): {e}")
#             finally:
#                 self._io_queue.task_done()

#     def _enqueue_write(self, filepath, data):
#         """
#         Post a write job — returns immediately, never blocks, never crashes.
#         If the I/O queue is full (disk saturated) the write is silently dropped
#         with a warning. A skipped write is always better than a crashed process.
#         """
#         try:
#             self._io_queue.put_nowait((filepath, data))
#         except queue.Full:
#             print(f"[WARN] I/O queue full — dropping write to {filepath}")

#     # =========================================================================
#     # Floor map — static base built once at startup
#     # =========================================================================

#     def _build_floor_base(self):
#         """
#         Draw the parts of the floor map that never change:
#         metric grid, zone outlines, title bar, legend.
#         Called once in __init__. Every frame copies this and draws dots on top.
#         """
#         self._floor_canvas[:] = (22, 22, 30)

#         # Metric grid
#         for x in range(0, self.MAP_W, self.MAP_SCALE):
#             cv2.line(self._floor_canvas, (x, 0), (x, self.MAP_H), (45, 45, 55), 1)
#             cv2.putText(self._floor_canvas, f"{x // self.MAP_SCALE}m",
#                         (x + 3, 13), cv2.FONT_HERSHEY_DUPLEX, 0.3, (80, 80, 100), 1)
#         for y in range(0, self.MAP_H, self.MAP_SCALE):
#             cv2.line(self._floor_canvas, (0, y), (self.MAP_W, y), (45, 45, 55), 1)
#             cv2.putText(self._floor_canvas, f"{y // self.MAP_SCALE}m",
#                         (3, y + 13), cv2.FONT_HERSHEY_DUPLEX, 0.3, (80, 80, 100), 1)

#         # Zone outlines (positions never change)
#         for name, poly_world in self.zm.zones_world.items():
#             if len(poly_world) < 3:
#                 continue
#             color = self.zone_color[name]
#             pts   = np.array(
#                 [[int(p[0] * self.MAP_SCALE), int(p[1] * self.MAP_SCALE)]
#                  for p in poly_world], dtype=np.int32)
#             cv2.polylines(self._floor_canvas, [pts], True, color, 2, cv2.LINE_AA)

#         # Title bar
#         cv2.rectangle(self._floor_canvas, (0, 0), (self.MAP_W, 24), (30, 30, 40), -1)
#         cv2.line(self._floor_canvas, (0, 24), (self.MAP_W, 24), C_ACCENT, 1)
#         cv2.putText(self._floor_canvas, "STORE FLOOR MAP  —  bird's-eye view",
#                     (self.MAP_W // 2 - 155, 17),
#                     cv2.FONT_HERSHEY_DUPLEX, 0.46, C_ACCENT, 1)

#         # Legend
#         lx, ly = self.MAP_W - 140, self.MAP_H - 52
#         draw_filled_rect_alpha(self._floor_canvas,
#                                lx - 8, ly - 14, self.MAP_W - 6, self.MAP_H - 6,
#                                C_DARK, alpha=0.70)
#         cv2.circle(self._floor_canvas, (lx + 6, ly),     5, (180, 180, 180), -1)
#         cv2.putText(self._floor_canvas, "open area", (lx + 16, ly + 4),
#                     cv2.FONT_HERSHEY_DUPLEX, 0.36, (180, 180, 180), 1)
#         cv2.circle(self._floor_canvas, (lx + 6, ly + 22), 5, C_GREEN, -1)
#         cv2.putText(self._floor_canvas, "in zone",   (lx + 16, ly + 26),
#                     cv2.FONT_HERSHEY_DUPLEX, 0.36, C_GREEN, 1)

#     # =========================================================================
#     # Drawing helpers — called from main thread every frame
#     # =========================================================================

#     def _draw_hud(self, output):
#         """Top-left stats panel: ZONE | NOW | ENTRY | EXIT per zone."""
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
#         """Zone boundary polylines with name labels. No transparent fill."""
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
#         """
#         Dark-green thin bounding box + foot dot.
#         Label above the box (falls back to below if too close to top edge).
#         Both left and right label edges are clamped to frame bounds.
#         """
#         x1, y1, x2, y2 = track["bbox"]
#         gender_label    = track.get("gender", "?")

#         # Bounding box and foot dot
#         cv2.rectangle(output, (x1, y1), (x2, y2), C_BBOX, 1)
#         cv2.circle(output, track["foot"], 4, C_BBOX, -1)

#         # Label positioning
#         label = f"ID {track['id']} | {gender_label}"
#         font  = cv2.FONT_HERSHEY_SIMPLEX
#         (tw, th), _ = cv2.getTextSize(label, font, 0.5, 1)

#         # Place above bbox; if too close to top edge place below instead
#         if y1 - th - 8 >= 0:
#             lx, ly = x1, y1
#         else:
#             lx, ly = x1, y2 + th + 8

#         # Clamp both horizontal edges to frame bounds
#         lx = max(0, lx)
#         rx = min(output.shape[1], lx + tw + 6)

#         cv2.rectangle(output, (lx, ly - th - 8), (rx, ly), C_BLACK, -1)
#         cv2.putText(output, label, (lx + 3, ly - 4),
#                     font, 0.5, C_LABEL_TEXT, 1, cv2.LINE_AA)

#     def _draw_floor_map(self, tracks):
#         """
#         Copy the static base canvas and draw per-frame dynamic elements:
#         live zone stats (NOW/E/X) and person dots.
#         """
#         floor_map = self._floor_canvas.copy()

#         # Live zone stats
#         for name, poly_world in self.zm.zones_world.items():
#             if len(poly_world) < 3:
#                 continue
#             color = self.zone_color[name]
#             pts   = np.array(
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

#         # Person dots
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
#         Called from the video loop on every captured frame.
#         Runs entirely on the main thread. Returns immediately without waiting
#         for any background thread.

#         Steps
#         -----
#         1. YOLO tracking  — produces bounding boxes + tracker IDs
#         2. Zone hysteresis — updates entry/exit state and event log
#         3. Gender cache read — reads last known label (may be 1 frame stale)
#         4. Gender job post — drops job into queue non-blocking (skip if busy)
#         5. Gender cache eviction — remove entries for vanished tracks immediately
#         6. Draw — zones, tracks, HUD, floor map
#         7. Periodic I/O — flush events and metrics to background thread
#         8. Return (annotated_frame, tracks, floor_map)
#         """
#         now = time.time()

#         # ── 1. YOLO ───────────────────────────────────────────────────────────
#         results = self.model.track(
#             frame,
#             persist = True,
#             classes = 0,
#             conf    = 0.1,
#             iou     = 0.7,
#             tracker = "botsort.yaml",
#             verbose = False,
#         )

#         result     = results[0]
#         output     = frame.copy()
#         active_ids = set()
#         tracks     = []

#         if result.boxes is not None and result.boxes.id is not None:
#             boxes = result.boxes.xyxy.cpu().numpy()
#             ids   = result.boxes.id.cpu().numpy().astype(int)

#             for box, tid in zip(boxes, ids):
#                 x1, y1, x2, y2 = box.astype(int)
#                 cx, cy          = int((x1 + x2) / 2), int(y2)
#                 foot_pixel      = (cx, cy)
#                 active_ids.add(tid)
#                 world_pt        = self.zm.pixel_to_world(cx, cy)

#                 # ── 2. Zone hysteresis ────────────────────────────────────────
#                 person_zones = []
#                 # AFTER
#                 for zone_name in self.zm.zones_pixel:
#                     if len(self.zm.zones_pixel[zone_name]) < 3:   # ← add this line
#                         raw_inside = False
#                     elif world_pt is not None and len(self.zm.zones_world[zone_name]) >= 3:
#                         raw_inside = (
#                             cv2.pointPolygonTest(
#                                 np.array(self.zm.zones_world[zone_name], np.float32),
#                                 tuple(world_pt), False,
#                             ) >= 0
#                         )
#                     else:
#                         raw_inside = (
#                             cv2.pointPolygonTest(
#                                 np.array(self.zm.zones_pixel[zone_name], np.float32),
#                                 foot_pixel, False,
#                             ) >= 0
#                         )               
#                     self.zm.apply_hysteresis(tid, zone_name, raw_inside,
#                                              now, self.event_log)
#                     if tid in self.zm.confirmed_inside[zone_name]:
#                         person_zones.append(zone_name)

#                 # ── 3. Gender cache read (CPython dict.get is atomic) ─────────
#                 cached = self._gender_cache.get(tid)
#                 gender = cached["label"] if cached else "?"

#                 tracks.append({
#                     "id":     tid,
#                     "bbox":   (x1, y1, x2, y2),
#                     "foot":   foot_pixel,
#                     "zones":  person_zones,
#                     "gender": gender,
#                 })

#             # ── 4. Post gender job — non-blocking, drop if thread is busy ─────
#             if not self._gender_queue.full():
#                 try:
#                     self._gender_queue.put_nowait((frame.copy(), boxes, ids))
#                 except queue.Full:
#                     pass   # race between full() check and put_nowait — harmless

#         # ── Cleanup lost tracks ───────────────────────────────────────────────
#         self.zm.cleanup_lost_tracks(active_ids, now, self.event_log)

#         # ── 5. Evict gender cache for vanished tracks (main thread, immediate) ─
#         # The gender worker evicts based on the most recent job's ids, which is
#         # 1 frame old. This eviction runs on the current frame's active_ids,
#         # preventing a reused tracker ID from inheriting a stale cached label.
#         with self._cache_lock:
#             for tid in list(self._gender_cache.keys()):
#                 if tid not in active_ids:
#                     del self._gender_cache[tid]

#         # ── 6. Draw ───────────────────────────────────────────────────────────
#         self._draw_zones(output)
#         for track in tracks:
#             self._draw_track(output, track)
#         self._draw_hud(output)
#         floor_map = self._draw_floor_map(tracks)

#         # ── 7. Periodic I/O ───────────────────────────────────────────────────
#         if now - self._last_events_flush >= EVENTS_FLUSH_INTERVAL:
#             new_events = self.event_log[self._flushed_count:]
#             if new_events:
#                 self._enqueue_write(EVENTS_FILE, {"events": new_events})
#                 self._flushed_count = len(self.event_log)
#             # Trim the already-flushed prefix to keep memory bounded
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

#         # ── 8. Return ─────────────────────────────────────────────────────────
#         return output, tracks, floor_map
# ---------------------------------------------------------

import cv2
import numpy as np
import json
import time
import threading
import queue
from ultralytics import YOLO
from gender_classifier import GenderClassifier
from zone import ZoneManager
import supervision as sv


# ─── CONFIGURATION ─────────────────────────────────────────────────────────────

ZONE_FILE    = "/home/keshav/rajan/new_pipeline/zones_runtime.json"
YOLO_MODEL   = "yolov8n_openvino_model"   # exported OpenVINO dir
GENDER_MODEL = "/home/keshav/rajan/new_pipeline/models/mobilenetv3_gender_best.pth"
METRICS_FILE = "zone_metrics.json"
EVENTS_FILE  = "zone_events.json"

ENTRY_FRAMES = 4
EXIT_FRAMES  = 6

# Gender cache: re-run inference when age >= TTL or confidence < threshold
GENDER_CACHE_TTL   = 30    # frames
GENDER_CONF_THRESH = 0.80

# Flush intervals
EVENTS_FLUSH_INTERVAL  = 5.0   # seconds
METRICS_FLUSH_INTERVAL = 60.0  # seconds

# Memory bounds
_MAX_EVENT_LOG_FLUSHED = 500
_MAX_METRICS_LOG       = 120
_IO_QUEUE_MAXSIZE      = 50


# ─── PALETTE ───────────────────────────────────────────────────────────────────

C_WHITE      = (255, 255, 255)
C_BLACK      = (0,   0,   0)
C_DARK       = (18,  18,  26)
C_ACCENT     = (255, 200,  60)
C_GREEN      = ( 60, 220, 120)
C_RED        = ( 60,  60, 230)
C_BBOX       = (  0, 100,   0)
C_LABEL_TEXT = (  0, 255,   0)

_ZONE_COLOR_BANK = [
    (255, 190,  60),
    (100, 220, 100),
    ( 60, 160, 255),
    (255, 100, 100),
    (180,  80, 220),
    (  0, 210, 210),
    (255, 220,   0),
    (255, 140,  40),
    (160, 255, 160),
    (255, 130, 220),
]


# ─── DRAWING HELPERS ───────────────────────────────────────────────────────────

def draw_filled_rect_alpha(img, x1, y1, x2, y2, color, alpha=0.55):
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return
    sub  = img[y1:y2, x1:x2]
    rect = np.full(sub.shape, color, dtype=np.uint8)
    cv2.addWeighted(rect, alpha, sub, 1 - alpha, 0, sub)
    img[y1:y2, x1:x2] = sub


def draw_rounded_rect(img, x1, y1, x2, y2, r, color, thickness=2):
    cv2.line(img, (x1+r, y1),   (x2-r, y1),   color, thickness)
    cv2.line(img, (x1+r, y2),   (x2-r, y2),   color, thickness)
    cv2.line(img, (x1,   y1+r), (x1,   y2-r), color, thickness)
    cv2.line(img, (x2,   y1+r), (x2,   y2-r), color, thickness)
    cv2.ellipse(img, (x1+r, y1+r), (r, r), 180, 0, 90, color, thickness)
    cv2.ellipse(img, (x2-r, y1+r), (r, r), 270, 0, 90, color, thickness)
    cv2.ellipse(img, (x1+r, y2-r), (r, r),  90, 0, 90, color, thickness)
    cv2.ellipse(img, (x2-r, y2-r), (r, r),   0, 0, 90, color, thickness)


def draw_label_with_bg(img, text, x, y, text_color=C_WHITE,
                       bg_color=C_DARK, font_scale=0.5, thickness=1, pad=6):
    font = cv2.FONT_HERSHEY_DUPLEX
    (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
    draw_filled_rect_alpha(img,
                           x - pad, y - th - pad,
                           x + tw + pad, y + pad,
                           bg_color, alpha=0.75)
    cv2.putText(img, text, (x, y), font, font_scale,
                text_color, thickness, cv2.LINE_AA)


# ─── DETECTOR ──────────────────────────────────────────────────────────────────

class Detector:
    """
    Full tracking pipeline using yolov8n OpenVINO model + sv.ByteTrack.

    Threading model
    ───────────────
    Main thread   — OpenVINO YOLO detect → sv.ByteTrack → zone hysteresis
                    → gender cache read → draw → return.  No waiting.

    Gender thread — batched gender inference for stale/new tracks only.
                    Writes into _gender_cache under _cache_lock.

    I/O thread    — drains _io_queue, writes JSON to disk.

    Key invariants
    ──────────────
    - model() is called with task="detect" — never .track() (incompatible
      with OpenVINO IR and causes segfaults).
    - sv.ByteTrack owns all tracking state on the main thread only.
    - Zone state is single-threaded (main thread).
    - Gender labels are display-only; 1-frame lag is invisible.
    - Background threads never crash or freeze the video loop.
    """

    def __init__(self, camera_name="cam_entry"):

        # ── OpenVINO model ────────────────────────────────────────────────────
        # Pass the exported directory path.  Ultralytics auto-detects the
        # OpenVINO IR inside and uses the CPU provider.
        # task="detect" is mandatory; omitting it can trigger a segfault on
        # some OpenVINO + Ultralytics version combinations.
        self.model = YOLO(YOLO_MODEL, task="detect")

        # Warm-up: compile the IR graph now so the first real frame is fast.
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model(dummy, verbose=False)

        # ── ByteTrack ─────────────────────────────────────────────────────────
        self.tracker = sv.ByteTrack()

        # ── Gender classifier ─────────────────────────────────────────────────
        self.gender_model = GenderClassifier(GENDER_MODEL)

        # ── Zone manager ──────────────────────────────────────────────────────
        with open(ZONE_FILE) as f:
            camera_data = json.load(f)[camera_name]

        self.zm = ZoneManager(
            camera_data,
            entry_frames=ENTRY_FRAMES,
            exit_frames=EXIT_FRAMES,
        )

        self.zone_color = {
            name: _ZONE_COLOR_BANK[idx % len(_ZONE_COLOR_BANK)]
            for idx, name in enumerate(self.zm.zones_pixel)
        }

        # ── Gender cache ──────────────────────────────────────────────────────
        self._gender_cache = {}   # tid → {"label": str, "confidence": float, "age": int}
        self._cache_lock   = threading.Lock()

        # ── Queues ────────────────────────────────────────────────────────────
        self._gender_queue = queue.Queue(maxsize=1)
        self._io_queue     = queue.Queue(maxsize=_IO_QUEUE_MAXSIZE)

        # ── Logs ──────────────────────────────────────────────────────────────
        self.event_log          = []
        self._flushed_count     = 0
        self.metrics_log        = []
        self._last_metrics      = 0.0
        self._last_events_flush = 0.0

        # ── Floor map static canvas ───────────────────────────────────────────
        self.MAP_SCALE     = 150
        self.MAP_W         = 900
        self.MAP_H         = 750
        self._floor_canvas = np.zeros((self.MAP_H, self.MAP_W, 3), dtype=np.uint8)
        self._build_floor_base()

        # ── Background threads ────────────────────────────────────────────────
        threading.Thread(target=self._gender_worker, daemon=True).start()
        threading.Thread(target=self._io_worker,     daemon=True).start()

    # =========================================================================
    # Gender thread
    # =========================================================================

    def _gender_worker(self):
        """
        Job payload: (frame, boxes, ids)
            boxes — np.ndarray (N, 4) float32  xyxy pixel coords
            ids   — np.ndarray (N,)   int       ByteTrack IDs
        """
        while True:
            job = self._gender_queue.get()
            if job is None:
                self._gender_queue.task_done()
                break
            try:
                frame, boxes, ids = job

                with self._cache_lock:
                    cache_snapshot = dict(self._gender_cache)

                stale_idx, stale_boxes = [], []
                for i, tid in enumerate(ids):
                    cached = cache_snapshot.get(tid)
                    if (cached is not None
                            and cached["age"] < GENDER_CACHE_TTL
                            and cached["confidence"] >= GENDER_CONF_THRESH):
                        with self._cache_lock:
                            if tid in self._gender_cache:
                                self._gender_cache[tid]["age"] += 1
                    else:
                        stale_idx.append(i)
                        stale_boxes.append(boxes[i])

                if stale_boxes:
                    preds = self.gender_model.predict(frame, stale_boxes)
                    with self._cache_lock:
                        for list_pos, orig_i in enumerate(stale_idx):
                            tid = ids[orig_i]
                            self._gender_cache[tid] = {
                                "label":      preds[list_pos]["label"],
                                "confidence": preds[list_pos]["confidence"],
                                "age":        0,
                            }

                active = set(ids)
                with self._cache_lock:
                    for tid in list(self._gender_cache.keys()):
                        if tid not in active:
                            del self._gender_cache[tid]

            except Exception as e:
                print(f"[WARN] gender worker error: {e}")
            finally:
                self._gender_queue.task_done()

    # =========================================================================
    # I/O thread
    # =========================================================================

    def _io_worker(self):
        while True:
            filepath, data = self._io_queue.get()
            try:
                with open(filepath, "w") as f:
                    json.dump(data, f, indent=2, default=str)
            except Exception as e:
                print(f"[WARN] I/O write failed ({filepath}): {e}")
            finally:
                self._io_queue.task_done()

    def _enqueue_write(self, filepath, data):
        try:
            self._io_queue.put_nowait((filepath, data))
        except queue.Full:
            print(f"[WARN] I/O queue full — dropping write to {filepath}")

    # =========================================================================
    # Floor map static base
    # =========================================================================

    def _build_floor_base(self):
        self._floor_canvas[:] = (22, 22, 30)

        for x in range(0, self.MAP_W, self.MAP_SCALE):
            cv2.line(self._floor_canvas, (x, 0), (x, self.MAP_H), (45, 45, 55), 1)
            cv2.putText(self._floor_canvas, f"{x // self.MAP_SCALE}m",
                        (x + 3, 13), cv2.FONT_HERSHEY_DUPLEX, 0.3, (80, 80, 100), 1)
        for y in range(0, self.MAP_H, self.MAP_SCALE):
            cv2.line(self._floor_canvas, (0, y), (self.MAP_W, y), (45, 45, 55), 1)
            cv2.putText(self._floor_canvas, f"{y // self.MAP_SCALE}m",
                        (3, y + 13), cv2.FONT_HERSHEY_DUPLEX, 0.3, (80, 80, 100), 1)

        for name, poly_world in self.zm.zones_world.items():
            if len(poly_world) < 3:
                continue
            color = self.zone_color[name]
            pts = np.array(
                [[int(p[0] * self.MAP_SCALE), int(p[1] * self.MAP_SCALE)]
                 for p in poly_world], dtype=np.int32)
            cv2.polylines(self._floor_canvas, [pts], True, color, 2, cv2.LINE_AA)

        cv2.rectangle(self._floor_canvas, (0, 0), (self.MAP_W, 24), (30, 30, 40), -1)
        cv2.line(self._floor_canvas, (0, 24), (self.MAP_W, 24), C_ACCENT, 1)
        cv2.putText(self._floor_canvas, "STORE FLOOR MAP  —  bird's-eye view",
                    (self.MAP_W // 2 - 155, 17),
                    cv2.FONT_HERSHEY_DUPLEX, 0.46, C_ACCENT, 1)

        lx, ly = self.MAP_W - 140, self.MAP_H - 52
        draw_filled_rect_alpha(self._floor_canvas,
                               lx - 8, ly - 14, self.MAP_W - 6, self.MAP_H - 6,
                               C_DARK, alpha=0.70)
        cv2.circle(self._floor_canvas, (lx + 6, ly),      5, (180, 180, 180), -1)
        cv2.putText(self._floor_canvas, "open area", (lx + 16, ly + 4),
                    cv2.FONT_HERSHEY_DUPLEX, 0.36, (180, 180, 180), 1)
        cv2.circle(self._floor_canvas, (lx + 6, ly + 22), 5, C_GREEN, -1)
        cv2.putText(self._floor_canvas, "in zone",   (lx + 16, ly + 26),
                    cv2.FONT_HERSHEY_DUPLEX, 0.36, C_GREEN, 1)

    # =========================================================================
    # Per-frame drawing helpers
    # =========================================================================

    def _draw_hud(self, output):
        font    = cv2.FONT_HERSHEY_DUPLEX
        pad     = 14
        row_h   = 36
        col_w   = 110
        label_w = 115
        n_zones = len(self.zm.zones_pixel)
        panel_w = label_w + 3 * col_w + 2 * pad
        panel_h = pad + 28 + n_zones * row_h + pad

        draw_filled_rect_alpha(output, 10, 10,
                               10 + panel_w, 10 + panel_h, C_DARK, alpha=0.72)
        cv2.rectangle(output, (10, 10),
                      (10 + panel_w, 10 + panel_h), C_ACCENT, 1)

        hx, hy = 10 + pad, 10 + pad + 16
        for title, offset in zip(
            ["ZONE", "NOW", "ENTRY", "EXIT"],
            [0, label_w, label_w + col_w, label_w + 2 * col_w],
        ):
            cv2.putText(output, title, (hx + offset, hy),
                        font, 0.42, C_ACCENT, 1, cv2.LINE_AA)

        div_y = 10 + pad + 22
        cv2.line(output, (10 + pad, div_y),
                 (10 + panel_w - pad, div_y), C_ACCENT, 1)

        for i, zone in enumerate(self.zm.zones_pixel):
            ry      = div_y + 8 + (i + 1) * row_h - 6
            inside  = len(self.zm.confirmed_inside[zone])
            entries = self.zm.zone_entry_count[zone]
            exits   = self.zm.zone_exit_count[zone]
            z_color = self.zone_color[zone]

            cv2.circle(output, (hx + 6, ry - 5), 5, z_color, -1)
            cv2.putText(output, zone.upper(),
                        (hx + 18, ry), font, 0.44, z_color, 1, cv2.LINE_AA)
            cv2.putText(output, str(inside),
                        (hx + label_w + 30, ry), font, 0.55,
                        C_GREEN if inside > 0 else C_WHITE, 1, cv2.LINE_AA)
            cv2.putText(output, str(entries),
                        (hx + label_w + col_w + 20, ry),
                        font, 0.55, C_GREEN, 1, cv2.LINE_AA)
            cv2.putText(output, str(exits),
                        (hx + label_w + 2 * col_w + 20, ry),
                        font, 0.55, C_RED, 1, cv2.LINE_AA)

    def _draw_zones(self, output):
        for name, poly in self.zm.zones_pixel.items():
            if len(poly) < 3:
                continue
            pts   = np.array(poly, dtype=np.int32)
            color = self.zone_color[name]
            cv2.polylines(output, [pts], True, color, 2, cv2.LINE_AA)
            cx = int(np.mean([p[0] for p in poly]))
            cy = int(np.mean([p[1] for p in poly]))
            draw_label_with_bg(output, name.upper(), cx - 30, cy,
                               text_color=color, bg_color=C_DARK)

    def _draw_track(self, output, track):
        x1, y1, x2, y2 = track["bbox"]
        gender_label    = track.get("gender", "?")

        cv2.rectangle(output, (x1, y1), (x2, y2), C_BBOX, 1)
        cv2.circle(output, track["foot"], 4, C_BBOX, -1)

        label = f"ID {track['id']} | {gender_label}"
        font  = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), _ = cv2.getTextSize(label, font, 0.5, 1)

        if y1 - th - 8 >= 0:
            lx, ly = x1, y1
        else:
            lx, ly = x1, y2 + th + 8

        lx = max(0, lx)
        rx = min(output.shape[1], lx + tw + 6)

        cv2.rectangle(output, (lx, ly - th - 8), (rx, ly), C_BLACK, -1)
        cv2.putText(output, label, (lx + 3, ly - 4),
                    font, 0.5, C_LABEL_TEXT, 1, cv2.LINE_AA)

    def _draw_floor_map(self, tracks):
        floor_map = self._floor_canvas.copy()

        for name, poly_world in self.zm.zones_world.items():
            if len(poly_world) < 3:
                continue
            color = self.zone_color[name]
            pts = np.array(
                [[int(p[0] * self.MAP_SCALE), int(p[1] * self.MAP_SCALE)]
                 for p in poly_world], dtype=np.int32)
            cx = int(np.mean(pts[:, 0]))
            cy = int(np.mean(pts[:, 1]))
            cv2.putText(floor_map, name.upper(),
                        (cx - 34, cy - 24),
                        cv2.FONT_HERSHEY_DUPLEX, 0.45, color, 1)
            cv2.putText(floor_map, f"NOW {len(self.zm.confirmed_inside[name])}",
                        (cx - 38, cy),
                        cv2.FONT_HERSHEY_DUPLEX, 0.40, C_GREEN, 1)
            cv2.putText(floor_map, f"E:{self.zm.zone_entry_count[name]}",
                        (cx - 38, cy + 20),
                        cv2.FONT_HERSHEY_DUPLEX, 0.38, (120, 255, 120), 1)
            cv2.putText(floor_map, f"X:{self.zm.zone_exit_count[name]}",
                        (cx + 14, cy + 20),
                        cv2.FONT_HERSHEY_DUPLEX, 0.38, (80, 80, 230), 1)

        for track in tracks:
            wp = self.zm.pixel_to_world(track["foot"][0], track["foot"][1])
            if wp is None:
                continue
            mx = int(wp[0] * self.MAP_SCALE)
            my = int(wp[1] * self.MAP_SCALE)
            if not (0 <= mx < self.MAP_W and 0 <= my < self.MAP_H):
                continue
            dot_col = C_GREEN if track["zones"] else (180, 180, 180)
            cv2.circle(floor_map, (mx, my), 8, dot_col, -1)
            cv2.circle(floor_map, (mx, my), 9, C_WHITE,  1)
            cv2.putText(floor_map, str(track["id"]),
                        (mx + 11, my + 4),
                        cv2.FONT_HERSHEY_DUPLEX, 0.38, dot_col, 1)

        return floor_map

    # =========================================================================
    # Main per-frame entry point
    # =========================================================================

    def process_frame(self, frame):
        """
        Steps
        -----
        1. OpenVINO detect  — model() on CPU, no .track(), no persist
        2. sv.ByteTrack     — assigns stable IDs from raw detections
        3. Zone hysteresis  — updates entry/exit state and event log
        4. Gender cache read
        5. Gender job post  — non-blocking, skip if thread busy
        6. Gender cache eviction for vanished tracks
        7. Draw
        8. Periodic I/O flush
        9. Return (annotated_frame, tracks, floor_map)
        """
        now    = time.time()
        output = frame.copy()

        # ── 1. OpenVINO inference ─────────────────────────────────────────────
        # NEVER call .track() with an OpenVINO model — it triggers a segfault
        # because Ultralytics' built-in tracker attempts CUDA ops on a CPU IR.
        results = self.model(
            frame,
            conf=0.1,
            iou=0.7,
            classes=0,      # person only
            verbose=False,
        )
        result = results[0]

        active_ids = set()
        tracks     = []

        if result.boxes is not None and len(result.boxes) > 0:

            # ── 2. ByteTrack ──────────────────────────────────────────────────
            detections = sv.Detections.from_ultralytics(result)
            tracked    = self.tracker.update_with_detections(detections)

            if tracked.tracker_id is not None and len(tracked) > 0:
                boxes = tracked.xyxy                        # (N,4) float32
                ids   = tracked.tracker_id.astype(int)      # (N,)  int

                for i in range(len(tracked)):
                    x1, y1, x2, y2 = boxes[i].astype(int)
                    tid             = ids[i]
                    cx, cy          = int((x1 + x2) / 2), int(y2)
                    foot_pixel      = (cx, cy)

                    active_ids.add(tid)
                    world_pt = self.zm.pixel_to_world(cx, cy)

                    # ── 3. Zone hysteresis ────────────────────────────────────
                    person_zones = []
                    for zone_name in self.zm.zones_pixel:
                        zone_poly_px = self.zm.zones_pixel[zone_name]
                        if len(zone_poly_px) < 3:
                            raw_inside = False
                        elif world_pt is not None and len(self.zm.zones_world[zone_name]) >= 3:
                            raw_inside = (
                                cv2.pointPolygonTest(
                                    np.array(self.zm.zones_world[zone_name], np.float32),
                                    tuple(world_pt), False,
                                ) >= 0
                            )
                        else:
                            raw_inside = (
                                cv2.pointPolygonTest(
                                    np.array(zone_poly_px, np.float32),
                                    foot_pixel, False,
                                ) >= 0
                            )

                        self.zm.apply_hysteresis(tid, zone_name, raw_inside,
                                                 now, self.event_log)
                        if tid in self.zm.confirmed_inside[zone_name]:
                            person_zones.append(zone_name)

                    # ── 4. Gender cache read ──────────────────────────────────
                    cached = self._gender_cache.get(tid)
                    gender = cached["label"] if cached else "?"

                    tracks.append({
                        "id":     tid,
                        "bbox":   (x1, y1, x2, y2),
                        "foot":   foot_pixel,
                        "zones":  person_zones,
                        "gender": gender,
                    })

                # ── 5. Post gender job ────────────────────────────────────────
                if not self._gender_queue.full():
                    try:
                        self._gender_queue.put_nowait((frame.copy(), boxes, ids))
                    except queue.Full:
                        pass

        # ── Cleanup lost tracks ───────────────────────────────────────────────
        self.zm.cleanup_lost_tracks(active_ids, now, self.event_log)

        # ── 6. Evict stale gender cache entries ───────────────────────────────
        with self._cache_lock:
            for tid in list(self._gender_cache.keys()):
                if tid not in active_ids:
                    del self._gender_cache[tid]

        # ── 7. Draw ───────────────────────────────────────────────────────────
        self._draw_zones(output)
        for track in tracks:
            self._draw_track(output, track)
        self._draw_hud(output)
        floor_map = self._draw_floor_map(tracks)

        # ── 8. Periodic I/O ───────────────────────────────────────────────────
        if now - self._last_events_flush >= EVENTS_FLUSH_INTERVAL:
            new_events = self.event_log[self._flushed_count:]
            if new_events:
                self._enqueue_write(EVENTS_FILE, {"events": new_events})
                self._flushed_count = len(self.event_log)
            if self._flushed_count > _MAX_EVENT_LOG_FLUSHED:
                del self.event_log[:self._flushed_count]
                self._flushed_count = 0
            self._last_events_flush = now

        if now - self._last_metrics >= METRICS_FLUSH_INTERVAL:
            log = {"time": self.zm.fmt_ts(now)}
            for zone in self.zm.zones_pixel:
                log[zone] = {
                    "current": len(self.zm.confirmed_inside[zone]),
                    "entries": self.zm.zone_entry_count[zone],
                    "exits":   self.zm.zone_exit_count[zone],
                }
            self.metrics_log.append(log)
            if len(self.metrics_log) > _MAX_METRICS_LOG:
                self.metrics_log = self.metrics_log[-_MAX_METRICS_LOG:]
            self._enqueue_write(METRICS_FILE, self.metrics_log)
            self._last_metrics = now

        # ── 9. Return ─────────────────────────────────────────────────────────
        return output, tracks, floor_map